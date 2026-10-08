"""Protocol tests with real sockets; no classroom network or vendor runtime."""
import contextlib
import http.client
import io
import json
import os
from pathlib import Path
import socket
import signal
import struct
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from oseasy_helper import client, files, video


def frame(opcode, body=b''):
    payload = struct.pack('<I', opcode) + body
    return struct.pack('<I', len(payload)) + payload


def counted(data):
    return struct.pack('<I', len(data)) + data


def task_packet(port, token='task', peer='127.0.0.2', local='127.0.0.1', subtype=9):
    task = bytearray(0x4d0)
    for offset, value in ((0x200, local), (0x250, peer), (0x2a2, token)):
        raw = value.encode('ascii')
        task[offset:offset + len(raw)] = raw
    struct.pack_into('<H', task, 0x2a0, port)
    struct.pack_into('<I', task, 0x2c4, subtype)
    return frame(3, task)


def listener():
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    sock.listen()
    sock.settimeout(5)
    return sock


def unused_port(kind=socket.SOCK_STREAM):
    with socket.socket(socket.AF_INET, kind) as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


class StudentTests(unittest.TestCase):
    @unittest.skipIf(os.name == 'nt', 'POSIX SIGINT process test')
    def test_sigint_releases_student_ports_and_records_shutdown(self):
        with tempfile.TemporaryDirectory() as folder, listener() as management, listener() as node:
            data_port, http_port = unused_port(), unused_port()
            args = [sys.executable, '-u', '-m', 'oseasy_helper', 'student',
                '--teacher', '127.0.0.1', '--local', '127.0.0.1',
                '--port', str(management.getsockname()[1]), '--node-port', str(node.getsockname()[1]),
                '--data-port', str(data_port), '--http-port', str(http_port),
                '--udp-port', str(unused_port(socket.SOCK_DGRAM)), '--receive-dir', folder,
                '--mac', '02:00:00:00:00:01']
            proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                with management.accept()[0] as connection:
                    connection.settimeout(4)
                    self.assertEqual(struct.unpack_from('<I', files.read_frame(connection, threading.Event()))[0], 6)
                    proc.send_signal(signal.SIGINT)
                    stdout, stderr = proc.communicate(timeout=7)
                self.assertEqual(proc.returncode, 130, stderr)
                events = [json.loads(line) for line in next(Path(folder).rglob('events.jsonl')).read_text().splitlines()]
                self.assertIn('video_stopped', [event['event'] for event in events])
                self.assertEqual(events[-1]['event'], 'stopped')
                for port in (data_port, http_port):
                    with socket.socket() as check:
                        check.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                        check.bind(('127.0.0.1', port))
            finally:
                if proc.poll() is None:
                    proc.kill()
                    proc.communicate()

    def test_reconnect_relay_dynamic_port_and_video_together(self):
        with tempfile.TemporaryDirectory() as folder, listener() as management, listener() as node:
            stop = threading.Event()
            args = SimpleNamespace(local='127.0.0.1', teacher='127.0.0.1',
                port=management.getsockname()[1], node_port=node.getsockname()[1],
                data_port=unused_port(), receive_dir=folder, mock_thumbnail=True,
                reconnect_delay=0.1, once=False, with_video=True,
                udp_port=unused_port(socket.SOCK_DGRAM), http_port=unused_port(),
                mac='02:00:00:00:00:01', name='TEST-PC', user='test')
            output, errors = io.StringIO(), []
            def run():
                try:
                    client.run(args, stop)
                except BaseException as error:
                    errors.append(error)
            worker = threading.Thread(target=run)
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(io.StringIO()), contextlib.ExitStack() as stack:
                worker.start()
                try:
                    login = stack.enter_context(management.accept()[0])
                    tasks = stack.enter_context(node.accept()[0])
                    for conn in (login, tasks):
                        conn.settimeout(5)
                    first_login = files.read_frame(login, stop)
                    self.assertIn('/TEST-PC/test/', first_login[16:].decode('utf-16le'))
                    self.assertEqual(files.read_frame(tasks, stop), struct.pack('<I', 6))
                    self.assertEqual(files.read_frame(tasks, stop), struct.pack('<I', 7))
                    # Reply to observed thumbnail and directory requests.
                    requests = struct.pack('<IIII', 89, 64, 0, 0)
                    login.sendall(struct.pack('<I', len(requests)) + requests)
                    reply = files.read_frame(login, stop)
                    self.assertEqual(struct.unpack_from('<II', reply), (43, 64))
                    self.assertEqual(reply[16:18], b'\xff\xd8')
                    request = struct.pack('<IIII', 87, 0, 1, 0)
                    login.sendall(struct.pack('<I', len(request)) + request)
                    self.assertEqual(struct.unpack_from('<I', files.read_frame(login, stop))[0], 88)
                    port = unused_port()
                    tasks.sendall(task_packet(port))
                    # Dynamic listener is created asynchronously from this task.
                    deadline = time.monotonic() + 4
                    while True:
                        try:
                            attacker = socket.create_connection(('127.0.0.1', port),
                                timeout=2, source_address=('127.0.0.3', 0))
                            break
                        except ConnectionRefusedError:
                            if time.monotonic() >= deadline:
                                raise
                            stop.wait(0.02)
                    with attacker:
                        self.assertEqual(attacker.recv(4), b'')
                    sender = stack.enter_context(socket.create_connection(('127.0.0.1', port),
                        timeout=5, source_address=('127.0.0.2', 0)))
                    content, name = b'file continues across management reconnect', '课堂.txt'.encode()
                    sender.sendall(frame(0, struct.pack('<Q', len(content)) + counted(name))
                                   + frame(1, counted(content[:7])))
                    login.shutdown(socket.SHUT_RDWR)
                    login.close()
                    login2 = stack.enter_context(management.accept()[0])
                    login2.settimeout(5)
                    second_login = files.read_frame(login2, stop)
                    self.assertEqual(first_login[:16], second_login[:16])
                    sender.sendall(frame(2, counted(content[7:])))
                    self.assertEqual(sender.recv(4), struct.pack('<I', 1))
                    sender.sendall(frame(4))
                    self.assertEqual(sender.recv(4), struct.pack('<I', 2))
                    report = files.read_frame(tasks, stop)
                    self.assertEqual(struct.unpack_from('<II', report), (5, 3))
                    self.assertEqual(struct.unpack_from('<I', report, 0x458)[0], 9)
                    self.assertEqual(files.read_frame(tasks, stop), struct.pack('<I', 7))
                    self.assertEqual(next(Path(folder).rglob('课堂.txt')).read_bytes(), content)
                    # Structural H.264 sample verifies UDP -> MPEG-TS -> HTTP,
                    # not pixel decoding. Receive URL stays alive after reconnect.
                    connection = http.client.HTTPConnection('127.0.0.1', args.http_port, timeout=5)
                    stack.callback(connection.close)
                    connection.request('GET', '/live.ts')
                    response = connection.getresponse()
                    stack.callback(response.close)
                    self.assertEqual(response.status, 200)
                    key = bytes.fromhex('000000016704000000016805000000016506')
                    packet = struct.pack('<8H', 65535, 0, 1, 320, 180, 1, 320, 180) + key
                    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
                        udp.sendto(packet, ('127.0.0.1', args.udp_port))
                    ts = response.read(188 * 3)
                    self.assertEqual([ts[i] for i in (0, 188, 376)], [0x47] * 3)
                finally:
                    stop.set()
                    worker.join(7)
                self.assertFalse(worker.is_alive())
                self.assertEqual(errors, [])
            events = [json.loads(line) for line in next(Path(folder).rglob('events.jsonl')).read_text().splitlines()]
            names = [event['event'] for event in events]
            for expected in ('management_retry', 'peer_rejected', 'file_saved', 'node_report_sent',
                             'video_receiving', 'video_stopped', 'stopped'):
                self.assertIn(expected, names)
            self.assertEqual(names.count('login_sent'), 2)
            self.assertFalse(any(t.name.startswith(('file-', 'video-')) for t in threading.enumerate()))

    def test_task_conflict_duplicate_expiry_and_sender_filter(self):
        reports = files.NodeReports()
        task = files.ReceiveTask('one', 9, '127.0.0.1', '127.0.0.2', 19100)
        self.assertTrue(reports.assign(task))
        self.assertTrue(reports.assign(files.ReceiveTask('one', 9, task.local, task.peer, task.port)))
        self.assertFalse(reports.assign(files.ReceiveTask('two', 9, task.local, task.peer, task.port)))
        self.assertIs(reports.snapshot(19100), task)
        self.assertEqual(reports.claim(19100, '127.0.0.3', '127.0.0.1'), (None, False))
        self.assertEqual(reports.claim(19100, task.peer, '127.0.0.1'), (task, True))
        self.assertEqual(reports.claim(19100, task.peer, '127.0.0.1'), (None, False))
        with patch('oseasy_helper.files.time.monotonic', return_value=time.monotonic() + 100):
            reports.expire(Mock())
        self.assertIs(reports.snapshot(19100), task)  # Active transfers do not expire.
        reports.abandon(task)
        self.assertIsNone(reports.snapshot(19100))
        sock = Mock()
        reports.send(sock, task.local, Mock())
        sock.sendall.assert_called_once_with(files.READY)
        self.assertTrue(reports.assign(task))
        emit = Mock()
        with patch('oseasy_helper.files.time.monotonic', return_value=time.monotonic() + 100):
            reports.expire(emit)
        self.assertIsNone(reports.snapshot(19100))
        self.assertEqual(emit.call_args.args[0], 'task_expired')

    def test_tasks_on_separate_ports_do_not_overwrite_reports(self):
        reports = files.NodeReports()
        first = files.ReceiveTask('one', 9, '127.0.0.1', '', 19100)
        second = files.ReceiveTask('two', 10, '127.0.0.1', '', 19101)
        reports.assign(first)
        reports.assign(second)
        self.assertTrue(reports.complete(first, '/tmp/one'))
        self.assertTrue(reports.complete(second, '/tmp/two'))
        sock = Mock()
        reports.send(sock, first.local, Mock())
        sent = [call.args[0] for call in sock.sendall.call_args_list]
        self.assertEqual(sent, [files.completion_report(first.local, 9, '/tmp/one'), files.READY,
                                files.completion_report(first.local, 10, '/tmp/two'), files.READY])

    def test_invalid_task_interface_port_and_sender(self):
        emit = Mock()
        self.assertIsNone(files.node_message(task_packet(19100, local='127.0.0.9')[4:],
                                             '127.0.0.1', '127.0.0.1', 9100, emit))
        self.assertEqual(emit.call_args.args[0], 'task_rejected')
        for raw in (task_packet(0), task_packet(19100, token=''), task_packet(19100, peer='239.1.2.3')):
            with self.assertRaises(ValueError):
                files.node_message(raw[4:], '127.0.0.1', '127.0.0.1', 9100, emit)

    def test_video_port_conflict_cleans_up_threads(self):
        with listener() as occupied:
            args = SimpleNamespace(local='127.0.0.1', teacher='127.0.0.1',
                udp_port=unused_port(socket.SOCK_DGRAM), http_port=occupied.getsockname()[1])
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(OSError):
                with video.service(args):
                    self.fail('An occupied port must fail at startup')
            self.assertFalse(any(t.name.startswith('video-') for t in threading.enumerate()))
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
                udp.bind(('0.0.0.0', args.udp_port))

    def test_silent_management_reconnects_after_video_startup_failure(self):
        with tempfile.TemporaryDirectory() as folder, listener() as management, listener() as node, listener() as occupied:
            stop, errors = threading.Event(), []
            args = SimpleNamespace(local='127.0.0.1', teacher='127.0.0.1',
                port=management.getsockname()[1], node_port=node.getsockname()[1],
                data_port=unused_port(), receive_dir=folder, mock_thumbnail=False,
                reconnect_delay=0.1, management_idle_timeout=0.1, with_video=True,
                udp_port=unused_port(socket.SOCK_DGRAM), http_port=occupied.getsockname()[1],
                mac='02:00:00:00:00:01')
            def run():
                try:
                    client.run(args, stop)
                except BaseException as error:
                    errors.append(error)
            worker = threading.Thread(target=run)
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()), contextlib.ExitStack() as stack:
                worker.start()
                try:
                    first = stack.enter_context(management.accept()[0])
                    first.settimeout(4)
                    self.assertEqual(struct.unpack_from('<I', files.read_frame(first, stop))[0], 6)
                    tasks = stack.enter_context(node.accept()[0])
                    tasks.settimeout(4)
                    self.assertEqual(files.read_frame(tasks, stop), struct.pack('<I', 6))
                    self.assertEqual(files.read_frame(tasks, stop), struct.pack('<I', 7))
                    # The first peer remains connected but sends no data.
                    second = stack.enter_context(management.accept()[0])
                    second.settimeout(4)
                    self.assertEqual(struct.unpack_from('<I', files.read_frame(second, stop))[0], 6)
                finally:
                    stop.set()
                    worker.join(7)
                self.assertFalse(worker.is_alive())
                self.assertEqual(errors, [])
            events = [json.loads(line) for line in next(Path(folder).rglob('events.jsonl')).read_text().splitlines()]
            names = [event['event'] for event in events]
            self.assertIn('video_unavailable', names)
            self.assertIn('management_retry', names)
            self.assertIn('node_ready', names)

    def test_dynamic_listener_bind_failure_and_idle_recycling(self):
        with tempfile.TemporaryDirectory() as folder, listener() as occupied:
            stop = threading.Event()
            args = SimpleNamespace(local='127.0.0.1', teacher='127.0.0.1', data_port=unused_port())
            reports, emit = files.NodeReports(), Mock()
            listeners = files.Listeners(args, Path(folder), stop, emit, reports)
            try:
                listeners.ensure(args.data_port)
                with self.assertRaises(OSError):
                    listeners.ensure(occupied.getsockname()[1])
                self.assertEqual(len(listeners.entries), 1)
                for _ in range(files.MAX_LISTENERS):
                    listeners.ensure(unused_port())
                self.assertEqual(len(listeners.entries), files.MAX_LISTENERS)
                self.assertIn(args.data_port, listeners.entries)
                self.assertTrue(any(call.args[0] == 'listener_retired' for call in emit.call_args_list))
            finally:
                stop.set()
                listeners.close()
            self.assertFalse(any(t.name.startswith('file-data-') for t in threading.enumerate()))
