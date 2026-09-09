import unittest

import psutil

from oseasy_helper import control


class FakeProcess:
    def __init__(self, pid, name, exe, status=psutil.STATUS_RUNNING):
        self.pid = pid
        self._name = name
        self._exe = exe
        self._status = status
        self.info = {"pid": pid, "name": name, "exe": exe, "status": status}
        self.suspend_calls = 0
        self.resume_calls = 0

    def name(self):
        return self._name

    def exe(self):
        return self._exe

    def status(self):
        return self._status

    def suspend(self):
        self.suspend_calls += 1
        self._status = psutil.STATUS_STOPPED

    def resume(self):
        self.resume_calls += 1
        self._status = psutil.STATUS_RUNNING


class ControlTests(unittest.TestCase):
    def test_suspend_and_resume_follow_main_client_names(self):
        root = r"C:\Program Files\OsEasy"
        student = FakeProcess(10, "Student.exe", root + r"\Student.exe")
        newer = FakeProcess(11, "MmcStudent.exe", root + r"\MmcStudent.exe",
                            psutil.STATUS_STOPPED)
        other_install = FakeProcess(12, "MultiClient.exe", r"D:\Other\MultiClient.exe")
        unrelated = FakeProcess(13, "notepad.exe", root + r"\notepad.exe")
        processes = [student, newer, other_install, unrelated]

        result = control._change_suspension("suspend", root, lambda attrs: processes)
        self.assertEqual(student.suspend_calls, 1)
        self.assertEqual(newer.suspend_calls, 0)
        self.assertEqual(other_install.suspend_calls, 0)
        self.assertIn("already suspended", result[1])

        result = control._change_suspension("resume", root, lambda attrs: processes)
        self.assertEqual(student.resume_calls, 1)
        self.assertEqual(newer.resume_calls, 1)
        self.assertEqual(other_install.resume_calls, 0)
        self.assertTrue(all("resumed" in line for line in result))

    def test_no_matching_process_is_an_error(self):
        with self.assertRaisesRegex(RuntimeError, "No running Student.exe"):
            control._change_suspension(
                "suspend", r"C:\OsEasy",
                lambda attrs: [FakeProcess(1, "Student.exe", r"C:\Elsewhere\Student.exe")])

    def test_path_check_does_not_accept_prefix_sibling(self):
        self.assertTrue(control._under_root(r"C:\OsEasy\Student.exe", r"C:\OsEasy"))
        self.assertFalse(control._under_root(r"C:\OsEasy-Other\Student.exe", r"C:\OsEasy"))


if __name__ == "__main__":
    unittest.main()
