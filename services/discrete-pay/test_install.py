"""No network/service mutations. Synthetic configuration and filesystem refusal tests."""
import copy
import importlib.util
import json
from pathlib import Path, PurePosixPath
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('app_install',Path(__file__).with_name('install.py'))
u=importlib.util.module_from_spec(spec);spec.loader.exec_module(u)


def request():
    private='/opt/discrete-pay/private'
    e={r:{key:'unused' for key in keys} for r,keys in u.ENV.items()}
    for r,prefix in u.PREFIX.items():
        e[r].update({prefix+'_ENABLED':'true',prefix+'_LISTEN_HOST':'127.0.0.1',prefix+'_LISTEN_PORT':str(17080+list(u.PREFIX).index(r))})
    e['facade'].update(DISCRETE_PAY_FACADE_JOURNAL_PATH=private+'/allocations.sqlite3',DISCRETE_PAY_FACADE_BEARER_TOKEN='a'*32,
        DISCRETE_PAY_FACADE_REGISTRY_MODE='paged-v1',DISCRETE_PAY_WALLETD_ENDPOINT='http://127.0.0.1:19340/json_rpc',
        DISCRETE_PAY_WALLETD_USERNAME='test',DISCRETE_PAY_WALLETD_PASSWORD='b'*32)
    e['gateway'].update(DISCRETE_PAY_GATEWAY_DATABASE_PATH=private+'/gateway.sqlite3',DISCRETE_PAY_GATEWAY_NETWORK='xds-testnet',
        DISCRETE_PAY_GATEWAY_FACADE_ENDPOINT='http://127.0.0.1:17080/v1/deposits',DISCRETE_PAY_GATEWAY_FACADE_BEARER_TOKEN='a'*32,
        DISCRETE_PAY_GATEWAY_DETECTION_GRACE_SECONDS='60',DISCRETE_PAY_GATEWAY_RATE_LIMIT_PER_MINUTE='120')
    e['public'].update(DISCRETE_PAY_PUBLIC_WEB_DATABASE_PATH=private+'/gateway.sqlite3',
        DISCRETE_PAY_PUBLIC_WEB_BRIDGE_BASE_URL='https://merchant.test/pay/#',DISCRETE_PAY_PUBLIC_WEB_RATE_LIMIT_PER_MINUTE='120')
    e['worker']={'DISCRETE_PAY_WORKER_ENABLED':'true','DISCRETE_PAY_WORKER_CONFIG_PATH':private+'/worker.json'}
    w={'databasePath':private+'/gateway.sqlite3','walletEndpoint':'http://127.0.0.1:19340/json_rpc','walletUsername':'test','walletPassword':'b'*32,
       'nodeEndpoint':'http://127.0.0.1:19339/json_rpc','accountNumber':'1-1-TEST-0','genesisHash':'a'*64,'network':'xds-testnet',
       'startHeight':0,'maxReorgDepth':30,'intervalMs':1000,'webhookDestinations':[{'url':'https://merchant.test/webhook','address':'127.0.0.1'}],
       'webhookKeyringPath':private+'/keyring.json'}
    return {'bundlePath':'/opt/approved-bundle','environments':e,'worker':w,'keyring':{'test':'c'*64},'caPem':None,
            'databaseSnapshot':None,'journalSnapshot':None}


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.root=patch.object(u,'ROOT',PurePosixPath('/opt/discrete-pay'));self.root.start();self.addCleanup(self.root.stop)

    def test_valid_cross_component_configuration(self):
        self.assertEqual(u.config(request()),([17080,17081,17082],['127.0.0.1']))

    def test_environment_escape_and_injection_refusals(self):
        r=request();e=r['environments']['facade'];e['DISCRETE_PAY_WALLETD_PASSWORD']='quote"slash\\percent%'
        text=u.env_text('facade',e);self.assertIn('quote\\"slash\\\\percent%',text)
        for value in ('x\nExecStart=foreign','x\r','x\0',''):
            e['DISCRETE_PAY_WALLETD_PASSWORD']=value
            with self.assertRaises(ValueError):u.env_text('facade',e)
        e['DISCRETE_PAY_WALLETD_PASSWORD']='safe';e['NODE_OPTIONS']='--import=evil'
        with self.assertRaises(ValueError):u.env_text('facade',e)

    def test_nonloopback_and_ambiguous_rpc_refused(self):
        for value in ('http://localhost:19340/json_rpc','http://192.0.2.1:19340/json_rpc','http://127.0.0.1:19340/json_rpc?x',
                      'http://user@127.0.0.1:19340/json_rpc','http://127.0.0.1:08080/json_rpc','https://127.0.0.1:19340/json_rpc'):
            with self.assertRaises(ValueError):u.loopback(value,'/json_rpc')

    def test_binding_mismatches_refused(self):
        for section,key,value in [('worker','walletPassword','changed'),('worker','databasePath','/tmp/foreign'),('worker','network','foreign'),
                                  ('gateway','DISCRETE_PAY_GATEWAY_FACADE_BEARER_TOKEN','changed'),('facade','DISCRETE_PAY_FACADE_JOURNAL_PATH','/tmp/foreign')]:
            r=request();(r['worker'] if section=='worker' else r['environments'][section])[key]=value
            with self.assertRaises(ValueError):u.config(r)

    def test_listener_collision_and_public_bind_refused(self):
        for key,value in [('DISCRETE_PAY_GATEWAY_LISTEN_HOST','0.0.0.0'),('DISCRETE_PAY_GATEWAY_LISTEN_PORT','17080'),
                          ('DISCRETE_PAY_GATEWAY_LISTEN_PORT','22'),('DISCRETE_PAY_GATEWAY_ENABLED','false')]:
            r=request();r['environments']['gateway'][key]=value
            with self.assertRaises(ValueError):u.config(r)

    def test_worker_limits_and_trust_refused(self):
        for key,value in [('startHeight',True),('intervalMs',99),('maxReorgDepth',1001),('genesisHash','bad')]:
            r=request();r['worker'][key]=value
            with self.assertRaises(ValueError):u.config(r)
        for address in ('::1','0.0.0.0','224.0.0.1','127.0.0.1\nIPAddressAllow=any'):
            r=request();r['worker']['webhookDestinations'][0]['address']=address
            with self.assertRaises(ValueError):u.config(r)

    def test_seed_pair_and_keyring_required(self):
        r=request();r['databaseSnapshot']='/root/snapshot.sqlite3'
        with self.assertRaises(ValueError):u.config(r)
        r=request();r['keyring']={}
        with self.assertRaises(ValueError):u.config(r)
        r=request();r['worker']['webhookCaPath']='/tmp/ca.pem'
        with self.assertRaises(ValueError):u.config(r)

    def test_unit_has_only_compiled_application_entrypoint(self):
        release=PurePosixPath('/opt/discrete-pay/releases/'+'a'*64)
        for role in u.APPS:
            text=u.unit(role,release,['192.0.2.7'])
            self.assertIn('User=discretepay\n',text);self.assertIn('NoNewPrivileges=yes',text)
            self.assertIn('IPAddressDeny=any',text);self.assertIn('/pay/dist/'+u.APPS[role],text)
            self.assertEqual('192.0.2.7' in text,role=='worker')
            self.assertNotIn('qualification',text);self.assertNotIn('service-role',text);self.assertNotIn('walletd ',text)
        with self.assertRaises(ValueError):u.unit('miner',release,[])
        with self.assertRaises(ValueError):u.unit('worker',PurePosixPath('/tmp/code'),[])

    def test_foreign_install_refused_before_file_reads(self):
        with self.assertRaises(ValueError):u.verify({'root':'/foreign','payCommit':u.PAY})

    @unittest.skipIf(os.name=='nt','POSIX mode contract')
    def test_backup_includes_committed_wal_and_retains_existing_destination(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp);source=d/'source.sqlite3';target=d/'backup.sqlite3'
            writer=sqlite3.connect(source)
            try:
                writer.execute('PRAGMA journal_mode=WAL');writer.execute('PRAGMA wal_autocheckpoint=0')
                writer.execute('CREATE TABLE retained(value)');writer.execute('INSERT INTO retained VALUES (12346)');writer.commit()
                self.assertTrue(Path(str(source)+'-wal').exists())
                expected=u.database_backup(source,target)
                reader=sqlite3.connect(target)
                try:self.assertEqual(reader.execute('SELECT value FROM retained').fetchall(),[(12346,)])
                finally:reader.close()
                with self.assertRaises(ValueError):u.database_backup(source,target)
                self.assertEqual(u.digest(target),expected)
            finally:writer.close()

    @unittest.skipIf(os.name=='nt','POSIX file ownership/mode contract')
    def test_partial_unit_publish_can_retry_but_not_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'unit';u.write_once(p,b'original',0o644);u.write_once(p,b'original',0o644)
            with self.assertRaises(ValueError):u.write_once(p,b'replacement',0o644)
            self.assertEqual(p.read_bytes(),b'original')

    @unittest.skipIf(os.name=='nt','POSIX file ownership/mode contract')
    def test_symlink_hardlink_and_weak_private_input_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp);p=d/'input';p.write_text('{}');p.chmod(0o644)
            with self.assertRaises(ValueError):u.regular(p,True)
            symlink=d/'link';symlink.symlink_to(p)
            with self.assertRaises(ValueError):u.regular(symlink)
            hard=d/'hard';os.link(p,hard)
            with self.assertRaises(ValueError):u.regular(p)


if __name__=='__main__':unittest.main()
