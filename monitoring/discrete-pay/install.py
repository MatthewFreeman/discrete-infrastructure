"""First-install only. Root reads a bounded JSON payload from stdin; no secrets logged.

Two explicit roles, no generic command, path, user, unit or runtime parameters.
Existing installs require a separate reviewed upgrade/rollback operation.
"""
import base64
import grp
import ipaddress
import json
import os
from pathlib import Path
import pwd
import re
import subprocess
import sys
import shutil
import hashlib


def allowed_users(effective):
    return {user for line in effective.splitlines() if line.startswith('allowusers ')
            for user in line.split()[1:]}


def run(*args):
    return subprocess.run(args, check=True, text=True, capture_output=True, timeout=30).stdout.strip()


def new_file(path, data, mode=0o644, group=0):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    with os.fdopen(fd, 'wb') as target:
        target.write(data)
        target.flush()
        os.fsync(target.fileno())
    os.chown(path, 0, group)


def main():
    assert os.geteuid() == 0
    raw = sys.stdin.buffer.read(131073)
    assert len(raw) <= 131072
    data = json.loads(raw)
    role = data['role']
    assert role in ('monitor', 'observer')
    resume = data.get('resume', False)
    assert isinstance(resume, bool) and (not resume or role == 'observer')
    release = data['release']
    assert re.fullmatch('[a-f0-9]{40}', release)
    files = ({'monitor.mjs', 'policy.mjs', 'discrete-pay-monitor.service'} if role == 'monitor' else
             {'collect.mjs', 'snapshot.mjs', 'policy.mjs', 'discrete-pay-observer-collect.service', 'discrete-pay-observer-collect.timer'})
    assert set(data['assets']) == files
    assets = {name: base64.b64decode(value, validate=True) for name, value in data['assets'].items()}
    assert all(len(value) <= 32768 for value in assets.values())
    account = 'paymonitor' if role == 'monitor' else 'payobserver'
    base = Path('/opt/discrete-pay-monitor' if role == 'monitor' else '/opt/discrete-pay-observer')
    home = Path('/var/lib/discrete-pay-monitor' if role == 'monitor' else '/var/lib/discrete-pay-observer')
    runtime = ('/usr/local/bin/node' if role == 'monitor' else
               '/opt/discrete-pay-qualification/tools/node-v24.18.1-linux-x64/bin/node')
    assert run(runtime, '--version').startswith(('v22.', 'v24.'))
    if not resume:
        assert not base.exists() and not home.exists()
    try:
        pwd.getpwnam(account)
    except KeyError:
        pass
    else:
        if not resume:
            raise ValueError('account already exists')
    if resume:
        identity = pwd.getpwnam(account)
        assert identity.pw_shell == '/bin/sh' and identity.pw_dir == str(home)
        assert home.stat().st_uid == 0 and (base / 'current').resolve() == base / 'releases' / release
        for name, content in assets.items():
            saved = base / 'releases' / release / name
            assert saved.stat().st_uid == 0 and saved.read_bytes() == content
        assert not (home / '.ssh/authorized_keys').exists()
    units = [name for name in files if name.endswith(('.service', '.timer'))]
    if resume:
        assert all(Path('/etc/systemd/system', name).read_bytes() == assets[name] for name in units)
    else:
        assert all(not Path('/etc/systemd/system', name).exists() for name in units)
    if role == 'observer':
        assert set(data) == {'role', 'release', 'assets', 'publicKey', 'sourceIp'} | ({'resume'} if resume else set())
        assert re.fullmatch(r'ssh-ed25519 [A-Za-z0-9+/=]+(?: [A-Za-z0-9._-]+)?', data['publicKey'])
        ipaddress.IPv4Address(data['sourceIp'])
        assert not Path('/etc/ssh/sshd_config.d/05-discrete-pay-observer.conf').exists()
        before_ssh = run('/usr/sbin/sshd', '-T')
        assert 'allowusers serveradmin\n' in before_ssh + '\n'
        assert 'passwordauthentication no\n' in before_ssh + '\n'
    else:
        assert set(data) == {'role', 'release', 'assets'}
        assert not Path('/etc/discrete-pay-monitor').exists()
    if not resume:
        run('/usr/sbin/useradd', '--system', '--no-create-home', '--home-dir', str(home),
            '--shell', '/usr/sbin/nologin' if role == 'monitor' else '/bin/sh', account)
    identity = pwd.getpwnam(account)
    if not resume:
        home.mkdir(mode=0o700 if role == 'monitor' else 0o755)
    if role == 'monitor':
        os.chown(home, identity.pw_uid, identity.pw_gid)
    destination = base / 'releases' / release
    if not resume:
        destination.mkdir(parents=True, mode=0o755)
        for name, content in assets.items():
            new_file(destination / name, content)
        (base / 'current').symlink_to(destination)
        for name in units:
            new_file(Path('/etc/systemd/system', name), assets[name])
    if role == 'observer':
        public_runtime = base / 'runtime' / 'node'
        if not public_runtime.exists():
            public_runtime.parent.mkdir(mode=0o755)
            shutil.copyfile(runtime, public_runtime)
            os.chmod(public_runtime, 0o755)
        assert public_runtime.stat().st_uid == 0
        with open(runtime, 'rb') as original, public_runtime.open('rb') as installed:
            assert hashlib.file_digest(original, 'sha256').digest() == hashlib.file_digest(installed, 'sha256').digest()
    run('/usr/bin/systemd-analyze', 'verify', *(str(Path('/etc/systemd/system', name)) for name in units))
    if role == 'monitor':
        config = Path('/etc/discrete-pay-monitor')
        config.mkdir(mode=0o750)
        os.chown(config, 0, identity.pw_gid)
        run('/usr/bin/ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-C', 'pay-observer', '-f', str(config / 'observer-key'))
        os.chown(config / 'observer-key', 0, identity.pw_gid)
        os.chmod(config / 'observer-key', 0o640)
        # Public key only. Never print the corresponding private key or config.
        public = (config / 'observer-key.pub').read_text().strip()
        run('/usr/bin/systemctl', 'daemon-reload')
        print(json.dumps({'installed': 'monitor', 'enabled': False, 'publicKey': public}))
    else:
        sshdir = home / '.ssh'
        if not resume:
            sshdir.mkdir(mode=0o755)
        forced = '/opt/discrete-pay-observer/runtime/node /opt/discrete-pay-observer/current/snapshot.mjs'
        line = f'from="{data["sourceIp"]}",restrict,command="{forced}" {data["publicKey"]}\n'
        new_file(sshdir / 'authorized_keys', line.encode())
        dropin = Path('/etc/ssh/sshd_config.d/05-discrete-pay-observer.conf')
        new_file(dropin, b'AllowUsers payobserver\n')
        try:
            run('/usr/sbin/sshd', '-t')
            effective = run('/usr/sbin/sshd', '-T')
            assert allowed_users(effective) == {'serveradmin', 'payobserver'}
            assert 'passwordauthentication no\n' in effective + '\n'
            assert 'allowtcpforwarding no\n' in effective + '\n'
            run('/usr/bin/systemctl', 'reload', 'ssh.service')
        except Exception:
            dropin.unlink()
            (sshdir / 'authorized_keys').unlink()
            run('/usr/sbin/sshd', '-t')
            run('/usr/bin/systemctl', 'reload', 'ssh.service')
            raise
        run('/usr/bin/systemctl', 'daemon-reload')
        run('/usr/bin/systemctl', 'start', 'discrete-pay-observer-collect.service')
        run('/usr/bin/systemctl', 'enable', '--now', 'discrete-pay-observer-collect.timer')
        hostkey = Path('/etc/ssh/ssh_host_ed25519_key.pub').read_text().split()
        print(json.dumps({'installed': 'observer', 'hostKey': ' '.join(hostkey[:2])}))


if __name__ == '__main__':
    try:
        main()
    except Exception:
        # Never print subprocess diagnostics, input JSON or a traceback.
        print('first install failed; retain staged files and inspect bounded state', file=sys.stderr)
        sys.exit(1)
