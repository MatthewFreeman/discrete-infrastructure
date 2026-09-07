"""Verify every archived Core source and both exact fixture modifications."""
import hashlib
import json
from pathlib import Path
import tarfile

root = Path('/opt/discrete-pay-qualification')
pay = root / 'pay'
source = pay / 'build/native-test/freeman-core'
archive = root / 'imports/core-source.tar'
sha = lambda data: hashlib.sha256(data).hexdigest()
assert sha(archive.read_bytes()) == 'aca62414353d5277bc8bc18dca8e0b9c6a01382edf159e99484106ebf114dff1'
replacements = {
    'src/P2p/NetNode.cpp': ('    addPortMapping(logger, m_listeningPort, m_external_port);',
        '    // Local qualification safety: loopback listeners must not configure a router.\n    if (m_bind_ip != "127.0.0.1") {\n      addPortMapping(logger, m_listeningPort, m_external_port);\n    }'),
    'src/CryptoNoteCore/Currency.cpp': ('    assert(timestamps.size() == cumulativeDifficulties.size());',
        '    assert(timestamps.size() == cumulativeDifficulties.size());\n\n    // Private qualification fixture only: deterministic mining, never mainnet.\n    if (isTestnet()) return 1;'),
}
count = 0
with tarfile.open(archive) as tar:
    for member in tar.getmembers():
        if not member.isfile():
            continue
        original = tar.extractfile(member).read()
        actual = (source / member.name).read_bytes()
        if member.name in replacements:
            before, after = replacements[member.name]
            text = original.decode().replace('\r\n', '\n')
            assert text.count(before) == 1
            assert actual.decode().replace('\r\n', '\n') == text.replace(before, after), member.name
        else:
            assert actual == original, member.name
        count += 1
manifest = {'coreCommit':'c114f13cdc16797901ad5f132d69ed79bc2956b2',
    'platform':'linux-x64', 'verifiedSourceFiles':count,
    'sourceArchiveSha256':sha(archive.read_bytes()),
    'patchSha256':[sha((pay / 'test/worker-runtime' / p).read_bytes()) for p in ('native-core-loopback.patch','native-core-difficulty.patch')]}
for binary in ('discreted','walletd'):
    manifest[binary+'Sha256'] = sha((pay / 'build/native-test/bin/src' / binary).read_bytes())
(pay / 'build/native-test/build-manifest.json').write_text(json.dumps(manifest, indent=2))
print(json.dumps(manifest, indent=2))
