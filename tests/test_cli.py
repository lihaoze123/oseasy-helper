import contextlib
import io
import unittest
from unittest.mock import patch

from oseasy_helper.cli import main


class CliTests(unittest.TestCase):
    def test_help_at_every_level(self):
        for args in (['-h'], ['video', '-h'], ['client', '-h'], ['student', '-h'], ['control', '-h']):
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

    def test_client_includes_file_parameters_without_control(self):
        with patch('oseasy_helper.cli.client.run') as receive, patch('oseasy_helper.cli.control.run') as control:
            code = main(['client', '--teacher', '203.0.113.10', '--local', '192.0.2.20'])
        self.assertEqual(code, 0)
        self.assertEqual(receive.call_args.args[0].data_port, 9100)
        self.assertEqual(receive.call_args.args[0].node_port, 8555)
        self.assertTrue(receive.call_args.args[0].mock_thumbnail)
        self.assertFalse(receive.call_args.args[0].with_video)
        control.assert_not_called()

    def test_student_defaults_and_identity_overrides(self):
        with patch('oseasy_helper.cli.client.run') as run:
            code = main(['student', '--teacher', '203.0.113.10', '--local', '192.0.2.20',
                         '--name', 'CLASS-PC', '--user', '学生', '--mac', '02-00-00-00-00-01'])
        self.assertEqual(code, 0)
        args = run.call_args.args[0]
        self.assertTrue(args.with_video)
        self.assertTrue(args.mock_thumbnail)
        self.assertEqual((args.name, args.user, args.mac), ('CLASS-PC', '学生', '02:00:00:00:00:01'))

    def test_student_opt_out_and_invalid_retry(self):
        with patch('oseasy_helper.cli.client.run') as run:
            self.assertEqual(main(['student', '--teacher', '203.0.113.10', '--local', '192.0.2.20',
                                   '--no-video', '--no-mock-thumbnail', '--once']), 0)
        args = run.call_args.args[0]
        self.assertFalse(args.with_video)
        self.assertFalse(args.mock_thumbnail)
        self.assertTrue(args.once)
        for option, value in (('--reconnect-delay', 'nan'), ('--reconnect-delay', '0'), ('--mac', 'bad')):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                main(['student', '--teacher', '203.0.113.10', '--local', '192.0.2.20', option, value])


if __name__ == '__main__':
    unittest.main()
