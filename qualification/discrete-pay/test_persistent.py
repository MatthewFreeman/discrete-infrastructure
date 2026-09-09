"""Offline renderer/refusal tests; no host operations."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('persistent', Path(__file__).with_name('persistent-test.py'))
p = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {'pwd': types.ModuleType('pwd')} if sys.platform == 'win32' else {}):
    spec.loader.exec_module(p)


class PersistentTest(unittest.TestCase):
    def test_environment_literal_and_no_newline_injection(self):
        self.assertEqual(p.env_file({'DISCRETE_PAY_TOKEN': 'a"\\$%b'}), 'DISCRETE_PAY_TOKEN="a\\"\\\\$%b"\n')
        for values in ({'LD_PRELOAD': 'x'}, {'DISCRETE_PAY_TOKEN': 'x\nX=y'}, {'DISCRETE_PAY_TOKEN': 1}):
            with self.assertRaises(ValueError):
                p.env_file(values)

    def test_real_compiled_worker_and_loopback_confinement(self):
        release = Path('/opt/discrete-pay-test/releases/' + 'a' * 64)
        directory = p.PAY / 'build/native-ops/run-persistent-test1'
        value = p.unit('worker', release, directory)
        self.assertIn('/dist/apps/worker/src/main.js', value)
        self.assertNotIn('service-role.mjs', value)
        self.assertIn('IPAddressDeny=any\nIPAddressAllow=localhost', value)
        self.assertIn('ProtectSystem=strict', value)
        self.assertIn('EnvironmentFile=/opt/discrete-pay-test/env/worker', value)
        self.assertEqual(p.unit_name('worker'), 'discrete-pay-worker.service')

    def test_signer_unknown_role_and_path_injection_refused(self):
        release = Path('/opt/discrete-pay-test/releases/' + 'a' * 64)
        directory = p.PAY / 'build/native-ops/run-persistent-test1'
        for role in ('miner-sender', 'anything', 'worker\nExecStart=/bin/false'):
            with self.assertRaises(ValueError):
                p.unit(role, release, directory)
        for invalid in (Path('/tmp/x'), Path('/opt/discrete-pay-test/releases/x\nUser=root')):
            with self.assertRaises(ValueError):
                p.unit('worker', invalid, directory)
        with self.assertRaises(ValueError):
            p.unit('worker', release, Path('/tmp/run-persistent-x'))

    def test_tree_hash_detects_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            item = root / 'value'
            item.write_text('first')
            before = p.tree_hashes(root)
            item.write_text('second')
            self.assertNotEqual(before, p.tree_hashes(root))

    @unittest.skipIf(sys.platform == 'win32', 'POSIX symlink test')
    def test_symlink_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'link').symlink_to('/etc/passwd')
            with self.assertRaises(ValueError):
                p.tree_hashes(root)

    def test_changed_or_foreign_units_refuse_operation(self):
        with self.assertRaises(ValueError):
            p.validate_owned({'units': {'sshd.service': 'abc'}})

    def test_exact_runtime_acceptance_required_for_boot(self):
        state = {'release': '/opt/discrete-pay-test/releases/abc', 'units': {'worker': 'hash'}}
        evidence = {'result': 'PASS', 'bundle': 'abc', 'unitsActive': 1}
        p.require_acceptance(state, evidence)
        for change in ({'result': 'FAIL'}, {'bundle': 'other'}, {'unitsActive': 0}):
            with self.assertRaises(ValueError):
                p.require_acceptance(state, {**evidence, **change})


if __name__ == '__main__':
    unittest.main()
