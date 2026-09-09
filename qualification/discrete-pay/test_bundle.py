import importlib.util
import io
from pathlib import Path
import tarfile
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('bundle',Path(__file__).with_name('bundle-candidate.py'))
bundle=importlib.util.module_from_spec(spec);spec.loader.exec_module(bundle)

class BundleTest(unittest.TestCase):
    def archive(self,name,kind=tarfile.REGTYPE):
        buffer=io.BytesIO()
        with tarfile.open(fileobj=buffer,mode='w') as archive:
            entry=tarfile.TarInfo(name);entry.type=kind
            archive.addfile(entry,io.BytesIO(b''))
        buffer.seek(0)
        return tarfile.open(fileobj=buffer)

    def test_member_allowlist(self):
        with self.archive('dist/apps/operator/src/main.js') as archive:self.assertEqual(len(bundle.members(archive)),1)
        for name,kind in [('../etc/passwd',tarfile.REGTYPE),('/dist/a.js',tarfile.REGTYPE),('dist/link.js',tarfile.SYMTYPE),('wallet.json',tarfile.REGTYPE),('dist/token.pem',tarfile.REGTYPE)]:
            with self.archive(name,kind) as archive:
                with self.assertRaises(ValueError):bundle.members(archive)

    def test_deterministic_envelope_and_binary_permissions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);tree=root/'tree';(tree/'bin').mkdir(parents=True)
            (tree/'bin/node').write_bytes(b'test fixture only')
            (tree/'manifest.json').write_text('{}')
            first=root/'first.tgz';second=root/'second.tgz'
            bundle.pack(tree,first);bundle.pack(tree,second)
            self.assertEqual(bundle.sha(first),bundle.sha(second))
            with tarfile.open(first) as archive:
                self.assertEqual(archive.getmember('bin/node').mode,0o755)
                self.assertEqual(archive.getmember('manifest.json').mode,0o644)

if __name__=='__main__':unittest.main()
