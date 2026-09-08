import copy
import unittest
from verify import SSH, validate_ssh, validate_firewall


def fixture():
    entries = [{'chain': {'family': 'ip', 'table': 'discrete_filter', 'name': n,
                'type': 'filter', 'hook': n, 'prio': 0, 'policy': p}}
               for n, p in [('input', 'drop'), ('forward', 'drop'), ('output', 'accept')]]
    def rule(left=None, right=None, verdict='accept'):
        expr = [] if left is None else [{'match': {'op': '==', 'left': left, 'right': right}}]
        entries.append({'rule': {'family': 'ip', 'table': 'discrete_filter', 'chain': 'input',
                                'expr': expr + [{'counter': {'packets': 1, 'bytes': 52}}, {verdict: None}]}})
    rule({'meta': {'key': 'iifname'}}, 'lo')
    rule({'ct': {'key': 'state'}}, {'set': ['established', 'related']})
    rule({'ct': {'key': 'state'}}, 'invalid', 'drop')
    rule({'payload': {'protocol': 'ip', 'field': 'protocol'}}, 'icmp')
    for port in (22822, 80, 443):
        rule({'payload': {'protocol': 'tcp', 'field': 'dport'}}, port)
    rule(verdict='drop')
    return {'nftables': entries}


class PolicyTest(unittest.TestCase):
    def test_ssh_control_and_negative_controls(self):
        good = '\n'.join(k+' '+v for k, v in SSH.items())
        validate_ssh(good)
        for key, value in [('passwordauthentication', 'yes'), ('permitrootlogin', 'yes'),
                           ('authenticationmethods', 'any'), ('allowusers', 'serveradmin root'),
                           ('allowtcpforwarding', 'yes'), ('port', '22')]:
            with self.subTest(key=key), self.assertRaises(AssertionError):
                validate_ssh(good.replace(key+' '+SSH[key], key+' '+value))

    def test_firewall_control(self):
        validate_firewall(fixture())

    def test_debian_12_nft_106_state_array(self):
        # Live nft 1.0.6 readback uses a JSON array, not a set wrapper.
        good = fixture()
        match = good['nftables'][4]['rule']['expr'][0]['match']
        match.update(op='in', right=['established', 'related'])
        good['nftables'][5]['rule']['expr'][0]['match']['op'] = 'in'
        validate_firewall(good)
        for states in (['new', 'established', 'related'], ['established'], ['invalid', 'related']):
            bad = copy.deepcopy(good)
            bad['nftables'][4]['rule']['expr'][0]['match']['right'] = states
            with self.subTest(states=states), self.assertRaises(AssertionError):
                validate_firewall(bad)

    def test_firewall_rejects_other_ingress(self):
        for port in (22, 9330, 9331, 9332, 9340, 7081):
            bad = fixture()
            bad['nftables'][7]['rule']['expr'][0]['match']['right'] = port
            with self.subTest(port=port), self.assertRaises(AssertionError):
                validate_firewall(bad)
        bad = fixture()
        bad['nftables'][7]['rule']['expr'][0]['match']['left']['payload']['protocol'] = 'udp'
        with self.assertRaises(AssertionError):
            validate_firewall(bad)

    def test_bare_accept_and_default_accept_are_refused(self):
        bad = fixture()
        bad['nftables'][-1]['rule']['expr'][-1] = {'accept': None}
        with self.assertRaises(AssertionError):
            validate_firewall(bad)
        bad = fixture()
        bad['nftables'][0]['chain']['policy'] = 'accept'
        with self.assertRaises(AssertionError):
            validate_firewall(bad)


if __name__ == '__main__':
    unittest.main()
