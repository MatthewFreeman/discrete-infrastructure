"""Offline prerequisite and recovery gates; no host operations."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('sequence',Path(__file__).with_name('combined-sequence.py'))
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)

class SequenceTest(unittest.TestCase):
    def proof(self):return {'result':'PASS','target':100000,'payCommit':'4d2f06952e2a566df4e92e9ee82b9f38601e0427','walletdCommit':'8703c16fa40ffc8456e3d71696b6220b32b4d74a','checks':[
        {'check':name,'value':{'count':100000}} for name in ['native large registry merchant four-request burst','wallet and facade reopen preserves all issued invoices and original payment']]}
    def test_collected_unit_accepts_only_audited_evidence(self):
        value=dict(LoadState='not-found',ActiveState='inactive',ControlGroup='')
        self.assertTrue(p.prerequisite(value,self.proof(),p.COMPLETED_NATIVE_SHA))
        for digest in (None,'0'*64):
            with self.assertRaises(ValueError):p.prerequisite(value,self.proof(),digest)
        for change in ({'ActiveState':'active'},{'ControlGroup':'/remaining'}):
            with self.assertRaises(ValueError):p.prerequisite({**value,**change},self.proof(),p.COMPLETED_NATIVE_SHA)
        with self.assertRaises(ValueError):p.prerequisite(value,{**self.proof(),'result':'FAIL'},p.COMPLETED_NATIVE_SHA)
    def test_collected_file_hash_is_computed_not_assumed(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(p,'SOURCE',Path(tmp)),patch.object(p,'state',return_value=dict(LoadState='not-found',ActiveState='inactive',ControlGroup='')):
            (Path(tmp)/'evidence.json').write_text('{"result":"PASS"}')
            with self.assertRaises(ValueError):p.current_prerequisite()
    def clean(self):return dict(LoadState='loaded',ActiveState='inactive',Result='success',ExecMainStatus='0',ControlGroup='')
    def test_wait_does_not_accept_active_success_label(self):
        self.assertFalse(p.prerequisite({**self.clean(),'ActiveState':'active'}))
        self.assertTrue(p.prerequisite(self.clean()))
    def test_failed_missing_or_unclean_native_refused(self):
        for changes in ({'LoadState':'not-found'},{'Result':'timeout'},{'ExecMainStatus':'1'},{'ControlGroup':'/running'},{'ActiveState':'failed'}):
            with self.assertRaises(ValueError):p.prerequisite({**self.clean(),**changes})
    def test_exact_native_payment_and_reopen_proof_required(self):
        proof={'result':'PASS','target':100000,'payCommit':'4d2f06952e2a566df4e92e9ee82b9f38601e0427','walletdCommit':'8703c16fa40ffc8456e3d71696b6220b32b4d74a','checks':[
          {'check':name,'value':{'count':100000}} for name in ['native large registry merchant four-request burst','wallet and facade reopen preserves all issued invoices and original payment']]}
        self.assertTrue(p.prerequisite(self.clean(),proof))
        for changes in ({'result':'RUNNING'},{'target':10000},{'checks':[]},{'walletdCommit':'other'}):
            with self.assertRaises(ValueError):p.prerequisite(self.clean(),{**proof,**changes})
    def test_no_pause_marker_never_starts_stack(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(p,'HERE',Path(tmp)),patch.object(p,'call') as call:
            p.restore();call.assert_not_called()
            (Path(tmp)/'sequence-state.json').write_text('{"paused":false}')
            p.restore();call.assert_not_called()
    def test_changed_install_blocks_recovery_mutation(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(p,'HERE',Path(tmp)),patch.object(p,'validate_install',side_effect=ValueError('changed')),patch.object(p,'call') as call:
            (Path(tmp)/'sequence-state.json').write_text('{"paused":true,"installSha256":"expected"}')
            with self.assertRaises(ValueError):p.restore()
            call.assert_not_called()
    def test_recovery_only_exact_child_and_target(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(p,'HERE',Path(tmp)),patch.object(p,'validate_install'),patch.object(p,'state',return_value={'LoadState':'loaded'}),patch.object(p,'call') as call,patch.object(p,'save') as save:
            (Path(tmp)/'sequence-state.json').write_text('{"paused":true,"installSha256":"expected"}')
            p.restore()
            self.assertEqual([x.args[0] for x in call.call_args_list],[['systemctl','stop',p.CHILD],['systemctl','start',p.TARGET]])
            self.assertFalse(save.call_args.args[0]['paused'])
            self.assertTrue(save.call_args.args[0]['restored'])
    def test_failure_before_child_creation_still_restores_target(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(p,'HERE',Path(tmp)),patch.object(p,'validate_install'),patch.object(p,'state',return_value={'LoadState':'not-found'}),patch.object(p,'call') as call,patch.object(p,'save'):
            (Path(tmp)/'sequence-state.json').write_text('{"paused":true,"installSha256":"expected"}')
            p.restore();call.assert_called_once_with(['systemctl','start',p.TARGET])

if __name__=='__main__':unittest.main()
