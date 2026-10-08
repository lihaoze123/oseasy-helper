"""Experimental TCP file receiver for the researched 10.9 protocol."""
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import socket
import stat
import struct
import tempfile
import threading
import time

MAX_FRAME = 8 * 1024 * 1024
MAX_NODE_FRAME = 64 * 1024
MAX_TRANSFER_BYTES = 8 * 1024**3
MAX_ENTRIES = 10000
HELLO = struct.pack('<II', 4, 6)
READY = struct.pack('<II', 4, 7)
MAX_LISTENERS = 8
TASK_WAIT_SECONDS = 60


@dataclass(eq=False, frozen=True)
class ReceiveTask:
    token: str
    subtype: int
    local: str
    peer: str
    port: int


def read_frame(sock, stop, *, limit=MAX_FRAME, tick=None, idle=60):
    """Read a length-prefixed message, independent of TCP packet boundaries."""
    def exact(size):
        result = bytearray()
        last_data = time.monotonic()
        while len(result) < size:
            if stop.is_set():
                raise InterruptedError('Listener stopped')
            if tick:
                tick()
            try:
                chunk = sock.recv(size - len(result))
            except socket.timeout:
                if idle is not None and time.monotonic() - last_data >= idle:
                    raise TimeoutError('Incomplete frame / idle connection')
                continue
            if not chunk:
                raise EOFError('Connection closed before transfer end')
            result.extend(chunk)
            last_data = time.monotonic()
        return bytes(result)

    length, = struct.unpack('<I', exact(4))
    if not 4 <= length <= limit:
        raise ValueError(f'Invalid frame length: {length}')
    return exact(length)


def safe_path(root, raw):
    """Accept relative UTF-8 names, never remote absolute paths or device names."""
    if not 1 <= len(raw) <= 4096:
        raise ValueError('Invalid path length')
    name = raw.decode('utf-8').replace('\\', '/')
    parts = name.split('/')
    devices = {'CON', 'PRN', 'AUX', 'NUL', 'CONIN$', 'CONOUT$'}
    devices.update(f'{p}{n}' for p in ('COM', 'LPT') for n in '123456789¹²³')
    for part in parts:
        if (not part or part in ('.', '..') or part.endswith((' ', '.'))
                or any(ord(c) < 32 or c in '<>:"|?*' for c in part)
                or part.split('.')[0].upper() in devices):
            raise ValueError(f'Unsafe relative path: {name!r}')
    target = root.joinpath(*parts)
    # Reject existing links/junctions as well as lexical traversal. A local actor
    # with write access to the output directory is outside this receiver's scope.
    for ancestor in (root, *target.relative_to(root).parents):
        check = ancestor if ancestor == root else root / ancestor
        if check.exists():
            info = check.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
                raise ValueError('Output parent is a link or reparse point')
    if not target.resolve().is_relative_to(root.resolve()):
        raise ValueError('Path escapes output directory')
    if target.exists() or target.is_symlink():
        if target.is_symlink() or getattr(target.lstat(), 'st_file_attributes', 0) & 0x400:
            raise ValueError('Output target is a link or reparse point')
    return target


def counted_bytes(payload, offset):
    if len(payload) < offset + 4:
        raise ValueError('Truncated byte count')
    size, = struct.unpack_from('<I', payload, offset)
    value = payload[offset + 4:]
    if len(value) != size:
        raise ValueError('Byte count does not match payload')
    return value


class Transfer:
    """One sequential transfer; ACK only after successfully storing an entry."""
    def __init__(self, root, emit):
        self.root = Path(root)
        self.emit = emit
        self.file = None
        self.total = 0
        self.entries = 0
        self.done = False

    def close(self):
        if self.file is not None:
            self.file.close()
            self.file = None
            self.emit('file_partial', path=str(self.partial.relative_to(self.root)),
                      received=self.written, expected=self.expected)

    def handle(self, payload):
        if self.done or len(payload) < 4:
            raise ValueError('Unexpected transfer state')
        opcode, = struct.unpack_from('<I', payload)
        if opcode in (0, 3):
            if self.file is not None:
                raise ValueError('New entry before current file ended')
            self.entries += 1
            if self.entries > MAX_ENTRIES:
                raise ValueError('Transfer entry limit exceeded')
            if opcode == 3:
                path = safe_path(self.root, counted_bytes(payload, 4))
                path.mkdir(parents=True, exist_ok=True)
                self.emit('directory', path=str(path.relative_to(self.root)))
                return 1
            if len(payload) < 16:
                raise ValueError('Truncated file header')
            self.expected, = struct.unpack_from('<Q', payload, 4)
            if self.expected > MAX_TRANSFER_BYTES - self.total:
                raise ValueError('Transfer exceeds 8 GiB limit')
            self.path = safe_path(self.root, counted_bytes(payload, 12))
            if self.path.exists():
                raise FileExistsError(f'Will not overwrite {self.path.name!r}')
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.partial = self.path.with_name(self.path.name + '.part')
            self.file = self.partial.open('xb')
            self.written = 0
            self.digest = hashlib.sha256()
            self.emit('file_begin', path=str(self.path.relative_to(self.root)), bytes=self.expected)
        elif opcode in (1, 2):
            if self.file is None:
                raise ValueError('File data without a file header')
            chunk = counted_bytes(payload, 4)
            if self.written + len(chunk) > self.expected:
                raise ValueError('File exceeds declared size')
            self.file.write(chunk)
            self.digest.update(chunk)
            self.written += len(chunk)
            if opcode == 2:
                if self.written != self.expected:
                    raise ValueError(f'File size mismatch: {self.written}/{self.expected}')
                self.file.flush()
                os.fsync(self.file.fileno())
                self.file.close()
                self.file = None
                # Windows rename refuses an existing destination. On POSIX use
                # an exclusive hard link so a repeated filename cannot replace it.
                if os.name == 'nt':
                    self.partial.rename(self.path)
                else:
                    os.link(self.partial, self.path)
                    self.partial.unlink()
                self.total += self.written
                self.emit('file_saved', path=str(self.path.relative_to(self.root)),
                          bytes=self.written, sha256=self.digest.hexdigest())
                return 1
        elif opcode == 4:
            if len(payload) != 4 or self.file is not None:
                raise ValueError('Transfer end before file completion')
            self.done = True
            self.emit('transfer_complete', bytes=self.total, entries=self.entries)
            return 2
        else:
            raise ValueError(f'Unknown file opcode: {opcode}')
        return None


def receive_connection(sock, root, stop, emit):
    transfer = Transfer(root, emit)
    payload = b''
    sock.settimeout(0.5)
    try:
        while not transfer.done:
            payload = b''
            payload = read_frame(sock, stop)
            ack = transfer.handle(payload)
            if ack is not None:
                sock.sendall(struct.pack('<I', ack))
    except (OSError, EOFError, ValueError) as error:
        emit('data_error', error=str(error), sample_hex=payload[:256].hex())
        return False
    finally:
        transfer.close()
    return transfer.done


def node_message(payload, local, teacher, data_port, emit):
    if len(payload) < 4:
        raise ValueError('Truncated node opcode')
    opcode, = struct.unpack_from('<I', payload)
    if opcode != 3:
        emit('node_ignored', opcode=opcode, reason='Upload/other commands are not implemented')
        return
    task = payload[4:]
    if len(task) < 0x2c8:
        raise ValueError('Truncated receive task')
    def text_at(start, end):
        return task[start:end].split(b'\0', 1)[0].decode('ascii')
    task_local = text_at(0x200, 0x250)
    peer = text_at(0x250, 0x2a0)
    port, = struct.unpack_from('<H', task, 0x2a0)
    token = text_at(0x2a2, 0x2c4)
    emit('receive_task', local=task_local, peer=peer, port=port, token=token,
         matches_listener=(task_local == local and port == data_port))
    if task_local != local:
        emit('task_rejected', token=token, reason='Task names a different local interface')
        return None
    if not 1 <= port <= 65535 or not token:
        raise ValueError('Invalid task port or empty token')
    if peer:
        address = ipaddress.IPv4Address(peer)
        if address.is_unspecified or address.is_multicast or address.is_reserved:
            raise ValueError('Invalid task sender address')
    return ReceiveTask(token, struct.unpack_from('<I', task, 0x2c4)[0], task_local, peer, port)


def completion_report(local, subtype, folder):
    """Native node opcode 5: success, empty detail, IP, subtype, UTF-16 path."""
    path = (str(Path(folder).absolute()).rstrip('\\/') + '\\' + '\0').encode('utf-16le')
    frame = bytearray(0x460 + len(path))
    struct.pack_into('<III', frame, 0, len(frame) - 4, 5, 3)
    ip = local.encode('ascii')
    if len(ip) >= 80:
        raise ValueError('Local address exceeds report field')
    frame[0x40c:0x40c + len(ip)] = ip
    struct.pack_into('<I', frame, 0x45c, subtype)
    frame[0x460:] = path
    return bytes(frame)


class NodeReports:
    """Track task identity per listener; never report across node generations."""
    def __init__(self):
        self.lock = threading.Condition()
        self.tasks = {}
        self.pending = {}
        self.ready_needed = False

    def reset(self):
        with self.lock:
            self.tasks.clear()
            self.pending.clear()
            self.ready_needed = False
            self.lock.notify_all()

    def assign(self, task):
        with self.lock:
            current = self.tasks.get(task.port)
            if current is not None:
                # Retransmitting the same task cannot replace an active identity.
                old = current[0]
                return (old.token, old.subtype, old.local, old.peer) == (
                    task.token, task.subtype, task.local, task.peer)
            if len(self.tasks) >= MAX_LISTENERS:
                return False
            self.tasks[task.port] = (task, False, time.monotonic())
            self.lock.notify_all()
            return True

    def snapshot(self, port):
        with self.lock:
            current = self.tasks.get(port)
            return current[0] if current else None

    def claim(self, port, peer, teacher, *, allow_unassigned=False, stop=None):
        with self.lock:
            # Tasks/data use separate TCP connections and can arrive out of order.
            deadline = time.monotonic() + 1
            while port not in self.tasks and time.monotonic() < deadline:
                if stop is not None and stop.is_set():
                    return None, False
                self.lock.wait(timeout=min(0.1, max(0, deadline - time.monotonic())))
            current = self.tasks.get(port)
            if current is None:
                return None, allow_unassigned and peer == teacher
            task, claimed, assigned = current
            if claimed or peer not in (teacher, task.peer):
                return None, False
            self.tasks[port] = (task, True, assigned)
            return task, True

    def abandon(self, task):
        with self.lock:
            current = self.tasks.get(task.port) if task is not None else None
            if current and current[0] is task:
                del self.tasks[task.port]
                self.pending.pop(task.port, None)
                self.ready_needed = True

    def expire(self, emit):
        expired = []
        with self.lock:
            for port, (task, claimed, assigned) in list(self.tasks.items()):
                if not claimed and time.monotonic() - assigned >= TASK_WAIT_SECONDS:
                    del self.tasks[port]
                    expired.append(task)
                    self.ready_needed = True
        for task in expired:
            emit('task_expired', token=task.token, port=task.port,
                 reason='No data connection within 60 seconds')

    def complete(self, task, folder):
        with self.lock:
            current = self.tasks.get(task.port) if task is not None else None
            if not current or current[0] is not task:
                return False
            self.pending[task.port] = (task, folder)
            return True

    def send(self, sock, local, emit):
        with self.lock:
            for port, (task, folder) in list(self.pending.items()):
                sock.sendall(completion_report(local, task.subtype, folder))
                sock.sendall(READY)
                del self.tasks[port]
                del self.pending[port]
                emit('node_report_sent', status=3, token=task.token, directory=str(folder))
            if self.ready_needed:
                sock.sendall(READY)
                self.ready_needed = False


def node_loop(args, stop, emit, reports=None, listeners=None):
    reports = reports or NodeReports()
    last_error = None
    while not stop.is_set():
        try:
            with socket.socket() as sock:
                sock.bind((args.local, 0))
                sock.settimeout(3)
                sock.connect((args.teacher, args.node_port))
                sock.settimeout(0.5)
                last_hello = -float('inf')
                def hello():
                    nonlocal last_hello
                    reports.expire(emit)
                    reports.send(sock, args.local, emit)
                    if time.monotonic() - last_hello >= 20:
                        sock.sendall(HELLO)
                        last_hello = time.monotonic()
                hello()
                # The native receiver announces that its local data listener is
                # ready with opcode 7. The server does not assign a receive task
                # after opcode 6 alone.
                sock.sendall(READY)
                emit('node_connected', host=args.teacher, port=args.node_port)
                emit('node_ready', local=args.local, port=args.data_port)
                last_error = None
                while not stop.is_set():
                    payload = read_frame(sock, stop, limit=MAX_NODE_FRAME, tick=hello, idle=None)
                    emit('node_frame', length=len(payload), sample_hex=payload[:4096].hex())
                    task = node_message(payload, args.local, args.teacher, args.data_port, emit)
                    if task is not None:
                        try:
                            if listeners is not None:
                                listeners.ensure(task.port)
                            elif task.port != args.data_port:
                                raise ValueError('Dynamic listener is unavailable')
                            if not reports.assign(task):
                                raise ValueError('Another task is active on this data port')
                            emit('task_listener_ready', token=task.token, local=task.local,
                                 port=task.port, peer=task.peer)
                        except (OSError, ValueError) as error:
                            emit('task_rejected', token=task.token, port=task.port, reason=str(error))
        except (OSError, EOFError, ValueError) as error:
            if not stop.is_set() and str(error) != last_error:
                emit('node_retry', error=str(error), retry_seconds=getattr(args, 'reconnect_delay', 5))
                last_error = str(error)
        finally:
            reports.reset()
        stop.wait(getattr(args, 'reconnect_delay', 5))


class Events:
    def __init__(self, path):
        self.file = path.open('x', encoding='utf-8')
        self.lock = threading.Lock()
        self.bytes = 0

    def __call__(self, event, **fields):
        line = json.dumps(dict(time=time.strftime('%Y-%m-%dT%H:%M:%S%z'), event=event, **fields),
                          ensure_ascii=True)
        with self.lock:
            if event != 'node_frame':
                print(line, flush=True)
            if self.bytes < 16 * 1024 * 1024:
                self.file.write(line + '\n')
                self.file.flush()
                self.bytes += len(line) + 1


def accept_loop(listener, args, root, stop, events, reports, retiring=None, busy=None):
    port = listener.getsockname()[1]
    retiring = retiring if retiring is not None else threading.Event()
    busy = busy if busy is not None else threading.Event()
    task = None
    try:
        while not stop.is_set() and not retiring.is_set():
            try:
                sock, peer = listener.accept()
            except socket.timeout:
                continue
            busy.set()
            task = None
            try:
                with sock:
                    if stop.is_set() or retiring.is_set():
                        continue
                    task, allowed = reports.claim(port, peer[0], args.teacher,
                        allow_unassigned=(port == args.data_port), stop=stop)
                    if not allowed:
                        events('peer_rejected', peer=peer[0], port=port,
                               reason='No matching available task for this sender')
                        continue
                    folder = Path(tempfile.mkdtemp(prefix='transfer-', dir=root))
                    events('data_connected', peer=peer[0], port=port,
                           token=task.token if task else None, directory=folder.name)
                    complete = receive_connection(sock, folder, stop,
                        lambda event, **fields: events(event, transfer=folder.name, **fields))
                    if complete:
                        if not reports.complete(task, folder):
                            events('node_report_skipped', directory=str(folder),
                                   reason='No matching task on the current node connection')
                    else:
                        reports.abandon(task)
            finally:
                busy.clear()
    except Exception as error:
        reports.abandon(task)
        events('listener_error', port=port, error=str(error))
        stop.set()


class Listeners:
    """Bind task-selected ports only on the configured classroom interface."""
    def __init__(self, args, root, stop, events, reports):
        self.args, self.root, self.stop = args, root, stop
        self.events, self.reports = events, reports
        self.entries = {}

    def ensure(self, port):
        if port in self.entries:
            return
        if len(self.entries) >= MAX_LISTENERS:
            # Recycle an idle dynamic port; keep the default listener available.
            for old, (sock, worker, retiring, busy) in list(self.entries.items()):
                if old != self.args.data_port and not busy.is_set() and self.reports.snapshot(old) is None:
                    retiring.set()
                    worker.join()
                    sock.close()
                    del self.entries[old]
                    self.events('listener_retired', port=old)
                    break
            else:
                raise ValueError('All eight file listeners are busy')
        sock = socket.socket()
        try:
            if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            else:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((self.args.local, port))
            sock.listen(4)
            sock.settimeout(0.5)
            retiring, busy = threading.Event(), threading.Event()
            worker = threading.Thread(target=accept_loop,
                args=(sock, self.args, self.root, self.stop, self.events, self.reports, retiring, busy),
                name=f'file-data-{port}')
            self.entries[port] = (sock, worker, retiring, busy)
            worker.start()
        except BaseException:
            sock.close()
            self.entries.pop(port, None)
            raise
        self.events('listening', local=self.args.local, port=port, teacher=self.args.teacher,
                    output=str(self.root))

    def close(self):
        for sock, worker, retiring, _ in self.entries.values():
            retiring.set()
        for sock, worker, _, _ in self.entries.values():
            worker.join()
            sock.close()
        self.entries.clear()


@contextmanager
def receiver(args, stop):
    """Bind before login and keep receivers alive across management reconnects."""
    output = Path(args.receive_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix=time.strftime('%Y%m%d-%H%M%S-'), dir=output))
    events = Events(root / 'events.jsonl')
    reports = NodeReports()
    listeners = Listeners(args, root, stop, events, reports)
    worker = None
    try:
        listeners.ensure(args.data_port)
        worker = threading.Thread(target=node_loop,
            args=(args, stop, events, reports, listeners), name='file-node')
        worker.start()
        yield events
    finally:
        stop.set()
        if worker:
            worker.join()
        listeners.close()
        events('stopped')
        events.file.close()
