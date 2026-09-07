"""Root orchestration of disposable, loopback-only systemd units; no production paths."""
import hashlib
import json
from pathlib import Path
import pwd
import subprocess
import sys
import tarfile
import time

ROOT = Path('/opt/discrete-pay-qualification')
PAY = ROOT / 'pay'
NODE = ROOT / 'tools/node-v24.18.1-linux-x64/bin/node'
file = Path(sys.argv[1]).resolve()
directory = file.parent
assert directory.parent == PAY / 'build/native-test' and directory.name.startswith('run-')
assert file.name == 'service-handoff.json'
handoff = json.loads(file.read_text())
assert handoff['dir'] == str(directory)
native = [p['name'] for p in handoff['processes']]
assert set(native) <= {'node-a','node-b','node-c','node-d','miner-sender','merchant-tracking-restored'}
assert {'node-a','node-b','miner-sender','merchant-tracking-restored'} <= set(native)
roles = native + ['receiver','facade','gateway','public','worker']
units = ['payqual-'+r+'.service' for r in roles]
assert all(subprocess.run(['systemctl','is-active','--quiet',u]).returncode != 0 for u in units)
evidence = {'scope':'disposable native Linux systemd qualification; no public domain or production funds','checks':[]}

def call(args, capture=False):
    return subprocess.check_output(args, text=True) if capture else subprocess.run(args, check=True)

def record(name):
    evidence['checks'].append(name)
    print('PASS:', name, flush=True)

def start(role):
    call(['systemd-run','--quiet','--unit=payqual-'+role,'--property=User=payqual','--property=Group=payqual',
          '--property=Type=exec','--property=Restart=on-failure','--property=RestartSec=1',
          '--property=TimeoutStopSec=40','--property=KillMode=control-group','--property=UMask=0077',
          '--property=NoNewPrivileges=yes','--property=ProtectSystem=strict','--property=ProtectHome=yes',
          '--property=PrivateTmp=yes','--property=CapabilityBoundingSet=',
          '--property=RestrictAddressFamilies=AF_UNIX AF_INET','--property=IPAddressDeny=any',
          '--property=IPAddressAllow=localhost','--property=ReadWritePaths='+str(directory),
          '--working-directory='+str(PAY),str(NODE),str(ROOT/'imports/service-role.mjs'),str(file),role])

def probe(action):
    call(['runuser','-u','payqual','--',str(NODE),str(ROOT/'imports/service-probe.mjs'),str(file),action])

def records():
    text = call(['journalctl','-u','payqual-worker.service','-o','cat','--no-pager'], True)
    return [json.loads(line) for line in text.splitlines() if line.startswith('{"event":"worker_cycle"')]

def wait(fn, timeout=40):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        if fn(): return
        time.sleep(.5)
    raise RuntimeError('bounded service condition timed out')

try:
    for role in roles: start(role)
    probe('baseline')
    wait(lambda:any(r['component']=='scanner' and r['code']=='success' for r in records()))
    record('native persisted payment, tracking mode, registry1000 and invoice replay through independent systemd apps')
    successes = sum(r['component']=='scanner' and r['code']=='success' for r in records())
    call(['systemctl','stop','payqual-merchant-tracking-restored.service'])
    wait(lambda:any(r['component']=='scanner' and r['code']=='rpc_unavailable' for r in records()))
    probe('outage')
    record('tracking outage visible in journal; checkpoint, confirmed payment and event count retained')
    start('merchant-tracking-restored')
    wait(lambda:sum(r['component']=='scanner' and r['code']=='success' for r in records())>successes)
    probe('baseline')
    record('tracking recovery visible in journal; same identity and payment retained')
    flag=directory/'receiver-reject'
    flag.touch(mode=0o600)
    uid=pwd.getpwnam('payqual').pw_uid
    import os
    os.chown(flag,uid,pwd.getpwnam('payqual').pw_gid)
    probe('pay')
    record('new signed native test payment detected and confirmed as exact overpayment; HTTPS receiver503')
    oldpid=call(['systemctl','show','payqual-worker.service','--property=MainPID','--value'],True).strip()
    call(['systemctl','kill','--kill-whom=main','--signal=SIGKILL','payqual-worker.service'])
    wait(lambda:(lambda p:p not in ('0',oldpid))(call(['systemctl','show','payqual-worker.service','--property=MainPID','--value'],True).strip()))
    flag.unlink()
    probe('retry')
    assert int(call(['systemctl','show','payqual-worker.service','--property=NRestarts','--value'],True))>=1
    record('systemd restarted killed worker; durable HTTPS retry has identical payload and ID with valid HMAC')
    probe('snapshot')
    record('online SQLite backup integrity and invoice/checkpoint readback')
    call(['systemctl','stop',*reversed(units)])
    backup=ROOT/'backups'/('systemd-'+directory.name+'.tar.gz')
    backup.parent.mkdir(mode=0o700,exist_ok=True)
    assert not backup.exists()
    call(['tar','-czf',str(backup),'-C',str(directory.parent),directory.name])
    digest=hashlib.sha256(backup.read_bytes()).hexdigest()
    with tarfile.open(backup) as tar:
        for member in tar.getmembers():
            parts=Path(member.name).parts
            assert parts[0]==directory.name and '..' not in parts and not Path(member.name).is_absolute()
            assert member.isfile() or member.isdir(), 'unexpected archive object'
    preserved=directory.with_name(directory.name+'.pre-restore')
    assert not preserved.exists()
    directory.rename(preserved)
    assert hashlib.sha256(backup.read_bytes()).hexdigest()==digest
    call(['tar','-xzf',str(backup),'-C',str(directory.parent)])
    for role in roles: start(role)
    probe('restored')
    record('cold full-state backup restored to original paths with original retained; wallet, invoice, events and registry replay preserved')
    evidence.update(result='PASS',backupSha256=digest,backup=str(backup),preservedOriginal=str(preserved))
except Exception as error:
    evidence.update(result='FAIL',error=str(error))
    raise
finally:
    subprocess.run(['systemctl','stop',*reversed(units)],check=False)
    (ROOT/'service-evidence.json').write_text(json.dumps(evidence,indent=2))
    print('Secret-free service evidence:',ROOT/'service-evidence.json',flush=True)
