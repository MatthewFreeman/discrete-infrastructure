"""Offline upgrade refusal, partial switch and acceptance gates; no VPS calls."""
import importlib.util
from contextlib import closing
import json
from pathlib import Path
import sys
import tempfile
import sqlite3
import unittest
from unittest.mock import patch, Mock

spec = importlib.util.spec_from_file_location('upgrade', Path(__file__).with_name('persistent-upgrade.py'))
u = importlib.util.module_from_spec(spec); spec.loader.exec_module(u)


class UpgradeTest(unittest.TestCase):
    old = '/opt/discrete-pay-test/releases/' + 'a' * 64
    new = '/opt/discrete-pay-test/releases/' + 'b' * 64

    def unit(self):
        return ('User=payqual\nIPAddressDeny=any\nIPAddressAllow=localhost\nWorkingDirectory=' + self.old
                + '\nExecStart=' + self.old + '/node ' + self.old + '/dist/apps/worker/src/main.js\n')

    def test_only_three_pinned_release_occurrences_change(self):
        self.assertEqual(u.replacement(self.unit(), self.old, self.new), self.unit().replace(self.old, self.new))
        for text in (self.unit().replace('User=payqual', 'User=root'), self.unit() + self.old,
                     self.unit().replace('/dist/apps/worker/src/main.js', '/service-role.mjs')):
            with self.assertRaises(ValueError): u.replacement(text, self.old, self.new)
        for path in ('/tmp/release', self.new + '\nExecStart=/bin/false'):
            with self.assertRaises(ValueError): u.replacement(self.unit(), self.old, path)

    def fixture(self, root):
        system = root / 'system'; system.mkdir()
        work = root / 'work'; work.mkdir()
        names = ['discrete-pay-test-facade.service', 'discrete-pay-test-gateway.service',
                 'discrete-pay-test-public.service', 'discrete-pay-worker.service']
        units = {name: {'before': 'old-' + name, 'after': 'new-' + name} for name in names}
        old = {'release': self.old, 'phase': 'enabled', 'units': {}, 'bundleFiles': {}}
        new = {**old, 'release': self.new, 'phase': 'upgrade-testing'}
        accepted = {**new, 'phase': 'enabled'}
        plan = {'old': old, 'new': new, 'acceptedState': accepted, 'units': units,
                'recover': True, 'accepted': False, 'phase': 'switching', 'fingerprint': 'fixed'}
        for i, (name, value) in enumerate(units.items()):
            (system / name).write_text(value['after' if i % 2 else 'before'])
        (root / 'install.json').write_text(json.dumps(old))
        (work / 'before-install.json').write_text(json.dumps(old))
        (work / 'before-acceptance.json').write_text('{"result":"PASS"}')
        (work / 'plan.json').write_text(json.dumps(plan))
        return system, work, plan

    def test_partial_unit_switch_and_partial_acceptance_are_recoverable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); system, work, plan = self.fixture(root)
            with patch.object(u, 'ROOT', root), patch.object(u, 'SYSTEM', system):
                for state in (plan['old'], plan['new'], plan['acceptedState']):
                    (root / 'install.json').write_text(json.dumps(state)); u.check_switch_files(plan)
                (root / 'install.json').write_text('{"release":"foreign"}')
                with self.assertRaises(ValueError): u.check_switch_files(plan)

    def test_unrelated_unit_edit_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); system, work, plan = self.fixture(root)
            (system / 'discrete-pay-worker.service').write_text('user edit')
            with patch.object(u, 'ROOT', root), patch.object(u, 'SYSTEM', system):
                with self.assertRaises(ValueError): u.check_switch_files(plan)

    def test_no_plan_or_accepted_plan_never_stops_services(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(u, 'WORK', Path(tmp)), patch.object(u, 'call') as call:
            u.recover(); call.assert_not_called()
            (Path(tmp) / 'plan.json').write_text('{"recover":false,"accepted":true}')
            u.recover(); call.assert_not_called()

    def test_recovery_restores_four_units_and_metadata_not_databases(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); system, work, plan = self.fixture(root)
            writes = []
            def write(path, value, mode=0o600): writes.append(path); path.write_text(value)
            p = Mock(); p.tree_hashes.return_value = {}
            with patch.object(u, 'ROOT', root), patch.object(u, 'SYSTEM', system), patch.object(u, 'WORK', work), \
                 patch.object(u, 'installer', return_value=p), patch.object(u, 'call') as call, \
                 patch.object(u, 'private_write', side_effect=write), patch.object(u, 'verify_running') as verify:
                u.recover()
                self.assertEqual(call.call_args_list[0].args[0], ['systemctl', 'stop', *plan['units']])
                verify.assert_called_once_with(plan['old'], p, 'fixed')
                self.assertEqual(json.loads((work / 'plan.json').read_text())['phase'], 'rolled-back')
                self.assertFalse(any(path.suffix == '.sqlite3' for path in writes))

    def test_failed_running_check_never_marks_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); system, work, plan = self.fixture(root)
            plan.update(phase='candidate-verified', rollbackVerified=True)
            (work / 'plan.json').write_text(json.dumps(plan))
            with patch.object(u, 'WORK', work), patch.object(u, 'installer'), patch.object(u, 'call'), \
                 patch.object(u, 'verify_running', side_effect=ValueError('failed')), patch.object(u, 'private_write') as write:
                with self.assertRaises(ValueError): u.accept()
                write.assert_not_called()

    def test_missing_failed_trial_refuses_acceptance_before_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); system, work, plan = self.fixture(root)
            plan['phase'] = 'candidate-verified'; (work / 'plan.json').write_text(json.dumps(plan))
            with patch.object(u, 'WORK', work), patch.object(u, 'installer'), patch.object(u, 'call') as call:
                with self.assertRaisesRegex(ValueError, 'rollback unverified'): u.accept()
                call.assert_not_called()

    def test_changed_old_release_refuses_recovery_before_service_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); system, work, plan = self.fixture(root)
            p = Mock(); p.tree_hashes.return_value = {'foreign': 'file'}
            with patch.object(u, 'ROOT', root), patch.object(u, 'SYSTEM', system), patch.object(u, 'WORK', work), \
                 patch.object(u, 'installer', return_value=p), patch.object(u, 'call') as call:
                with self.assertRaisesRegex(ValueError, 'rollback release changed'): u.recover()
                call.assert_not_called()

    def test_partial_backup_failure_retains_files_and_allows_new_attempt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); clone = root / 'clone'; clone.mkdir(); work = root / 'work'; work.mkdir()
            gateway = clone / 'gateway.sqlite3'; journal = clone / 'journal.sqlite3'
            with closing(sqlite3.connect(gateway)) as db: db.execute('CREATE TABLE retained(value)')
            handoff = {'gatewayEnv': {'DISCRETE_PAY_GATEWAY_DATABASE_PATH': str(gateway)},
                       'facadeEnv': {'DISCRETE_PAY_FACADE_JOURNAL_PATH': str(journal)}}
            (clone / 'service-handoff.json').write_text(json.dumps(handoff))
            with patch.object(u, 'WORK', work):
                with self.assertRaises(sqlite3.OperationalError): u.backup_databases({'clone': str(clone)})
                retained = next(work.glob('*/gateway.sqlite3')); digest = u.sha(retained)
                with closing(sqlite3.connect(journal)) as db: db.execute('CREATE TABLE retained(value)')
                result = u.backup_databases({'clone': str(clone)})
                self.assertEqual(len(result), 2); self.assertEqual(u.sha(retained), digest)
                self.assertNotIn(str(retained), result)

    @unittest.skipIf(sys.platform == 'win32', 'Linux directory fsync contract')
    def test_abandoned_temporary_write_does_not_block_recovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); path = root / 'install.json'
            (root / 'install.json.pending-abandoned').write_text('partial')
            u.private_write(path, 'restored'); self.assertEqual(path.read_text(), 'restored')
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)


if __name__ == '__main__': unittest.main()
