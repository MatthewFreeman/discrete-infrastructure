"""Prepare independent PRIVATE inputs for the ordinary app installer. No live fixture writes."""
from contextlib import closing
import importlib.util
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import pwd
import shutil
import socket
import sqlite3
import subprocess
import sys
import tarfile

ROOT=Path('/opt/discrete-pay-inputs')
NATIVE=Path('/opt/discrete-pay-tracking-test')
APP=Path('/opt/discrete-pay')
QUAL=Path('/opt/discrete-pay-qualification')
BUNDLE=ROOT/'bundle'


def copy_bundle():
    archive=QUAL/'bundles/pay-94995a7-core-8703c16.tar.gz'
    assert not archive.is_symlink()
    local=ROOT/'candidate.tar.gz'
    if not local.exists():shutil.copyfile(archive,local);local.chmod(0o600)
    assert not local.is_symlink() and local.stat().st_uid==0
    assert hashlib.sha256(local.read_bytes()).hexdigest()=='a6f5e00970f037678c7b3d8b0452d1e95f6c175531d6520d52c65a5f336d92ec'
    BUNDLE.mkdir(mode=0o755,exist_ok=True)
    assert not BUNDLE.is_symlink() and BUNDLE.stat().st_uid==0
    with tarfile.open(local) as bundle:
        seen=set()
        for item in bundle.getmembers():
            p=PurePosixPath(item.name)
            assert p.as_posix()==item.name and item.name not in seen and p.parts and not p.is_absolute() and '..' not in p.parts and (item.isfile() or item.isdir())
            seen.add(item.name)
        # Portable across the host's older Python: copy regular payloads only,
        # never archive ownership, links, devices or privileged mode bits.
        for item in bundle.getmembers():
            target=BUNDLE/item.name
            if item.isdir():target.mkdir(mode=0o755,parents=True,exist_ok=True)
            else:
                target.parent.mkdir(mode=0o755,parents=True,exist_ok=True)
                value=bundle.extractfile(item).read()
                if target.exists():assert not target.is_symlink() and target.read_bytes()==value
                else:
                    with target.open('xb') as f:f.write(value)
                target.chmod(0o755 if PurePosixPath(item.name).parent.as_posix()=='bin' else 0o644)
    print('PASS: hash-pinned archive extracted under a root-controlled input directory')


def prepare():
    assert os.geteuid()==0 and not ROOT.exists() and not NATIVE.exists() and not APP.exists()
    installed=json.loads(Path('/opt/discrete-pay-test/install.json').read_text())
    source=Path(installed['source'])
    assert source==QUAL/'pay-merged-4d2f069/build/native-ops/run-refv70x9'
    actual={p.relative_to(source).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in source.rglob('*') if p.is_file()}
    assert actual==installed['sourceFiles']
    for port in (17880,17881,17882,19540,19443):
        with socket.socket() as s:s.bind(('127.0.0.1',port))
    h=json.loads((source/'service-handoff.json').read_text())
    process=next(p for p in h['processes'] if p['name']=='merchant-tracking-restored')
    assert process['args'][0]=='--config' and process['args'][2:]==['--testnet']
    config=Path(process['args'][1]);assert config.parent==source
    values=dict(line.split('=',1) for line in config.read_text().splitlines() if '=' in line)
    wallet=Path(values['container-file']);assert wallet.parent==source
    ROOT.mkdir(mode=0o700);copy_bundle();NATIVE.mkdir(mode=0o700)
    shutil.copyfile(wallet,NATIVE/'tracking.wallet')
    values.update({'container-file':str(NATIVE/'tracking.wallet'),'bind-address':'127.0.0.1','bind-port':'19540','log-file':str(NATIVE/'wallet.log')})
    (NATIVE/'wallet.conf').write_text(''.join(k+'='+v+'\n' for k,v in values.items()))
    identity=pwd.getpwnam('payqual')
    for p in [NATIVE,*NATIVE.iterdir()]:os.chown(p,identity.pw_uid,identity.pw_gid);p.chmod(0o700 if p.is_dir() else 0o600)
    # Copy the stopped inputs first; SQLite must never create SHM beside the original.
    for section,key,name in [('gatewayEnv','DISCRETE_PAY_GATEWAY_DATABASE_PATH','gateway.sqlite3'),('facadeEnv','DISCRETE_PAY_FACADE_JOURNAL_PATH','allocations.sqlite3')]:
        old=Path(h[section][key]);assert old.parent==source
        raw=ROOT/('raw-'+name)
        for suffix in ('','-wal','-shm'):
            p=Path(str(old)+suffix)
            if p.exists():shutil.copyfile(p,Path(str(raw)+suffix))
        with closing(sqlite3.connect(str(raw))) as db, closing(sqlite3.connect(str(ROOT/name))) as dest:db.backup(dest)
        (ROOT/name).chmod(0o600)
    # Isolate copied legacy receivers. Their financial records remain intact.
    with sqlite3.connect(ROOT/'gateway.sqlite3') as db:db.execute('UPDATE webhook_endpoints SET active=0')
    worker=json.loads(Path(h['workerEnv']['DISCRETE_PAY_WORKER_CONFIG_PATH']).read_text())
    keyring=json.loads(Path(worker['webhookKeyringPath']).read_text())
    ca=Path(worker['webhookCaPath']).read_text()
    private=str(APP/'private');env={r:dict(h[r+'Env']) for r in ('facade','gateway','public','worker')}
    for r,prefix,port in [('facade','DISCRETE_PAY_FACADE',17881),('gateway','DISCRETE_PAY_GATEWAY',17880),('public','DISCRETE_PAY_PUBLIC_WEB',17882)]:
        env[r].update({prefix+'_LISTEN_HOST':'127.0.0.1',prefix+'_LISTEN_PORT':str(port)})
    env['facade'].update(DISCRETE_PAY_FACADE_JOURNAL_PATH=private+'/allocations.sqlite3',DISCRETE_PAY_WALLETD_ENDPOINT='http://127.0.0.1:19540/json_rpc')
    env['gateway'].update(DISCRETE_PAY_GATEWAY_DATABASE_PATH=private+'/gateway.sqlite3',DISCRETE_PAY_GATEWAY_FACADE_ENDPOINT='http://127.0.0.1:17881/v1/deposits',DISCRETE_PAY_GATEWAY_RATE_LIMIT_PER_MINUTE='120')
    env['public'].update(DISCRETE_PAY_PUBLIC_WEB_DATABASE_PATH=private+'/gateway.sqlite3',DISCRETE_PAY_PUBLIC_WEB_RATE_LIMIT_PER_MINUTE='120')
    env['worker']['DISCRETE_PAY_WORKER_CONFIG_PATH']=private+'/worker.json'
    worker.update(databasePath=private+'/gateway.sqlite3',walletEndpoint='http://127.0.0.1:19540/json_rpc',webhookKeyringPath=private+'/keyring.json',
                  webhookCaPath=private+'/ca.pem',webhookDestinations=[{'url':'https://merchant.test:19443/webhook','address':'127.0.0.1'}])
    request={'bundlePath':str(BUNDLE),'environments':env,'worker':worker,'keyring':keyring,'caPem':ca,
             'databaseSnapshot':str(ROOT/'gateway.sqlite3'),'journalSnapshot':str(ROOT/'allocations.sqlite3')}
    (ROOT/'request.json').write_text(json.dumps(request));(ROOT/'request.json').chmod(0o600)
    info={'invoiceId':h['invoiceId'],'publicToken':h['publicToken'],'merchantToken':h['merchantToken'],
          'sourceFiles':actual,'source':str(source),'keyId':next(iter(keyring)),
          'certificate':(source/'edge-cert.pem').read_text(),'certificateKey':(source/'edge-key.pem').read_text()}
    (ROOT/'qualification-private.json').write_text(json.dumps(info));(ROOT/'qualification-private.json').chmod(0o600)
    assert actual=={p.relative_to(source).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in source.rglob('*') if p.is_file()}
    print('PREPARED: independent tracking-only wallet and coherent copied SQL; original fixture unchanged')


if __name__=='__main__':
    if sys.argv[1:]==['bundle']:
        # Resume the first qualification's input-only ownership refusal.
        assert ROOT.exists() and NATIVE.exists() and not APP.exists()
        copy_bundle();file=ROOT/'request.json';value=json.loads(file.read_text())
        assert value['bundlePath']==str(QUAL/'bundles/pay-94995a7-core-8703c16')
        shutil.copyfile(file,ROOT/'request-before-bundle.json');(ROOT/'request-before-bundle.json').chmod(0o600)
        value['bundlePath']=str(BUNDLE);file.write_text(json.dumps(value));file.chmod(0o600)
    else:prepare()
