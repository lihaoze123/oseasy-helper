"""Fragmented H.264 -> MPEG-TS over loopback HTTP; no pixel decoder or GUI."""
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import queue
import re
import select
import socket
import struct
import sys
import threading
import time


def nal_types(data):
    return {data[m.end()] & 31 for m in re.finditer(b'\x00\x00\x01', data)
            if m.end() < len(data)}


@dataclass
class Frame:
    data: bytes
    key: bool
    width: int
    height: int
    received: float


@dataclass
class Parts:
    count: int
    width: int
    height: int
    received: float
    pieces: dict = field(default_factory=dict)
    size: int = 0


class Reassembler:
    def __init__(self):
        self.pending = {}
        self.next = None
        self.last_packet = None
        self.need_key = True
        self.lost = self.invalid = self.duplicates = 0

    def push(self, packet, now=None):
        now = time.monotonic() if now is None else now
        if not 16 < len(packet) <= 65507:
            self.invalid += 1
            return []
        magic, index, count, width, height, seq, _, _ = struct.unpack_from('<8H', packet)
        if magic != 65535 or not 0 <= index < count <= 4096 or not (16 <= width <= 8192 and 16 <= height <= 8192):
            self.invalid += 1
            return []
        if self.last_packet is not None and now - self.last_packet > 2:
            self.pending.clear()
            self.next, self.need_key = None, True
        self.last_packet = now
        if self.next is None:
            self.next = seq
        ahead = (seq - self.next) & 65535
        if ahead >= 32768:
            self.duplicates += 1
            return []
        if ahead > 32 or len(self.pending) > 32:
            self.lost += max(1, ahead)
            self.pending.clear()
            self.next, self.need_key = seq, True
        frame = self.pending.setdefault(seq, Parts(count, width, height, now))
        if (frame.count, frame.width, frame.height) != (count, width, height):
            self.invalid += 1
            return []
        if index in frame.pieces:
            self.duplicates += 1
            return []
        body = packet[16:]
        if frame.size + len(body) > 8 * 1024 * 1024:
            del self.pending[seq]
            self.invalid += 1
            self.need_key = True
            return []
        frame.pieces[index] = body
        frame.size += len(body)
        return self.drain(now)

    def drain(self, now=None):
        now = time.monotonic() if now is None else now
        complete = []
        while self.pending:
            frame = self.pending.get(self.next)
            if frame and len(frame.pieces) == frame.count:
                del self.pending[self.next]
                self.next = (self.next + 1) & 65535
                data = b''.join(frame.pieces[i] for i in range(frame.count))
                key = {5, 7, 8} <= nal_types(data)
                if self.need_key and not key:
                    continue
                self.need_key = False
                complete.append(Frame(data, key, frame.width, frame.height, frame.received))
                continue
            if now - min(f.received for f in self.pending.values()) < 0.4:
                break
            self.need_key = True
            nearest = min(self.pending, key=lambda seq: (seq - self.next) & 65535)
            distance = (nearest - self.next) & 65535
            if distance == 0:
                del self.pending[self.next]
                self.next = (self.next + 1) & 65535
                self.lost += 1
            else:
                self.next = nearest
                self.lost += distance
        return complete


def mpeg_crc(data):
    crc = 0xffffffff
    for byte in data:
        crc ^= byte << 24
        for _ in range(8):
            crc = ((crc << 1) ^ (0x04c11db7 if crc & 0x80000000 else 0)) & 0xffffffff
    return crc


class TsMuxer:
    """H.264 PES in 188-byte TS packets; monotonic arrival-clock PTS/PCR."""
    def __init__(self):
        self.counters = {0: 0, 0x1000: 0, 0x100: 0}
        self.origin, self.last_pts = None, -1

    def counter(self, pid):
        value = self.counters[pid]
        self.counters[pid] = (value + 1) & 15
        return value

    def psi(self, pid, section):
        data = b'\0' + section + struct.pack('>I', mpeg_crc(section))
        return bytes((0x47, 0x40 | (pid >> 8), pid & 255, 0x10 | self.counter(pid))) + data.ljust(184, b'\xff')

    def mux(self, frame):
        if self.origin is None:
            self.origin = frame.received
        pts = max(self.last_pts + 1, round((frame.received - self.origin) * 90000) + 90000)
        self.last_pts = pts
        pcr = max(0, pts - 4500) & ((1 << 33) - 1)
        pts &= (1 << 33) - 1
        result = bytearray(self.psi(0, bytes.fromhex('00b00d0001c100000001f000')))
        result.extend(self.psi(0x1000, bytes.fromhex('02b0120001c10000e100f0001be100f000')))
        timestamp = bytes((0x21 | (((pts >> 30) & 7) << 1), (pts >> 22) & 255,
                           (((pts >> 15) & 127) << 1) | 1, (pts >> 7) & 255, ((pts & 127) << 1) | 1))
        aud = b'' if 9 in nal_types(frame.data) else b'\x00\x00\x00\x01\x09\xf0'
        pes = b'\x00\x00\x01\xe0\x00\x00\x80\x80\x05' + timestamp + aud + frame.data
        offset, first = 0, True
        while offset < len(pes):
            size = min(len(pes) - offset, 176 if first else 184)
            padding = 184 - size
            packet = bytearray((0x47, 0x41 if first else 0x01, 0,
                                (0x30 if padding else 0x10) | self.counter(0x100)))
            if padding:
                packet.append(padding - 1)
                if padding > 1:
                    packet.append((0x10 | (0x40 if frame.key else 0)) if first else 0)
                if first:
                    packet.extend(bytes(((pcr >> 25) & 255, (pcr >> 17) & 255, (pcr >> 9) & 255,
                                         (pcr >> 1) & 255, ((pcr & 1) << 7) | 0x7e, 0)))
                packet.extend(b'\xff' * (4 + padding - len(packet)))
            packet.extend(pes[offset:offset + size])
            result.extend(packet)
            offset += size
            first = False
        return bytes(result)


class Client:
    def __init__(self):
        self.ready = False
        self.queue = queue.Queue(maxsize=64)
        self.dead = threading.Event()
        self.buffered = 0
        self.lock = threading.Lock()

    def offer(self, data, key):
        if self.dead.is_set() or (not self.ready and not key):
            return
        self.ready = True
        with self.lock:
            if self.buffered + len(data) > 8 * 1024 * 1024:
                self.dead.set()
                return
            try:
                self.queue.put_nowait(data)
                self.buffered += len(data)
            except queue.Full:
                self.dead.set()


class State:
    def __init__(self):
        self.reassembler, self.muxer = Reassembler(), TsMuxer()
        self.clients, self.lock = [], threading.Lock()
        self.packets = self.frames = 0
        self.running = True

    def publish(self, frame):
        self.frames += 1
        ts = self.muxer.mux(frame)
        with self.lock:
            for client in self.clients:
                client.offer(ts, frame.key)


def handler_for(state):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            if self.path != '/live.ts':
                self.send_error(404)
                return
            client = Client()
            with state.lock:
                if len(state.clients) >= 4:
                    self.send_error(503, 'Maximum 4 players')
                    return
                state.clients.append(client)
            try:
                self.connection.settimeout(3)
                self.send_response(200)
                self.send_header('Content-Type', 'video/mp2t')
                self.send_header('Cache-Control', 'no-store')
                self.send_header('Connection', 'close')
                self.end_headers()
                while state.running and not client.dead.is_set():
                    try:
                        data = client.queue.get(timeout=0.5)
                    except queue.Empty:
                        readable, _, _ = select.select([self.connection], [], [], 0)
                        if readable and not self.connection.recv(1, socket.MSG_PEEK):
                            break
                        continue
                    with client.lock:
                        client.buffered -= len(data)
                    self.wfile.write(data)
            except OSError:
                pass
            finally:
                client.dead.set()
                with state.lock:
                    state.clients.remove(client)
    return Handler


def receive(args):
    state, server = State(), None
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
        try:
            udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            udp.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * 1024 * 1024)
            udp.bind(('0.0.0.0', args.udp_port))
            udp.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP,
                           socket.inet_aton(args.group) + socket.inet_aton(args.local))
            udp.settimeout(0.1)
            server = ThreadingHTTPServer(('127.0.0.1', args.http_port), handler_for(state))
            server.daemon_threads = True
            threading.Thread(target=server.serve_forever, daemon=True).start()
            print(f'http://127.0.0.1:{args.http_port}/live.ts', flush=True)
            print('Waiting for a complete H.264 keyframe. Ctrl+C stops.', file=sys.stderr, flush=True)
            while True:
                try:
                    packet, address = udp.recvfrom(65536)
                    if address[0] != args.teacher:
                        continue
                    state.packets += 1
                    frames = state.reassembler.push(packet)
                except socket.timeout:
                    frames = state.reassembler.drain()
                for frame in frames:
                    if not state.frames:
                        print(f'Receiving H.264: {frame.width}x{frame.height}; open the URL in your player.',
                              file=sys.stderr, flush=True)
                    state.publish(frame)
        except KeyboardInterrupt:
            pass
        finally:
            state.running = False
            if server:
                server.shutdown()
                server.server_close()
            print(f'Stopped: packets={state.packets}, frames={state.frames}, '
                  f'lost={state.reassembler.lost}, invalid={state.reassembler.invalid}',
                  file=sys.stderr, flush=True)
