import contextlib
import io
import unittest
from unittest.mock import patch

from oseasy_helper.cli import main


class CliTests(unittest.TestCase):
    def test_help_at_every_level(self):
        for args in (['-h'], ['video', '-h'], ['control', '-h']):
            with self.subTest(args=args), contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as result:
                main(args)
            self.assertEqual(result.exception.code, 0)

    def test_missing_addresses_fail_before_network_use(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as result:
            main(['video'])
        self.assertEqual(result.exception.code, 2)

    def test_video_does_not_require_a_group(self):
        with patch('oseasy_helper.cli.video.receive') as receive:
            code = main(['video', '--teacher', '203.0.113.10', '--local', '192.0.2.20'])
        self.assertEqual(code, 0)
        receive.assert_called_once()

    def test_reject_multicast_teacher_before_network_use(self):
        with patch('oseasy_helper.cli.video.receive') as receive, contextlib.redirect_stderr(io.StringIO()):
            code = main(['video', '--teacher', '239.255.0.1', '--local', '192.0.2.20'])
        self.assertEqual(code, 1)
        receive.assert_not_called()

    def test_invalid_port(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as result:
            main(['video', '--teacher', '203.0.113.10', '--local', '192.0.2.20', '--http-port', '65536'])
        self.assertEqual(result.exception.code, 2)


if __name__ == '__main__':
    unittest.main()
