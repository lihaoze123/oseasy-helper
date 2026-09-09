import contextlib
import io
from pathlib import Path
import socket
import struct
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from oseasy_helper import client, files


class IntegratedClientTests(unittest.TestCase):
    def test_login_receive_and_disconnect(self):
        with tempfile.TemporaryDirectory() as folder, socket.socket() as management, socket.socket() as node, socket.socket() as reserve:
            for server in (management, node, reserve):
                server.bind(('127.0.0.1', 0))
                server.listen()
                server.settimeout(4)
            data_port = reserve.getsockname()[1]
            reserve.close()
            args = SimpleNamespace(local='127.0.0.1', teacher='127.0.0.1',
                port=management.getsockname()[1], node_port=node.getsockname()[1],
                data_port=data_port, receive_dir=folder, mock_thumbnail=False)
            errors = []
            def run():
                try:
                    client.run(args)
                except BaseException as error:
                    errors.append(error)
            def frame(opcode, body=b''):
                payload = struct.pack('<I', opcode) + body
                return struct.pack('<I', len(payload)) + payload
            worker = threading.Thread(target=run)
            with patch('oseasy_helper.client.interface_mac', return_value='02:00:00:00:00:01'), contextlib.redirect_stdout(io.StringIO()):
                worker.start()
                try:
                    with management.accept()[0] as login, node.accept()[0] as tasks:
                        login.settimeout(2)
                        tasks.settimeout(2)
                        stop = threading.Event()
                        self.assertEqual(files.read_frame(login, stop)[:4], struct.pack('<I', 6))
                        self.assertEqual(files.read_frame(tasks, stop), struct.pack('<I', 6))
                        self.assertEqual(files.read_frame(tasks, stop), struct.pack('<I', 7))
                        task = bytearray(0x4d0)
                        task[0x200:0x209] = b'127.0.0.1'
                        struct.pack_into('<H', task, 0x2a0, data_port)
                        task[0x2a2:0x2a6] = b'test'
                        struct.pack_into('<I', task, 0x2c4, 9)
                        tasks.sendall(frame(3, task))
                        with socket.create_connection(('127.0.0.1', data_port), timeout=2) as sender:
                            name, content = b'example.txt', b'integrated transfer'
                            sender.sendall(frame(0, struct.pack('<QI', len(content), len(name)) + name)
                                + frame(2, struct.pack('<I', len(content)) + content))
                            self.assertEqual(sender.recv(4), struct.pack('<I', 1))
                            sender.sendall(frame(4))
                            self.assertEqual(sender.recv(4), struct.pack('<I', 2))
                        self.assertEqual(next(Path(folder).rglob('example.txt')).read_bytes(), content)
                        report = files.read_frame(tasks, stop)
                        self.assertEqual(struct.unpack_from('<II', report), (5, 3))
                        self.assertEqual(report[8:0x408], bytes(1024))
                        self.assertEqual(report[0x408:0x458], b'127.0.0.1' + bytes(71))
                        self.assertEqual(struct.unpack_from('<I', report, 0x458)[0], 9)
                        saved = next(Path(folder).rglob('example.txt')).parent
                        self.assertEqual(report[0x45c:].decode('utf-16le'), str(saved) + '\\\0')
                        self.assertEqual(files.read_frame(tasks, stop), struct.pack('<I', 7))
                finally:
                    worker.join(6)
                self.assertFalse(worker.is_alive())
                self.assertEqual(errors, [])
                self.assertFalse(any(t.name in ('file-node', 'file-data') for t in threading.enumerate()))
                with socket.socket() as check:
                    check.bind(('127.0.0.1', data_port))
