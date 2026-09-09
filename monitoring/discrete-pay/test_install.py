"""Pure installer regressions; imports do not mutate the host."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('pay_install', Path(__file__).with_name('install.py'))
# pwd/grp are POSIX-only; the policy suite covers both Windows and Linux.
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class AllowedUsersTests(unittest.TestCase):
    def test_separate_openssh_output_lines(self):
        self.assertEqual(module.allowed_users('allowusers payobserver\nallowusers serveradmin\n'),
                         {'payobserver', 'serveradmin'})

    def test_one_line_multiple_values(self):
        self.assertEqual(module.allowed_users('allowusers serveradmin payobserver\npasswordauthentication no\n'),
                         {'payobserver', 'serveradmin'})

    def test_unrelated_or_unexpected_user_not_ignored(self):
        self.assertEqual(module.allowed_users('denyusers stranger\n'), set())
        self.assertNotEqual(module.allowed_users('allowusers serveradmin payobserver stranger\n'),
                            {'payobserver', 'serveradmin'})


if __name__ == '__main__':
    unittest.main()
