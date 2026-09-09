import struct
import unittest

from oseasy_helper.client import login_packet, message, thumbnail_reply


class ClientTests(unittest.TestCase):
    def test_mock_thumbnail_only_answers_observed_request(self):
        jpeg = b'\xff\xd8test\xff\xd9'
        reply = thumbnail_reply(dict(command=89, kind=64), jpeg)
        self.assertEqual(struct.unpack_from('<IIIII', reply), (24, 43, 64, 0, 8))
        self.assertEqual(reply[20:], jpeg)
        self.assertIsNone(thumbnail_reply(dict(command=25, kind=64), jpeg))
        self.assertIsNone(thumbnail_reply(dict(command=89, kind=128), jpeg))

    def test_login_has_utf16_byte_length_and_management_header(self):
        packet = login_packet('PC', '同学', '02:00:00:00:00:01', '192.0.2.20',
                              '2026-01-01 09:00:00')
        length, command, kind, extra, size = struct.unpack_from('<IIIII', packet)
        self.assertEqual((length, command, kind, extra, size),
                         (len(packet) - 4, 6, 0, 0, len(packet) - 20))
        self.assertEqual(packet[20:].decode('utf-16-le'),
                         '/PC/同学/2026-01-01 09:00:00//1/0/0/02:00:00:00:00:01/192.0.2.20/')

    def test_commands_are_only_parsed(self):
        for command in (25, 89, 43, 0xffffffff):
            parsed = message(struct.pack('<IIII', command, 64, 0, 0))
            self.assertEqual(parsed['command'], command)
        with self.assertRaises(ValueError):
            message(struct.pack('<IIII', 6, 0, 0, 100))

    def test_reject_field_delimiter(self):
        with self.assertRaises(ValueError):
            login_packet('PC/other', 'user', 'mac', '192.0.2.20', 'now')
