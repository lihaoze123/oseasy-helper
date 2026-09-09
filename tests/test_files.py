import hashlib
import socket
import struct
import tempfile
import threading
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from oseasy_helper import files


def packet(opcode, body=b''):
    payload = struct.pack('<I', opcode) + body
    return struct.pack('<I', len(payload)) + payload


def counted(raw):
    return struct.pack('<I', len(raw)) + raw


def header(name, size):
    return packet(0, struct.pack('<Q', size) + counted(name.encode('utf-8')))


class FileTests(unittest.TestCase):
    def test_completion_not_reused_after_disconnect_or_new_task(self):
        reports = files.NodeReports()
        reports.assign(('first', 0))
        first = reports.snapshot()
        reports.reset()
        self.assertFalse(reports.complete(first, self.root))
        reports.assign(('second', 0))
        second = reports.snapshot()
        self.assertFalse(reports.complete(first, self.root))
        self.assertTrue(reports.complete(second, self.root))
        reports.reset()
        sock = Mock()
        reports.send(sock, '127.0.0.1', self.emit)
        sock.sendall.assert_not_called()

    def test_failed_end_ack_does_not_report_success(self):
        sock = Mock()
        sock.recv.side_effect = [struct.pack('<I', 4), struct.pack('<I', 4)]
        sock.sendall.side_effect = OSError('Connection lost')
        self.assertFalse(files.receive_connection(sock, self.root, self.stop, self.emit))
        self.assertEqual(self.events[-1]['event'], 'data_error')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.events = []
        self.stop = threading.Event()

    def emit(self, event, **fields):
        self.events.append(dict(event=event, **fields))

    def connection(self):
        listener = socket.socket()
        listener.bind(('127.0.0.1', 0))
        listener.listen()
        sender = socket.create_connection(listener.getsockname(), timeout=2)
        receiver, _ = listener.accept()
        listener.close()
        def work():
            with receiver:
                files.receive_connection(receiver, self.root, self.stop, self.emit)
        thread = threading.Thread(target=work)
        thread.start()
        def cleanup():
            sender.close()
            self.stop.set()
            thread.join(3)
            self.assertFalse(thread.is_alive())
        self.addCleanup(cleanup)
        return sender, thread

    def ack(self, sender, expected):
        result = bytearray()
        while len(result) < 4:
            chunk = sender.recv(4 - len(result))
            self.assertTrue(chunk, 'Receiver closed before acknowledgement')
            result.extend(chunk)
        self.assertEqual(bytes(result), struct.pack('<I', expected))

    def test_loopback_files_directories_and_tail_chunk(self):
        sender, thread = self.connection()
        # A fragmented prefix and a Unicode Windows-style relative path.
        directory = packet(3, counted('课堂'.encode()))
        for byte in directory:
            sender.sendall(bytes([byte]))
        self.ack(sender, 1)
        data = b'hello\x00world\r\n'
        sender.sendall(header('课堂\\test.txt', len(data))
                       + packet(1, counted(data[:4])) + packet(2, counted(data[4:])))
        self.ack(sender, 1)
        sender.sendall(header('empty.txt', 0) + packet(2, counted(b'')))
        self.ack(sender, 1)
        sender.sendall(packet(4))
        self.ack(sender, 2)
        thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertEqual((self.root / '课堂/test.txt').read_bytes(), data)
        self.assertEqual((self.root / 'empty.txt').read_bytes(), b'')
        self.assertFalse(list(self.root.rglob('*.part')))
        saved = [e for e in self.events if e['event'] == 'file_saved']
        self.assertEqual(saved[0]['sha256'], hashlib.sha256(data).hexdigest())
        self.assertEqual(self.events[-1]['event'], 'transfer_complete')

    def test_size_mismatch_keeps_partial_and_does_not_ack(self):
        sender, thread = self.connection()
        sender.sendall(header('short.txt', 9) + packet(2, counted(b'bad')))
        self.assertEqual(sender.recv(4), b'')
        thread.join(2)
        self.assertEqual((self.root / 'short.txt.part').read_bytes(), b'bad')
        self.assertFalse((self.root / 'short.txt').exists())
        self.assertNotIn('file_saved', [e['event'] for e in self.events])

    def test_aborted_connection_keeps_partial(self):
        sender, thread = self.connection()
        sender.sendall(header('aborted.bin', 6) + packet(1, counted(b'123')))
        sender.shutdown(socket.SHUT_WR)
        self.assertEqual(sender.recv(4), b'')
        thread.join(2)
        self.assertEqual((self.root / 'aborted.bin.part').read_bytes(), b'123')
        self.assertEqual(self.events[-1]['event'], 'file_partial')

    def test_oversized_frame_rejected_before_body(self):
        sender, thread = self.connection()
        sender.sendall(struct.pack('<I', files.MAX_FRAME + 1))
        self.assertEqual(sender.recv(4), b'')
        thread.join(2)
        self.assertIn('Invalid frame length', self.events[-1]['error'])

    def test_invalid_paths(self):
        for name in ('../x', '/tmp/x', 'C:\\x', '\\\\server\\x', 'a/../../x',
                     'a:b', 'NUL.txt', 'COM1', 'dir/LPT².log', 'a.', 'a ', 'a\0b',
                     'a//b', './a', '', 'dir\\..\\x'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                files.safe_path(self.root, name.encode())

    def test_existing_link_cannot_redirect_writes(self):
        target = self.root / 'real'
        target.mkdir()
        link = self.root / 'link'
        try:
            link.symlink_to(target, target_is_directory=True)
        except OSError:
            self.skipTest('Creating symlinks is unavailable for this account')
        with self.assertRaises(ValueError):
            files.safe_path(self.root, b'link/file.txt')

    def test_no_overwrite_and_no_premature_success(self):
        (self.root / 'keep.txt').write_bytes(b'keep')
        transfer = files.Transfer(self.root, self.emit)
        with self.assertRaises(FileExistsError):
            transfer.handle(header('keep.txt', 1)[4:])
        self.assertEqual((self.root / 'keep.txt').read_bytes(), b'keep')
        transfer.handle(header('pending.txt', 3)[4:])
        with self.assertRaises(ValueError):
            transfer.handle(struct.pack('<I', 4))
        transfer.close()
        self.assertFalse(transfer.done)

    def test_bad_chunk_and_disk_budget(self):
        transfer = files.Transfer(self.root, self.emit)
        with self.assertRaises(ValueError):
            transfer.handle(header('huge', files.MAX_TRANSFER_BYTES + 1)[4:])
        transfer.handle(header('normal', 2)[4:])
        try:
            with self.assertRaises(ValueError):
                transfer.handle(packet(1, struct.pack('<I', 9) + b'x')[4:])
            with self.assertRaises(ValueError):
                transfer.handle(packet(2, counted(b'123'))[4:])
        finally:
            transfer.close()

    def test_node_handshake_receive_task_and_upload_ignored(self):
        with socket.socket() as server:
            server.bind(('127.0.0.1', 0))
            server.listen()
            server.settimeout(3)
            args = SimpleNamespace(local='127.0.0.1', teacher='127.0.0.1',
                                   node_port=server.getsockname()[1], data_port=19100)
            received = threading.Event()
            def emit(event, **fields):
                self.emit(event, **fields)
                if event == 'receive_task':
                    received.set()
            worker = threading.Thread(target=files.node_loop, args=(args, self.stop, emit))
            worker.start()
            try:
                conn, _ = server.accept()
                with conn:
                    conn.settimeout(0.5)
                    self.assertEqual(files.read_frame(conn, self.stop), struct.pack('<I', 6))
                    self.assertEqual(files.read_frame(conn, self.stop), struct.pack('<I', 7))
                    task = bytearray(0x4d0)
                    task[0x200:0x209] = b'127.0.0.1'
                    # Real tasks may name a teacher-internal sender node here;
                    # the TCP peer check remains the security boundary.
                    task[0x250:0x259] = b'127.0.0.2'
                    struct.pack_into('<H', task, 0x2a0, 19100)
                    task[0x2a2:0x2a6] = b'test'
                    conn.sendall(packet(2, task) + packet(3, task))
                    self.assertTrue(received.wait(3))
                    self.stop.set()
            finally:
                self.stop.set()
                worker.join(4)
            self.assertFalse(worker.is_alive())
            self.assertTrue(any(e['event'] == 'node_ready' for e in self.events))
            tasks = [e for e in self.events if e['event'] == 'receive_task']
            self.assertTrue(tasks[0]['matches_listener'])
            self.assertTrue(any(e['event'] == 'node_ignored' and e['opcode'] == 2 for e in self.events))


if __name__ == '__main__':
    unittest.main()
