"""One bounded PRIVATE test sequence, not a monitor or production installer.

Wait for the already-running exact native100000 prerequisite without stopping it.
Only after clean success, pause the hash-validated private stack and run combined
qualification on a new copy. The saved pause marker supports ExecStopPost recovery.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT=Path('/opt/discrete-pay-qualification')
HERE=Path(__file__).resolve().parent
SOURCE=ROOT/'pay-merged-4d2f069/build/native-load/run-Dh58cq'
INSTALL=Path('/opt/discrete-pay-test/install.json')
INSTALLER=Path('/opt/discrete-pay-test/persistent-test.py')
NODE=ROOT/'tools/node-v24.18.1-linux-x64/bin/node'
TARGET='discrete-pay-test.target'
NATIVE='pay-qualification-native100k.service'
CHILD='pay-qualified-combined100k.service'
# Exact retained evidence audited with journal clean-exit readback on2026-09-10.
# A collected transient unit is NOT success without this immutable proof.
COMPLETED_NATIVE_SHA='450474e339e6ebeb91e0720c130cb567d0d0e60ca753a8dba34992364d862624'
PINS={
 'combined-native-journal.mjs':'b44a5caf3c9bb10ad5edd57693b452aba85ca53539a58535ab0401dceb7c82d2',
 'registry-prefix.mjs':'6dde39f0c487ebc59d29561c3f35b5a710c3a3735ff19e581c444b582dadbf66',
 'bounded-child.mjs':'148734e843ddb2d76962aa93c3f1e3b6d0397ed4f97a39d65393ebb64d2d62fc',
}

def sha(path):
    digest=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):digest.update(chunk)
    return digest.hexdigest()
def call(args):return subprocess.check_output(args,text=True,stderr=subprocess.STDOUT,timeout=180).strip()
def state(unit):return dict(line.split('=',1) for line in call(['systemctl','show',unit,'-p','LoadState,ActiveState,SubState,Result,ExecMainStatus,ControlGroup']).splitlines())

def prerequisite(value,proof=None,evidence_sha=None):
    collected=value.get('LoadState')=='not-found'
    if collected:
        if proof is None or evidence_sha!=COMPLETED_NATIVE_SHA or value.get('ActiveState')!='inactive' or value.get('ControlGroup'):
            raise ValueError('collected native prerequisite requires exact audited evidence')
    elif value.get('LoadState')!='loaded':raise ValueError('exact native prerequisite missing')
    if value.get('ActiveState') in ('active','activating','deactivating'):return False
    if not collected and (value.get('ActiveState')!='inactive' or value.get('Result')!='success' or value.get('ExecMainStatus')!='0' or value.get('ControlGroup')):
        raise ValueError('native prerequisite did not stop cleanly')
    if proof is None:return True
    if proof.get('result')!='PASS' or proof.get('target')!=100000 or proof.get('payCommit')!='4d2f06952e2a566df4e92e9ee82b9f38601e0427' or proof.get('walletdCommit')!='8703c16fa40ffc8456e3d71696b6220b32b4d74a':
        raise ValueError('native evidence does not match exact prerequisite')
    checks={c['check']:c['value'] for c in proof.get('checks',[])}
    for name in ('native large registry merchant four-request burst','wallet and facade reopen preserves all issued invoices and original payment'):
        if checks.get(name,{}).get('count')!=100000:raise ValueError('native final interaction evidence missing')
    return True

def current_prerequisite():
    value=state(NATIVE)
    if value.get('LoadState')!='not-found':return prerequisite(value)
    raw=(SOURCE/'evidence.json').read_bytes()
    return prerequisite(value,json.loads(raw),hashlib.sha256(raw).hexdigest())

def save(value):
    temporary=HERE/'sequence-state.pending'
    with temporary.open('w') as f:
        os.chmod(temporary,0o600);json.dump(value,f,indent=2);f.flush();os.fsync(f.fileno())
    temporary.replace(HERE/'sequence-state.json')
    fd=os.open(HERE,os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)

def validate_install(expected=None):
    if sha(INSTALLER)!='86e8dde3822d3ebb92769b9c968f6f8b7aa6f1e677aed09310229291c6ad6067':raise ValueError('private installer changed')
    if expected is not None and sha(INSTALL)!=expected:raise ValueError('private installation changed')
    call(['/usr/bin/python3','-B',str(INSTALLER),'verify'])
    return json.loads(INSTALL.read_text())

def restore():
    marker=HERE/'sequence-state.json'
    if not marker.exists():return
    saved=json.loads(marker.read_text())
    if not saved.get('paused'):return
    validate_install(saved['installSha256'])
    if state(CHILD).get('LoadState')!='not-found':call(['systemctl','stop',CHILD])
    call(['systemctl','start',TARGET])
    saved['paused']=False;saved['restored']=True;save(saved)
    print('RESTORED: exact private test target; readback acceptance remains required',flush=True)

def run():
    if os.geteuid()!=0:raise ValueError('root supervisor required')
    if (HERE/'sequence-state.json').exists():raise ValueError('existing sequence retained; do not rerun blindly')
    for name,digest in PINS.items():
        if sha(HERE/name)!=digest:raise ValueError('combined helper changed')
    if sha(ROOT/'imports/paged-native-load-100k.mjs')!='1fdae2c85e01d92a7c3761ede7d49a4dec155575ea501059ee4519fb18ad3c1f':raise ValueError('native helper changed')
    if sha(NODE)!='f3432a45b03b2da0d270095fdd8813dc34cbea73f5fc8b18c7a384b7cf9b333a':raise ValueError('Node changed')
    if state(CHILD).get('LoadState')!='not-found':raise ValueError('combined unit already exists')
    saved={'phase':'waiting-native','paused':False,'source':str(SOURCE),'scope':'copied private test sequence, no production'};save(saved)
    print('WAITING: exact native100000; no test services changed',flush=True)
    deadline=time.monotonic()+10800
    while not current_prerequisite():
        if time.monotonic()>deadline:raise TimeoutError('native wait deadline; prerequisite left untouched')
        time.sleep(15)
    raw=(SOURCE/'evidence.json').read_bytes();evidence_sha=hashlib.sha256(raw).hexdigest()
    if not prerequisite(state(NATIVE),json.loads(raw),evidence_sha):raise ValueError('native prerequisite became active again')
    saved.update(phase='waiting-gui',nativeEvidenceSha256=evidence_sha);save(saved)
    deadline=time.monotonic()+2100
    while state('pay-gui-uri-7344fbd1.service').get('ActiveState') not in ('inactive','failed'):
        if time.monotonic()>deadline:raise TimeoutError('GUI wait deadline; private stack left untouched')
        time.sleep(15)
    installed=validate_install()
    if state(TARGET).get('ActiveState')!='active':raise ValueError('native automatic stack restoration missing')
    saved.update(phase='combined-preparing',paused=True,installSha256=sha(INSTALL),nativeEvidenceSha256=evidence_sha);save(saved)
    try:
        call(['systemctl','stop',TARGET])
        call(['systemctl','stop',*[n for n in installed['units'] if n!=TARGET]])
        if subprocess.run(['pgrep','-u','payqual'],stdout=subprocess.DEVNULL).returncode!=1:raise ValueError('unexpected test processes remain')
        saved['phase']='combined-running';save(saved)
        command=['systemd-run','--wait','--pipe','--unit='+CHILD,
          '--property=User=payqual','--property=Group=payqual','--property=UMask=0077',
          '--property=MemoryMax=700M','--property=MemorySwapMax=1G','--property=RuntimeMaxSec=10800','--property=TimeoutStopSec=60',
          '--property=PrivateTmp=yes','--property=IPAddressDeny=any','--property=IPAddressAllow=localhost',
          '--property=ProtectSystem=strict','--property=ProtectHome=yes',
          '--property=ReadWritePaths='+str(ROOT/'pay-merged-4d2f069/build/native-combined'),
          '--property=ExecStopPost=+/usr/bin/systemctl start '+TARGET,
          '--setenv=DISCRETE_PAY_COMBINED=copied-private-chain-full-journal',
          '--setenv=DISCRETE_PAY_COMBINED_COUNT=100000',
          '--setenv=DISCRETE_PAY_COMBINED_SOURCE='+str(SOURCE/'state'),
          '--setenv=DISCRETE_PAY_COMBINED_SOURCE_SHA256='+evidence_sha,str(NODE),str(HERE/'combined-native-journal.mjs')]
        with (HERE/'combined-output.log').open('x') as output:
            os.chmod(HERE/'combined-output.log',0o600)
            result=subprocess.run(command,stdout=output,stderr=subprocess.STDOUT,timeout=11000)
        if result.returncode!=0:raise ValueError('combined test failed; inspect retained private evidence')
        matches=re.findall(r'^Evidence: (/opt/discrete-pay-qualification/pay-merged-4d2f069/build/native-combined/run-[A-Za-z0-9_-]+/evidence.json)$',(HERE/'combined-output.log').read_text(),re.M)
        if len(matches)!=1:raise ValueError('exact combined evidence missing')
        evidence=Path(matches[0]);data=json.loads(evidence.read_text())
        if data.get('result')!='PASS':raise ValueError('combined evidence failed')
        saved.update(phase='combined-passed',combinedEvidence=str(evidence),combinedEvidenceSha256=sha(evidence));save(saved)
        print('PASS: combined private100000; evidence='+str(evidence),flush=True)
    finally:restore()

if __name__=='__main__':
    if sys.argv[1:]==['restore']:restore()
    elif sys.argv[1:]==['run']:run()
    else:raise ValueError('expected run or restore')
