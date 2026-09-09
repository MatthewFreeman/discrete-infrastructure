"""Assemble an internal pinned Linux bundle; not an installer or public release.

Only explicit compiled Pay/source archives and already hash-pinned binaries are
copied. No wallet, database, host configuration, token, .ssh or fixture tree enters
the package. The clean Core daemon must not be replaced with a difficulty fixture.
"""
import gzip
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import shutil
import sys
import tarfile

PAY = '939d8fe60435c895d618246d1a50923c7b3f46b2'
CORE = '8703c16fa40ffc8456e3d71696b6220b32b4d74a'
ROOT = Path('/opt/discrete-pay-qualification')
PINS = {
 'walletd': '630a033e0b41ebb01d666886948bd9a4affa4c44a299474bc125c3284afc15d1',
 'discreted': 'b3c09f1ee8df80ff7078ed0d8f7c6c9dbb0c11c47b8b44a19a3d61b8c3e30d17',
 'core-license': 'fcab022adb04e4779be9a492716b8c13af45ff44f087723ff704d7ef55e9ba0a',
 'node': 'f3432a45b03b2da0d270095fdd8813dc34cbea73f5fc8b18c7a384b7cf9b333a',
 'node-license': '148eacf7863ef4329224a29398623077200a27194aa075569faf4a0a85566ca5',
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def members(archive):
    seen = set()
    for member in archive.getmembers():
        path = PurePosixPath(member.name)
        if path.is_absolute() or '..' in path.parts or str(path) in seen or not (member.isfile() or member.isdir()):
            raise ValueError('unsafe archive member')
        seen.add(str(path))
        if path.parts[0] not in ('dist', 'docs', 'package.json', 'pnpm-lock.yaml'):
            raise ValueError('runtime archive outside allowlist')
        if member.isfile() and path.suffix not in ('.js', '.json', '.sql', '.css', '.md', '.yaml', '.svg', '.txt'):
            raise ValueError('unexpected runtime asset')
    return archive.getmembers()


def pack(tree, destination):
    # Deterministic archive envelope; this does not claim compiler reproducibility.
    with destination.open('xb') as output:
        with gzip.GzipFile(filename='', fileobj=output, mode='wb', mtime=0) as stream:
            with tarfile.open(fileobj=stream, mode='w|', format=tarfile.PAX_FORMAT) as archive:
                for path in sorted(tree.rglob('*')):
                    if path.is_symlink() or not (path.is_dir() or path.is_file()):
                        raise ValueError('unexpected bundle object')
                    info=tarfile.TarInfo(path.relative_to(tree).as_posix())
                    info.uid=info.gid=info.mtime=0;info.uname=info.gname='root'
                    info.mode=0o755 if path.is_dir() or path.parent.name=='bin' else 0o644
                    if path.is_dir():info.type=tarfile.DIRTYPE;archive.addfile(info)
                    else:
                        data=path.read_bytes();info.size=len(data);archive.addfile(info,io.BytesIO(data))


def main(runtime, runtime_sha, source, source_sha):
    if runtime_sha!='b6c19b5e8567bb01cd607396b74c95138758ad1628225dd2b7aa6acb71369b35' or source_sha!='c0ae4e4d34fd08f1a6aa92a18a9c988c76e5aded841766ab8bd6c9057164fc05':raise ValueError('unknown immutable Pay input')
    if sha(runtime)!=runtime_sha or sha(source)!=source_sha:raise ValueError('Pay input hash mismatch')
    inputs = {
      'walletd':ROOT/'freeman-ci-8703c16/walletd', 'discreted':ROOT/'freeman-ci-8703c16/discreted',
      'core-license':ROOT/'freeman-ci-8703c16/LICENSE',
      'node':ROOT/'tools/node-v24.18.1-linux-x64/bin/node',
      'node-license':ROOT/'tools/node-v24.18.1-linux-x64/LICENSE',
    }
    for name,path in inputs.items():
        if path.is_symlink() or sha(path)!=PINS[name]:raise ValueError('binary/license pin mismatch')
    base=ROOT/'bundles';base.mkdir(mode=0o755,exist_ok=True)
    tree=base/('pay-'+PAY[:7]+'-core-'+CORE[:7]);tree.mkdir(mode=0o755)
    app=tree/'pay';app.mkdir()
    with tarfile.open(runtime) as archive:
        archive.extractall(app,members=members(archive))
    (tree/'bin').mkdir();(tree/'licenses').mkdir();(tree/'source').mkdir()
    for name in ('walletd','discreted','node'):shutil.copyfile(inputs[name],tree/'bin'/name)
    for name in ('core-license','node-license'):shutil.copyfile(inputs[name],tree/'licenses'/(name+'.txt'))
    shutil.copyfile(source,tree/'source'/('pay-'+PAY+'.tar'))
    manifest = {'format':1,'status':'internal-candidate-not-public-release',
      'payCommit':PAY,'paySourceSha256':source_sha,'payRuntimeArchiveSha256':runtime_sha,
      'coreCommit':CORE,'coreBaseCommit':'3e8ef0bad719c6ac6304674f76df52cc5aecbea7',
      'coreCiRun':34181954333,'coreCiArtifact':10039317338,
      'coreArtifactDigest':'751c530f34d7dc35524c5df479b9e18fa35cd5e573cb813046350700c72b9c90',
      'coreSourceUrl':'https://github.com/MatthewFreeman/discrete/tree/'+CORE,
      'nodeVersion':'24.18.1','architecture':'linux-x64',
      'scope':'pinned compiled files only; no configuration, wallets, services or production activation',
      'files':{p.relative_to(tree).as_posix():sha(p) for p in sorted(tree.rglob('*')) if p.is_file()}}
    (tree/'manifest.json').write_text(json.dumps(manifest,sort_keys=True,indent=2)+'\n')
    for path in tree.rglob('*'):path.chmod(0o755 if path.is_dir() or path.parent.name=='bin' else 0o644)
    first=tree.with_suffix('.tar.gz');second=tree.with_suffix('.repeat.tar.gz')
    pack(tree,first);pack(tree,second)
    if sha(first)!=sha(second):raise ValueError('archive reproducibility failure')
    print(json.dumps({'bundle':str(first),'sha256':sha(first),'manifestSha256':sha(tree/'manifest.json'),'repeatedArchiveEqual':True,'files':len(manifest['files'])}))


if __name__=='__main__':
    main(Path(sys.argv[1]),sys.argv[2],Path(sys.argv[3]),sys.argv[4])
