"""Pinned PRIVATE Pay application upgrade/rollback qualification.

Changes only four existing Pay units and their release metadata. No node, wallet,
environment, firewall, SSH, payment, mining, schema migration or production action.
The old release, unit files, acceptance and coherent SQLite backups are retained.
Run under a root systemd supervisor with ExecStopPost invoking `recover`.
"""
import hashlib
from contextlib import closing
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time

ROOT = Path('/opt/discrete-pay-test')
QUAL = Path('/opt/discrete-pay-qualification')
SYSTEM = Path('/etc/systemd/system')
WORK = ROOT / 'upgrades/pay-94995a7'
CANDIDATE = QUAL / 'bundles/pay-94995a7-core-8703c16'
OLD_INSTALL = '6371fb9ba116c99221da4b789fdacc174382c14b8ddf0e26287c6f8e74776845'
INSTALLER = '86e8dde3822d3ebb92769b9c968f6f8b7aa6f1e677aed09310229291c6ad6067'
MANIFEST = '120f2b9478d4474d9cb27456aeb9b83d24febadaebdfb1ba887ba1e856f6f589'
PAY = '94995a7c8d7215d1261b79abb83ae7fdda181c58'
ROLES = ('facade', 'gateway', 'public', 'worker')


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1048576), b''): h.update(chunk)
    return h.hexdigest()


def call(args):
    return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT, timeout=90).strip()


def private_write(path, value, mode=0o600):
    descriptor, name = tempfile.mkstemp(prefix=path.name + '.pending-', dir=path.parent)
    temporary = Path(name)
    with os.fdopen(descriptor, 'w') as f:
        os.chmod(temporary, mode)
        f.write(value); f.flush(); os.fsync(f.fileno())
    temporary.replace(path)
    fd = os.open(path.parent, os.O_RDONLY)
    try: os.fsync(fd)
    finally: os.close(fd)


def save(plan):
    private_write(WORK / 'plan.json', json.dumps(plan, sort_keys=True, indent=2))


def installer():
    path = ROOT / 'persistent-test.py'
    if sha(path) != INSTALLER: raise ValueError('installed private helper changed')
    spec = importlib.util.spec_from_file_location('private_installer', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def replacement(text, old, new):
    for release in (old, new):
        if not re.fullmatch(r'/opt/discrete-pay-test/releases/[a-f0-9]{64}', release):
            raise ValueError('foreign release')
    if text.count(old) != 3 or 'service-role.mjs' in text:
        raise ValueError('not an exact Pay application unit')
    if 'User=payqual\n' not in text or 'IPAddressDeny=any\nIPAddressAllow=localhost\n' not in text:
        raise ValueError('private boundary missing')
    return text.replace(old, new)


def verify_candidate():
    if sha(CANDIDATE / 'manifest.json') != MANIFEST: raise ValueError('candidate manifest changed')
    manifest = json.loads((CANDIDATE / 'manifest.json').read_text())
    if manifest['payCommit'] != PAY: raise ValueError('candidate source changed')
    if {str(p.relative_to(CANDIDATE)) for p in CANDIDATE.rglob('*') if p.is_file()} != set(manifest['files']) | {'manifest.json'}:
        raise ValueError('unexpected candidate file')
    for name, digest in manifest['files'].items():
        path = CANDIDATE / name
        if path.is_symlink() or sha(path) != digest: raise ValueError('candidate file changed')
    for path, digest in (
        (QUAL / 'pay-merged-4d2f069/build/native-combined/run-2pRELJ/evidence.json',
         '90cdccb9968047d93de11bd70eb4b713c97b4a627dd8e0ee901be540ad0800d9'),
        (QUAL / 'bundle-validation-nyte9h8c/validation-evidence.json',
         '6550c9d4a4185349671f99832661c10c83a4ed5c4f656387a0eee161b2665623')):
        if sha(path) != digest: raise ValueError('prior exact candidate acceptance changed')


def financial_fingerprint(state):
    handoff = json.loads((Path(state['clone']) / 'service-handoff.json').read_text())
    path = Path(handoff['gatewayEnv']['DISCRETE_PAY_GATEWAY_DATABASE_PATH'])
    h = hashlib.sha256()
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as db:
        for query in (
            'SELECT id,deposit_t,deposit_account,amount_atomic,received_atomic,confirmed_atomic,observed_atomic,status,late,reorg_notice_pending FROM invoices ORDER BY id',
            'SELECT invoice_id,transaction_hash,deposit_account,amount_atomic,block_height,block_hash,canonical,mempool_active,confirmations FROM payments ORDER BY id',
            'SELECT height,block_hash,canonical FROM chain_blocks ORDER BY height,block_hash',
            'SELECT event_id,invoice_id,sequence,payload_sha256 FROM invoice_events ORDER BY event_id'):
            for row in db.execute(query): h.update(json.dumps(row, separators=(',', ':')).encode() + b'\n')
    h.update(json.dumps(json.loads((Path(state['clone']) / 'service-receipts.json').read_text()), sort_keys=True).encode())
    return h.hexdigest()


def probe(state):
    call(['runuser', '-u', 'payqual', '--', state['release'] + '/node',
          str(ROOT / 'persistent-probe.mjs'), state['clone'] + '/service-handoff.json', state['release'], 'replay'])


def verify_running(state, p, fingerprint):
    deadline = time.monotonic() + 75
    observed_after = int(time.time() * 1000)
    while True:
        try:
            p.validate_owned(state)
            for name in state['units']:
                if call(['systemctl', 'is-active', name]) != 'active': raise ValueError('unit inactive')
            for role in ROLES:
                name = p.unit_name(role)
                pid = call(['systemctl', 'show', name, '-p', 'MainPID', '--value'])
                if pid == '0' or os.readlink('/proc/' + pid + '/exe') != state['release'] + '/node':
                    raise ValueError('wrong running release')
            probe(state)
            if financial_fingerprint(state) != fingerprint: raise ValueError('payment/event/receipt state changed')
            snapshot = json.loads(Path('/run/discrete-pay-observer/snapshot.json').read_text())
            if (not snapshot['active'] or snapshot['at'] < observed_after
                    or not all((snapshot['samples'].get(k) or {}).get('code') == 'success'
                               and (snapshot['samples'].get(k) or {}).get('at', 0) >= observed_after
                               for k in ('scanner', 'webhook'))):
                raise ValueError('worker observation not successful')
            if call(['systemctl', 'is-enabled', p.TARGET]) != 'enabled': raise ValueError('test target boot policy changed')
            return
        except (ValueError, subprocess.SubprocessError, FileNotFoundError):
            if time.monotonic() >= deadline: raise
            time.sleep(1)


def prepare():
    p = installer()
    if WORK.exists(): raise ValueError('upgrade already prepared; inspect retained plan')
    if sha(ROOT / 'install.json') != OLD_INSTALL: raise ValueError('baseline install changed')
    old = json.loads((ROOT / 'install.json').read_text()); p.validate_owned(old)
    if old['phase'] != 'enabled': raise ValueError('not an enabled private baseline')
    if sha(ROOT / 'persistent-probe.mjs') != '34326f0c9fbdc659118816e886c6dbf636408582b1a007d0cce224755e7ab010':
        raise ValueError('private replay probe changed')
    verify_candidate()
    fingerprint = financial_fingerprint(old); verify_running(old, p, fingerprint)
    WORK.mkdir(parents=True, mode=0o700)
    for name in ('install.json', 'acceptance.json'):
        shutil.copyfile(ROOT / name, WORK / ('before-' + name)); (WORK / ('before-' + name)).chmod(0o600)
    staging = WORK / 'release'; staging.mkdir()
    shutil.copytree(CANDIDATE / 'pay/dist', staging / 'dist')
    shutil.copyfile(CANDIDATE / 'pay/package.json', staging / 'package.json')
    shutil.copyfile(CANDIDATE / 'bin/node', staging / 'node')
    shutil.copyfile(Path(old['release']) / 'service-role.mjs', staging / 'service-role.mjs')
    for path in [staging, *staging.rglob('*')]:
        path.chmod(0o755 if path.is_dir() or path.name == 'node' else 0o644)
    hashes = p.tree_hashes(staging)
    for name, digest in old['bundleFiles'].items():
        if name.endswith('.sql') or name == 'dist/src/persistence/schema-contract.js':
            if hashes.get(name) != digest: raise ValueError('schema changed; code-only rollback refused')
    identity = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    release = ROOT / 'releases' / identity
    if release.exists(): raise ValueError('candidate release already retained')
    staging.rename(release)
    new = json.loads(json.dumps(old)); new.update(release=str(release), bundleFiles=hashes, phase='upgrade-testing')
    # Native/receiver/edge units keep their old helper and Node. Verify those files too.
    for name, digest in old['bundleFiles'].items(): new['fixtureDependencies'][old['release'] + '/' + name] = digest
    units = {}
    for role in ROLES:
        name = p.unit_name(role); before = (SYSTEM / name).read_text()
        after = replacement(before, old['release'], str(release))
        units[name] = {'before': before, 'after': after}
        new['units'][name] = hashlib.sha256(after.encode()).hexdigest()
    accepted = json.loads(json.dumps(new)); accepted['phase'] = 'enabled'
    plan = {'old': old, 'new': new, 'acceptedState': accepted, 'units': units, 'fingerprint': fingerprint,
            'phase': 'prepared', 'recover': False, 'accepted': False}
    save(plan)
    print('PREPARED: isolated immutable release; live services unchanged', flush=True)


def check_switch_files(plan):
    for name, values in plan['units'].items():
        if name not in ('discrete-pay-test-facade.service', 'discrete-pay-test-gateway.service',
                        'discrete-pay-test-public.service', 'discrete-pay-worker.service'):
            raise ValueError('foreign unit in plan')
        if (SYSTEM / name).read_text() not in (values['before'], values['after']):
            raise ValueError('unit changed outside this upgrade')
    current = json.loads((ROOT / 'install.json').read_text())
    if current not in (plan['old'], plan['new'], plan['acceptedState']): raise ValueError('install changed outside this upgrade')
    for name, digest in plan['old']['units'].items():
        if name not in plan['units'] and sha(SYSTEM / name) != digest: raise ValueError('fixture unit changed')


def backup_databases(state):
    handoff = json.loads((Path(state['clone']) / 'service-handoff.json').read_text())
    # A failed attempt stays available for diagnosis; retries never overwrite it.
    attempt = Path(tempfile.mkdtemp(prefix='before-databases-', dir=WORK))
    result = {}
    for name, section, key in (
        ('gateway.sqlite3', 'gatewayEnv', 'DISCRETE_PAY_GATEWAY_DATABASE_PATH'),
        ('allocations.sqlite3', 'facadeEnv', 'DISCRETE_PAY_FACADE_JOURNAL_PATH')):
        source = Path(handoff[section][key]).resolve()
        if source.parent != Path(state['clone']).resolve(): raise ValueError('foreign database')
        destination = attempt / name
        with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as db, closing(sqlite3.connect(destination)) as target:
            db.backup(target)
            if target.execute('PRAGMA integrity_check').fetchone() != ('ok',): raise ValueError('backup integrity failed')
        destination.chmod(0o600); result[str(destination)] = sha(destination)
    return result


def activate():
    p = installer(); plan = json.loads((WORK / 'plan.json').read_text())
    if plan['accepted'] or plan['recover'] or plan['phase'] not in ('prepared', 'rolled-back'):
        raise ValueError('unexpected activation state')
    check_switch_files(plan); p.validate_owned(plan['old']); verify_candidate()
    plan['recover'] = True; plan['phase'] = 'switching'; save(plan)
    call(['systemctl', 'stop', *plan['units']])
    if 'backups' not in plan: plan['backups'] = backup_databases(plan['old']); save(plan)
    for name, values in plan['units'].items(): private_write(SYSTEM / name, values['after'], 0o644)
    private_write(ROOT / 'install.json', json.dumps(plan['new'], indent=2))
    call(['systemctl', 'daemon-reload']); call(['systemctl', 'start', *plan['units']])
    verify_running(plan['new'], p, plan['fingerprint'])
    plan['phase'] = 'candidate-verified'; save(plan)
    print('PASS: candidate running, prior payment/events/replay and all12units retained', flush=True)


def recover():
    if not (WORK / 'plan.json').exists(): return
    plan = json.loads((WORK / 'plan.json').read_text())
    if not plan['recover'] or plan['accepted']: return
    p = installer(); check_switch_files(plan)
    if p.tree_hashes(Path(plan['old']['release'])) != plan['old']['bundleFiles']: raise ValueError('rollback release changed')
    call(['systemctl', 'stop', *plan['units']])
    for name, values in plan['units'].items(): private_write(SYSTEM / name, values['before'], 0o644)
    private_write(ROOT / 'install.json', (WORK / 'before-install.json').read_text())
    private_write(ROOT / 'acceptance.json', (WORK / 'before-acceptance.json').read_text())
    call(['systemctl', 'daemon-reload']); call(['systemctl', 'start', *plan['units']])
    verify_running(plan['old'], p, plan['fingerprint'])
    if plan.get('trialFailureInjected') and plan['phase'] == 'candidate-verified':
        plan['rollbackVerified'] = True
    plan['phase'] = 'rolled-back'; plan['recover'] = False; save(plan)
    print('PASS: rollback restored old applications; no ledger/database restored or overwritten', flush=True)


def accept():
    p = installer(); plan = json.loads((WORK / 'plan.json').read_text())
    if (plan['phase'] != 'candidate-verified' or not plan['recover']
            or not plan.get('rollbackVerified')): raise ValueError('candidate or failed-trial rollback unverified')
    # Restart the real four services once more before accepting their boot release.
    before = {name: call(['systemctl', 'show', name, '-p', 'MainPID', '--value']) for name in plan['units']}
    call(['systemctl', 'restart', *plan['units']]); verify_running(plan['new'], p, plan['fingerprint'])
    for name, pid in before.items():
        if call(['systemctl', 'show', name, '-p', 'MainPID', '--value']) in ('0', pid):
            raise ValueError('application restart not observed')
    evidence = {'result': 'PASS', 'bundle': Path(plan['new']['release']).name, 'payCommit': PAY,
                'unitsActive': len(plan['new']['units']), 'scope': 'private existing test only; no production or new transfer',
                'checks': ['candidate activation and same invoice HTTP replay', 'real failed-trial ExecStopPost rollback',
                           'retry activation and four application restart', 'payment/event/receipt fingerprint unchanged',
                           'all12units active and actual worker observation successful']}
    private_write(ROOT / 'install.json', json.dumps(plan['acceptedState'], indent=2))
    private_write(ROOT / 'acceptance.json', json.dumps(evidence, indent=2))
    plan.update(accepted=True, recover=False, phase='accepted'); save(plan)
    print('ACCEPTED: new private Pay release; rollback artifacts retained', flush=True)


if __name__ == '__main__':
    if os.geteuid() != 0: raise ValueError('root supervisor required')
    import fcntl
    upgrade_lock = (ROOT / 'upgrade.lock').open('a')
    os.chmod(ROOT / 'upgrade.lock', 0o600)
    fcntl.flock(upgrade_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    action = sys.argv[1]
    if action == 'trial':
        prepare(); activate()
        plan = json.loads((WORK / 'plan.json').read_text())
        plan['trialFailureInjected'] = True; save(plan)
        print('EXPECTED: injected trial exit23; ExecStopPost must restore the old release', flush=True)
        sys.exit(23)
    elif action == 'recover': recover()
    elif action == 'activate':
        plan = json.loads((WORK / 'plan.json').read_text())
        if not plan.get('rollbackVerified') or plan['phase'] != 'rolled-back':
            raise ValueError('verified failed trial and rollback required')
        activate(); accept()
    else: raise ValueError('expected trial, recover or activate')
