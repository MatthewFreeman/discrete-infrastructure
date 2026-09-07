"""Bounded boot qualification for the disposable Pay fixture, not deployment."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path('/opt/discrete-pay-qualification')
SYSTEM = Path('/etc/systemd/system')
TARGET = 'payqual-reboot.target'
STATE = ROOT / 'reboot-state.json'
EVIDENCE = ROOT / 'reboot-evidence.json'
NODE = ROOT / 'tools/node-v24.18.1-linux-x64/bin/node'
ALLOWED = {'node-a', 'node-b', 'node-c', 'node-d', 'miner-sender',
           'merchant-tracking-restored', 'receiver', 'facade', 'gateway', 'public', 'worker', 'edge'}

def call(args, capture=False):
    return subprocess.check_output(args, text=True) if capture else subprocess.run(args, check=True)

def digest(data):
    return hashlib.sha256(data).hexdigest()

def probe(handoff, action):
    call(['runuser', '-u', 'payqual', '--', str(NODE), str(ROOT / 'imports/service-probe.mjs'), handoff, action])

def boot():
    return Path('/proc/sys/kernel/random/boot_id').read_text().strip()

action = sys.argv[1]
if action == 'prepare':
    assert not STATE.exists(), 'do not overwrite an existing reboot test'
    assert json.loads((ROOT / 'service-evidence.json').read_text())['result'] == 'PASS'
    handoff = Path(sys.argv[2]).resolve()
    assert handoff.name == 'service-handoff.json'
    assert handoff.parent.parent == ROOT / 'pay/build/native-test'
    assert handoff.parent.name.startswith('run-')
    units = sorted((ROOT / 'boot-units').glob('payqual-*.service'))
    roles = {p.name.removeprefix('payqual-').removesuffix('.service') for p in units}
    assert roles <= ALLOWED and {'worker', 'edge', 'gateway', 'public', 'facade', 'receiver', 'node-a', 'merchant-tracking-restored'} <= roles
    data = {}
    for source in units:
        assert not (SYSTEM / source.name).exists()
        assert call(['systemctl', 'show', source.name, '-p', 'ActiveState', '--value'], True).strip() != 'active'
        value = source.read_text()
        assert str(handoff) in value and 'User=payqual' in value
        assert 'IPAddressDeny=0.0.0.0/0' in value and 'IPAddressDeny=::/0' in value
        assert 'IPAddressAllow=127.0.0.0/8' in value and 'ProtectSystem=strict' in value
        data[source.name] = (value + '\n[Unit]\nPartOf=' + TARGET + '\n').encode()
    assert not (SYSTEM / TARGET).exists()
    data[TARGET] = ('[Unit]\nDescription=Disposable Pay reboot qualification\nWants=' + ' '.join(p.name for p in units) +
                    '\nAfter=network.target\n\n[Install]\nWantedBy=multi-user.target\n').encode()
    state = {'scope': 'isolated loopback test only', 'handoff': str(handoff), 'beforeBootId': boot(),
             'files': {name: digest(value) for name, value in data.items()}, 'phase': 'installing'}
    STATE.write_text(json.dumps(state, indent=2)); STATE.chmod(0o600)
    for name, value in data.items():
        with (SYSTEM / name).open('xb') as output:
            output.write(value)
        (SYSTEM / name).chmod(0o644)
    call(['systemctl', 'daemon-reload'])
    call(['systemctl', 'start', TARGET])
    probe(str(handoff), 'restored')
    probe(str(handoff), 'edge')
    call(['systemctl', 'enable', TARGET])
    state['phase'] = 'ready-to-reboot'
    STATE.write_text(json.dumps(state, indent=2))
    print('PASS: isolated units installed, payment/TLS readback passed, reboot target enabled', flush=True)
elif action == 'verify':
    state = json.loads(STATE.read_text())
    assert state['phase'] == 'ready-to-reboot'
    assert boot() != state['beforeBootId'], 'host has not rebooted'
    for name, expected in state['files'].items():
        assert digest((SYSTEM / name).read_bytes()) == expected
        call(['systemctl', 'is-active', '--quiet', name])
    probe(state['handoff'], 'restored')
    probe(state['handoff'], 'edge')
    result = {'result': 'PASS', 'scope': 'isolated systemd boot and restored native payment; no production deployment',
              'beforeBootId': state['beforeBootId'], 'afterBootId': boot(),
              'checks': ['all exact units automatically active after actual reboot',
                         'tracking identity, registry1000, invoice replay, exact12346, events and checkpoint retained',
                         'Nginx TLS trust/hostname, short payment URI, auth and bounded rate limit'],
              'unitSha256': state['files']}
    EVIDENCE.write_text(json.dumps(result, indent=2))
    state['phase'] = 'verified'; STATE.write_text(json.dumps(state, indent=2))
    print('PASS: actual reboot and application readback; secret-free evidence ' + str(EVIDENCE), flush=True)
elif action == 'cleanup':
    state = json.loads(STATE.read_text())
    assert state['phase'] in ('installing', 'ready-to-reboot', 'verified')
    names = list(state['files'])
    assert set(names) <= {'payqual-' + r + '.service' for r in ALLOWED} | {TARGET}
    for name in names:
        if (SYSTEM / name).exists():
            assert digest((SYSTEM / name).read_bytes()) == state['files'][name], 'changed unit requires manual review'
    call(['systemctl', 'disable', '--now', TARGET])
    call(['systemctl', 'stop', *[n for n in names if n != TARGET]])
    for name in names:
        (SYSTEM / name).unlink(missing_ok=True)
    call(['systemctl', 'daemon-reload'])
    state['phase'] = 'cleaned'; STATE.write_text(json.dumps(state, indent=2))
    if EVIDENCE.exists():
        result = json.loads(EVIDENCE.read_text()); result['testUnitsRemoved'] = True
        EVIDENCE.write_text(json.dumps(result, indent=2))
    print('PASS: only exact owned test units removed; all fixture and backup data retained', flush=True)
else:
    raise ValueError('expected prepare, verify or cleanup')
