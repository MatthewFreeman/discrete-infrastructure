"""Persistent PRIVATE-CHAIN qualification, never a public-network installer.

Clone a stopped, already-qualified fixture; leave its original and backups intact.
Run compiled Pay directly from a root-owned, hashed bundle. Fixture dependencies
remain explicit test helpers. No mining, payment, SSH, firewall or reboot action.
The test identity can read disposable fixture wallets: NOT a production custody
layout. Do not place real keys/funds in this tree.
"""
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import subprocess
import sys
import tempfile

QUAL = Path('/opt/discrete-pay-qualification')
PAY = QUAL / 'pay-merged-4d2f069'
ROOT = Path('/opt/discrete-pay-test')
SYSTEM = Path('/etc/systemd/system')
TARGET = 'discrete-pay-test.target'
STATE = ROOT / 'install.json'
APPS = {
    'facade': ('services/walletd-facade/src/main.js', 'facadeEnv'),
    'gateway': ('apps/gateway-api/src/main.js', 'gatewayEnv'),
    'public': ('apps/public-web/src/main.js', 'publicEnv'),
    'worker': ('apps/worker/src/main.js', 'workerEnv'),
}
NATIVE = {'node-a', 'node-b', 'node-c', 'node-d', 'merchant-tracking-restored'}


def call(args):
    return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT).strip()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_hashes(path):
    result = {}
    for item in sorted(path.rglob('*')):
        if item.is_symlink() or not (item.is_file() or item.is_dir()):
            raise ValueError('non-regular fixture object')
        if item.is_file():
            result[str(item.relative_to(path))] = digest(item)
    return result


def env_file(values):
    lines = []
    for key, value in sorted(values.items()):
        if not re.fullmatch(r'DISCRETE_PAY_[A-Z_]+', key):
            raise ValueError('unexpected environment key')
        if not isinstance(value, str) or any(c in value for c in '\r\n\x00'):
            raise ValueError('invalid environment value')
        lines.append(key + '="' + value.replace('\\', '\\\\').replace('"', '\\"') + '"')
    return '\n'.join(lines) + '\n'


def unit_name(role):
    if role not in set(APPS) | NATIVE | {'edge', 'receiver'}:
        raise ValueError('unexpected service role')
    return 'discrete-pay-worker.service' if role == 'worker' else 'discrete-pay-test-' + role + '.service'


def unit(role, release, directory):
    unit_name(role)
    if not re.fullmatch(r'/opt/discrete-pay-test/releases/[a-f0-9]{64}', release.as_posix()):
        raise ValueError('unexpected bundle path')
    if directory.parent != PAY / 'build/native-ops' or not re.fullmatch(r'run-persistent-[a-z0-9_]+', directory.name):
        raise ValueError('unexpected private test path')
    release = release.as_posix()
    directory = directory.as_posix()
    if role in APPS:
        launch = f'{release}/node {release}/dist/{APPS[role][0]}'
        environment = f'EnvironmentFile={ROOT.as_posix()}/env/{role}\n'
    else:
        launch = f'{release}/node {release}/service-role.mjs {directory}/service-handoff.json {role}'
        environment = 'Environment=DISCRETE_PAY_QUALIFICATION_MODE=paged\n'
    return f'''[Unit]
Description=Discrete Pay PRIVATE CHAIN test: {role} (not production)
PartOf={TARGET}
After=network.target
StartLimitIntervalSec=60
StartLimitBurst=10

[Service]
Type=exec
User=payqual
Group=payqual
WorkingDirectory={release}
{environment}ExecStart={launch}
Restart=on-failure
RestartSec=5
TimeoutStopSec=40
KillMode=control-group
UMask=0077
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
PrivateDevices=yes
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
RestrictSUIDSGID=yes
CapabilityBoundingSet=
RestrictAddressFamilies=AF_UNIX AF_INET
IPAddressDeny=any
IPAddressAllow=localhost
ReadWritePaths={directory}
TasksMax=64
MemoryMax=256M
StandardOutput=journal
StandardError=journal
'''


def validate_owned(state):
    names = {unit_name(r) for r in set(APPS) | NATIVE | {'edge', 'receiver'}} | {TARGET}
    if set(state['units']) != names:
        raise ValueError('unexpected installed unit set')
    for name, expected in state['units'].items():
        if digest(SYSTEM / name) != expected:
            raise ValueError('unit changed; refuse automatic operation')
    release = Path(state['release'])
    if release.parent != ROOT / 'releases' or tree_hashes(release) != state['bundleFiles']:
        raise ValueError('bundle changed; refuse automatic operation')
    for path, expected in state['fixtureDependencies'].items():
        if digest(Path(path)) != expected:
            raise ValueError('native test dependency changed')


def require_acceptance(state, evidence):
    if evidence.get('result') != 'PASS' or evidence.get('bundle') != Path(state['release']).name or evidence.get('unitsActive') != len(state['units']):
        raise ValueError('exact-bundle runtime acceptance required before boot enablement')


def install(file):
    if os.geteuid() != 0:
        raise ValueError('root required')
    file = file.resolve()
    directory = file.parent
    if directory.parent != PAY / 'build/native-ops' or not re.fullmatch(r'run-[a-z0-9]+', directory.name) or file.name != 'service-handoff.json':
        raise ValueError('expected exact previously qualified paged fixture')
    if ROOT.exists():
        raise ValueError('existing installation retained; inspect before replacing')
    for filename in ('paged-service-evidence.json', 'paged-reboot-evidence.json'):
        if json.loads((QUAL / filename).read_text())['result'] != 'PASS':
            raise ValueError('prior systemd/reboot qualification required')
    if subprocess.run(['pgrep', '-u', 'payqual'], stdout=subprocess.DEVNULL).returncode == 0:
        raise ValueError('fixture identity has running processes')
    original = tree_hashes(directory)
    handoff = json.loads(file.read_text())
    if handoff['dir'] != str(directory) or {p['name'] for p in handoff['processes']} != NATIVE | {'miner-sender'}:
        raise ValueError('unexpected qualified handoff')
    roles = sorted(set(APPS) | NATIVE | {'receiver', 'edge'})
    dependencies = {p['executable'] for p in handoff['processes']}
    dependencies.add(str(PAY / 'test/worker-runtime/tls-fixture.ts'))
    dependencies.add(str(QUAL / 'imports/paged-service-probe.mjs'))
    dependency_hashes = {path: digest(Path(path)) for path in sorted(dependencies)}
    for name in [unit_name(r) for r in roles] + [TARGET]:
        if (SYSTEM / name).exists() or call(['systemctl', 'show', name, '-p', 'LoadState', '--value']) != 'not-found':
            raise ValueError('conflicting unit exists')
    tree_hashes(PAY / 'dist')  # Reject links before a privileged copy follows them.
    for source in (PAY / 'package.json', QUAL / 'tools/node-v24.18.1-linux-x64/bin/node', QUAL / 'imports/paged-service-role.mjs'):
        if source.is_symlink() or not source.is_file():
            raise ValueError('non-regular bundle input')
    # No native miner/signer process is installed. Existing private-chain state
    # can be observed without mining or making any new transfer.
    ROOT.mkdir(mode=0o755)
    staging = ROOT / 'bundle-staging'
    staging.mkdir(mode=0o755)
    shutil.copytree(PAY / 'dist', staging / 'dist')
    shutil.copy2(PAY / 'package.json', staging / 'package.json')
    shutil.copy2(QUAL / 'tools/node-v24.18.1-linux-x64/bin/node', staging / 'node')
    shutil.copy2(QUAL / 'imports/paged-service-role.mjs', staging / 'service-role.mjs')
    for item in staging.rglob('*'):
        if item.is_symlink():
            raise ValueError('bundle symlink refused')
        item.chmod(0o755 if item.is_dir() or item.name == 'node' else 0o644)
    hashes = tree_hashes(staging)
    identity = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    release = ROOT / 'releases' / identity
    release.parent.mkdir(mode=0o755)
    staging.rename(release)
    clone = Path(tempfile.mkdtemp(prefix='run-persistent-', dir=directory.parent))
    shutil.copytree(directory, clone, dirs_exist_ok=True)
    # Paths change only in copies of textual fixture configuration, not wallets,
    # SQLite state, logs or original evidence.
    for path in clone.iterdir():
        if path.is_file() and path.suffix in ('.json', '.conf'):
            path.write_text(path.read_text().replace(str(directory), str(clone)))
    uid = pwd.getpwnam('payqual').pw_uid
    gid = pwd.getpwnam('payqual').pw_gid
    for item in [clone, *clone.rglob('*')]:
        os.chown(item, uid, gid)
        item.chmod(0o700 if item.is_dir() else 0o600)
    handoff = json.loads((clone / file.name).read_text())
    env = ROOT / 'env'
    env.mkdir(mode=0o700)
    for role, (_, key) in APPS.items():
        target = env / role
        target.write_text(env_file(handoff[key]))
        target.chmod(0o600)
    values = {unit_name(r): unit(r, release, clone) for r in roles}
    values[TARGET] = '[Unit]\nDescription=Discrete Pay persistent PRIVATE CHAIN qualification\nWants=' + ' '.join(values) + '\nAfter=network.target\n\n[Install]\nWantedBy=multi-user.target\n'
    state = {'scope': 'private chain only; no new payment or mining; not public release',
             'source': str(directory), 'sourceFiles': original, 'clone': str(clone),
             'release': str(release), 'bundleFiles': hashes, 'phase': 'prepared',
             'fixtureDependencies': dependency_hashes,
             'units': {k: hashlib.sha256(v.encode()).hexdigest() for k, v in values.items()}}
    STATE.write_text(json.dumps(state, indent=2)); STATE.chmod(0o600)
    for name, content in values.items():
        with (SYSTEM / name).open('x') as output:
            output.write(content)
        (SYSTEM / name).chmod(0o644)
    if tree_hashes(directory) != original:
        raise ValueError('original fixture changed')
    call(['systemd-analyze', 'verify', *[str(SYSTEM / n) for n in values]])
    call(['systemctl', 'daemon-reload'])
    validate_owned(state)
    call(['systemctl', 'start', TARGET])
    state['phase'] = 'started-not-enabled'
    STATE.write_text(json.dumps(state, indent=2))
    print('STARTED: independent cloned fixture; verify before boot enablement')


def main():
    action = sys.argv[1]
    if action == 'install':
        install(Path(sys.argv[2]))
        return
    state = json.loads(STATE.read_text())
    validate_owned(state)
    if action == 'enable':
        require_acceptance(state, json.loads((ROOT / 'acceptance.json').read_text()))
        for name in state['units']:
            call(['systemctl', 'is-active', name])
        if tree_hashes(Path(state['source'])) != state['sourceFiles']:
            raise ValueError('original fixture changed')
        call(['systemctl', 'enable', TARGET])
        state['phase'] = 'enabled'
        STATE.write_text(json.dumps(state, indent=2))
        print('ENABLED: exact private test target only')
    elif action == 'stop':
        call(['systemctl', 'disable', '--now', TARGET])
        call(['systemctl', 'stop', *[n for n in state['units'] if n != TARGET]])
        state['phase'] = 'stopped-data-retained'
        STATE.write_text(json.dumps(state, indent=2))
        print('STOPPED: exact owned units; bundle, clone and original retained')
    elif action == 'verify':
        if tree_hashes(Path(state['source'])) != state['sourceFiles']:
            raise ValueError('original fixture changed')
        print(json.dumps({'phase': state['phase'], 'bundle': Path(state['release']).name,
                          'originalUnchanged': True, 'units': len(state['units'])}))
    else:
        raise ValueError('expected install, verify, enable or stop')


if __name__ == '__main__':
    main()
