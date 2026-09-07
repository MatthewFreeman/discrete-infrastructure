"""Host policy only. Fail closed on unexpected SSH/firewall ingress."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PORTS = {80, 443, 22822}
SSH = {
    'addressfamily': 'inet', 'port': '22822', 'permitrootlogin': 'no',
    'passwordauthentication': 'no', 'kbdinteractiveauthentication': 'no',
    'authenticationmethods': 'publickey', 'pubkeyauthentication': 'yes',
    'allowusers': 'serveradmin', 'x11forwarding': 'no',
    'allowagentforwarding': 'no', 'allowtcpforwarding': 'no', 'permittunnel': 'no',
}


def run(*args):
    return subprocess.check_output(args, text=True)


def validate_ssh(text):
    fields = {}
    for line in text.splitlines():
        key, _, value = line.partition(' ')
        if key in SSH:
            assert key not in fields, 'duplicate SSH policy field'
            fields[key] = value
    assert fields == SSH, 'effective SSH policy mismatch'


def validate_firewall(doc):
    entries = doc['nftables']
    chains = {e['chain']['name']: e['chain'] for e in entries if 'chain' in e}
    assert set(chains) == {'input', 'forward', 'output'}, 'unexpected chains'
    for name, policy in [('input', 'drop'), ('forward', 'drop'), ('output', 'accept')]:
        chain = chains[name]
        assert chain['family'] == 'ip' and chain['table'] == 'discrete_filter'
        assert chain['type'] == 'filter' and chain['hook'] == name and chain['prio'] == 0
        assert chain['policy'] == policy, 'incorrect default policy'
    ports, controls = set(), []
    rules = [e['rule'] for e in entries if 'rule' in e]
    assert len(rules) == 8, 'unexpected rule count'
    for rule in rules:
        assert rule['family'] == 'ip' and rule['table'] == 'discrete_filter' and rule['chain'] == 'input'
        expr = [e for e in rule['expr'] if set(e) != {'counter'}]
        if expr == [{'drop': None}]:
            controls.append('drop'); continue
        assert len(expr) == 2 and set(expr[0]) == {'match'}, 'unexpected rule expression'
        m = expr[0]['match']
        assert set(m) == {'op', 'left', 'right'} and m['op'] in ('==', 'in')
        left, right, verdict = m['left'], m['right'], expr[1]
        if left == {'meta': {'key': 'iifname'}} and right == 'lo' and verdict == {'accept': None}:
            controls.append('loopback')
        elif left == {'ct': {'key': 'state'}} and right in (
                {'set': ['established', 'related']}, ['established', 'related']) and verdict == {'accept': None}:
            controls.append('established')
        elif left == {'ct': {'key': 'state'}} and right == 'invalid' and verdict == {'drop': None}:
            controls.append('invalid')
        elif left == {'payload': {'protocol': 'ip', 'field': 'protocol'}} and right == 'icmp' and verdict == {'accept': None}:
            controls.append('icmp')
        else:
            assert left == {'payload': {'protocol': 'tcp', 'field': 'dport'}} and verdict == {'accept': None}
            assert isinstance(right, int) and right in PORTS and right not in ports, 'unexpected ingress port'
            ports.add(right)
    assert controls == ['loopback', 'established', 'invalid', 'icmp', 'drop']
    assert ports == PORTS
    assert rules[-1]['expr'][-1] == {'drop': None}, 'terminal drop missing'


def main(mode):
    if mode in ('ssh', 'all'):
        run('sshd', '-t')
        validate_ssh(run('sshd', '-T'))
        print('PASS: effective key-only serveradmin SSH on 22822')
    if mode in ('firewall', 'all'):
        validate_firewall(json.loads(run('nft', '-j', 'list', 'table', 'ip', 'discrete_filter')))
        print('PASS: exact firewall ingress 80,443,22822; internal ports excluded')
    if mode == 'all':
        for component in ('ipv4', 'fail2ban', 'timesync'):
            subprocess.run(['bash', str(ROOT / 'scripts/verify.sh'), component], check=True)
        for unit in ('ssh', 'nftables'):
            run('systemctl', 'is-active', unit)
            run('systemctl', 'is-enabled', unit)
        for line in run('ss', '-4', '-H', '-lnt').splitlines():
            address = line.split()[3]
            host, port = address.rsplit(':', 1)
            if not host.startswith('127.'):
                assert int(port) in PORTS, 'unexpected public TCP listener'
        print('PASS: Discrete Pay host profile (not application deployment)')


if __name__ == '__main__':
    assert len(sys.argv) == 2 and sys.argv[1] in ('ssh', 'firewall', 'all')
    main(sys.argv[1])
