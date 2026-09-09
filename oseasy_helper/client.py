"""Experimental management login; received commands are observed, never executed."""
import getpass
import json
from pathlib import Path
import re
import socket
import struct
import threading
import time

import psutil

from .files import read_frame


def interface_mac(local):
    for addresses in psutil.net_if_addrs().values():
        if any(a.family == socket.AF_INET and a.address == local for a in addresses):
            for address in addresses:
                if address.family == psutil.AF_LINK:
                    mac = address.address.replace('-', ':').upper()
                    if re.fullmatch(r'(?:[0-9A-F]{2}:){5}[0-9A-F]{2}', mac):
                        return mac
    raise ValueError('No MAC address found for --local')


def login_packet(name, user, mac, local, timestamp):
    # Observed PC login: ten slash-separated fields; empty first/fourth fields.
    fields = ['', name, user, timestamp, '', '1', '0', '0', mac, local]
    if any('/' in field or any(ord(c) < 32 for c in field) for field in fields):
        raise ValueError('Login fields cannot contain slashes or control characters')
    body = ('/'.join(fields) + '/').encode('utf-16-le')
    payload = struct.pack('<IIII', 6, 0, 0, len(body)) + body
    return struct.pack('<I', len(payload)) + payload


def message(payload):
    if len(payload) < 16:
        raise ValueError('Truncated management header')
    command, kind, extra, size = struct.unpack_from('<IIII', payload)
    # Some commands carry data beyond the first declared field. Preserve its
    # length in diagnostics instead of guessing how the extra fields work.
    if size > len(payload) - 16:
        raise ValueError('Management body is shorter than its declared size')
    return dict(command=command, kind=kind, extra=extra,
                declared_bytes=size, body_bytes=len(payload) - 16)


def thumbnail_reply(fields, jpeg):
    if fields['command'] != 89 or fields['kind'] != 64:
        return None
    payload = struct.pack('<IIII', 43, 64, 0, len(jpeg)) + jpeg
    return struct.pack('<I', len(payload)) + payload


def directory_reply(fields, receive_dir):
    """Offer only our receiving directory, with no disk or child enumeration."""
    if fields['command'] != 87 or fields['extra'] != 1:
        return None
    path = (str(receive_dir) + '\0').encode('utf-16-le')
    if len(path) > 0x208:
        raise ValueError('Receiving directory exceeds the protocol path limit')
    # Native directory response: 64 entry slots, disk list, current path.
    # Zero counts are intentional: only the current receive directory is offered.
    body = bytearray(0x285b0)
    body[0x283a8:0x283a8 + len(path)] = path
    payload = struct.pack('<IIII', 88, 0, 0, len(body)) + body
    return struct.pack('<I', len(payload)) + payload


def run(args):
    stop = threading.Event()
    mac = interface_mac(args.local)
    receive_dir = Path(args.receive_dir).resolve()
    receive_dir.mkdir(parents=True, exist_ok=True)
    jpeg = (Path(__file__).with_name('mock-thumbnail.jpg').read_bytes()
            if args.mock_thumbnail else None)
    def emit(event, **fields):
        print(json.dumps(dict(time=time.strftime('%Y-%m-%dT%H:%M:%S%z'),
                              event=event, **fields)), flush=True)
    with socket.socket() as sock:
        sock.bind((args.local, 0))
        sock.settimeout(5)
        sock.connect((args.teacher, args.port))
        sock.settimeout(0.5)
        sock.sendall(login_packet(socket.gethostname(), getpass.getuser(), mac,
                                  args.local, time.strftime('%Y-%m-%d %H:%M:%S')))
        emit('login_sent', note='TCP connected; teacher acceptance is not yet verified')
        try:
            while True:
                fields = message(read_frame(sock, stop, idle=None))
                emit('management_message', **fields)
                reply = directory_reply(fields, receive_dir)
                if reply is not None:
                    sock.sendall(reply)
                    emit('receive_directory_sent', path=str(receive_dir))
                if jpeg is not None:
                    reply = thumbnail_reply(fields, jpeg)
                    if reply is not None:
                        sock.sendall(reply)
                        emit('mock_thumbnail_sent', bytes=len(jpeg), width=64, height=64)
                if fields['command'] == 25:
                    emit('file_transfer_command', kind=fields['kind'])
        except EOFError:
            emit('disconnected')
