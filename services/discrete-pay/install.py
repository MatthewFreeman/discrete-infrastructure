"""Install the pinned Pay application bundle; never provision a wallet or open ports.

Four compiled entrypoints, a dedicated Unix identity and explicit operator inputs.
prepare/start/verify/stop are separate. Existing data and unrelated units are never
overwritten. No automatic boot activation, native daemon, shell hooks or fixture imports.
"""
from contextlib import closing
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import socket
import sqlite3
import stat
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit

ROOT = Path('/opt/discrete-pay')
SYSTEM = Path('/etc/systemd/system')
USER = 'discretepay'
TARGET = 'discrete-pay-app.target'
MANIFEST = '120f2b9478d4474d9cb27456aeb9b83d24febadaebdfb1ba887ba1e856f6f589'
PAY = '94995a7c8d7215d1261b79abb83ae7fdda181c58'
APPS = {'facade': 'services/walletd-facade/src/main.js', 'gateway': 'apps/gateway-api/src/main.js',
        'public': 'apps/public-web/src/main.js', 'worker': 'apps/worker/src/main.js'}
ENV = {
 'facade': {'DISCRETE_PAY_FACADE_ENABLED','DISCRETE_PAY_FACADE_LISTEN_HOST','DISCRETE_PAY_FACADE_LISTEN_PORT',
            'DISCRETE_PAY_FACADE_JOURNAL_PATH','DISCRETE_PAY_FACADE_BEARER_TOKEN','DISCRETE_PAY_FACADE_REGISTRY_MODE',
            'DISCRETE_PAY_WALLETD_ENDPOINT','DISCRETE_PAY_WALLETD_USERNAME','DISCRETE_PAY_WALLETD_PASSWORD'},
 'gateway': {'DISCRETE_PAY_GATEWAY_ENABLED','DISCRETE_PAY_GATEWAY_LISTEN_HOST','DISCRETE_PAY_GATEWAY_LISTEN_PORT',
             'DISCRETE_PAY_GATEWAY_DATABASE_PATH','DISCRETE_PAY_GATEWAY_NETWORK','DISCRETE_PAY_GATEWAY_DETECTION_GRACE_SECONDS',
             'DISCRETE_PAY_GATEWAY_FACADE_ENDPOINT','DISCRETE_PAY_GATEWAY_FACADE_BEARER_TOKEN','DISCRETE_PAY_GATEWAY_RATE_LIMIT_PER_MINUTE'},
 'public': {'DISCRETE_PAY_PUBLIC_WEB_ENABLED','DISCRETE_PAY_PUBLIC_WEB_LISTEN_HOST','DISCRETE_PAY_PUBLIC_WEB_LISTEN_PORT',
            'DISCRETE_PAY_PUBLIC_WEB_DATABASE_PATH','DISCRETE_PAY_PUBLIC_WEB_BRIDGE_BASE_URL','DISCRETE_PAY_PUBLIC_WEB_RATE_LIMIT_PER_MINUTE'},
 'worker': {'DISCRETE_PAY_WORKER_ENABLED','DISCRETE_PAY_WORKER_CONFIG_PATH'}}
PREFIX = {'facade':'DISCRETE_PAY_FACADE','gateway':'DISCRETE_PAY_GATEWAY','public':'DISCRETE_PAY_PUBLIC_WEB'}


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1048576),b''): h.update(chunk)
    return h.hexdigest()


def call(args):
    return subprocess.check_output(args,text=True,stderr=subprocess.STDOUT,timeout=90).strip()


def regular(path, private=False):
    if not path.is_absolute() or path.resolve()!=path: raise ValueError('noncanonical input path')
    info=path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1: raise ValueError('nonregular input')
    if private and (info.st_uid!=0 or stat.S_IMODE(info.st_mode)&0o077
                    or path.parent.stat().st_uid!=0 or stat.S_IMODE(path.parent.stat().st_mode)&0o077):
        raise ValueError('operator input must be root-private')


def write_once(path, data, mode=0o600):
    if path.exists() or path.is_symlink():
        regular(path)
        if path.read_bytes()!=data or stat.S_IMODE(path.stat().st_mode)!=mode:
            raise ValueError('existing file differs; retained unchanged')
        return
    with path.open('xb') as f:
        os.fchmod(f.fileno(),mode); f.write(data); f.flush(); os.fsync(f.fileno())


def atomic(path, value):
    fd,name=tempfile.mkstemp(prefix=path.name+'.pending-',dir=path.parent)
    with os.fdopen(fd,'w') as f:
        os.fchmod(f.fileno(),0o600);json.dump(value,f,sort_keys=True,indent=2);f.flush();os.fsync(f.fileno())
    os.replace(name,path)
    fd=os.open(path.parent,os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)


def env_text(role, values):
    if set(values)!=ENV[role]: raise ValueError('unexpected environment fields')
    if any(not isinstance(v,str) or not v or any(c in v for c in '\r\n\0') for v in values.values()):
        raise ValueError('invalid environment value')
    return ''.join(k+'="'+v.replace('\\','\\\\').replace('"','\\"')+'"\n' for k,v in sorted(values.items()))


def loopback(value, suffix):
    p=urlsplit(value)
    if p.scheme!='http' or p.hostname!='127.0.0.1' or p.path!=suffix or p.query or p.fragment or p.username or p.password:
        raise ValueError('exact loopback endpoint required')
    if p.port is None or not 1024<=p.port<=65535 or value!=f'http://127.0.0.1:{p.port}{suffix}':
        raise ValueError('invalid endpoint port')
    return p.port


def config(request):
    if set(request)!={'bundlePath','environments','worker','keyring','caPem','databaseSnapshot','journalSnapshot'}:
        raise ValueError('unexpected request fields')
    env=request['environments']; worker=request['worker']
    if set(env)!=set(APPS): raise ValueError('four app environments required')
    for role in APPS:env_text(role,env[role])
    ports=[]
    for role,prefix in PREFIX.items():
        e=env[role]
        if e[prefix+'_ENABLED']!='true' or e[prefix+'_LISTEN_HOST']!='127.0.0.1': raise ValueError('loopback opt-in required')
        value=e[prefix+'_LISTEN_PORT']
        if not re.fullmatch('[1-9][0-9]{3,4}',value) or not 1024<=int(value)<=65535: raise ValueError('invalid listener port')
        ports.append(int(value))
    if len(set(ports))!=3:raise ValueError('listener port collision')
    private=str(ROOT/'private')
    if env['facade']['DISCRETE_PAY_FACADE_JOURNAL_PATH']!=private+'/allocations.sqlite3':raise ValueError('foreign journal')
    for role,key in (('gateway','DISCRETE_PAY_GATEWAY_DATABASE_PATH'),('public','DISCRETE_PAY_PUBLIC_WEB_DATABASE_PATH')):
        if env[role][key]!=private+'/gateway.sqlite3':raise ValueError('foreign database')
    if env['worker']!={'DISCRETE_PAY_WORKER_ENABLED':'true','DISCRETE_PAY_WORKER_CONFIG_PATH':private+'/worker.json'}:
        raise ValueError('foreign worker config')
    if loopback(env['gateway']['DISCRETE_PAY_GATEWAY_FACADE_ENDPOINT'],'/v1/deposits')!=ports[0]:raise ValueError('facade mismatch')
    if env['gateway']['DISCRETE_PAY_GATEWAY_FACADE_BEARER_TOKEN']!=env['facade']['DISCRETE_PAY_FACADE_BEARER_TOKEN']:
        raise ValueError('facade capability mismatch')
    if len(env['facade']['DISCRETE_PAY_FACADE_BEARER_TOKEN'])<32:raise ValueError('short facade capability')
    if env['facade']['DISCRETE_PAY_FACADE_REGISTRY_MODE'] not in ('legacy','paged-v1'):raise ValueError('unknown registry mode')
    for role,key in (('gateway','DISCRETE_PAY_GATEWAY_RATE_LIMIT_PER_MINUTE'),('public','DISCRETE_PAY_PUBLIC_WEB_RATE_LIMIT_PER_MINUTE')):
        v=env[role][key]
        if not re.fullmatch('[1-9][0-9]*',v) or int(v)>10000:raise ValueError('invalid request bound')
    grace=env['gateway']['DISCRETE_PAY_GATEWAY_DETECTION_GRACE_SECONDS']
    if not re.fullmatch('0|[1-9][0-9]*',grace) or int(grace)>2**53-1:raise ValueError('invalid grace interval')
    bridge=env['public']['DISCRETE_PAY_PUBLIC_WEB_BRIDGE_BASE_URL'];p=urlsplit(bridge)
    if p.scheme!='https' or not p.hostname or p.path!='/pay/' or p.query or p.fragment or not bridge.endswith('#') or p.username or p.password:
        raise ValueError('explicit HTTPS bridge required')
    wallet=loopback(env['facade']['DISCRETE_PAY_WALLETD_ENDPOINT'],'/json_rpc')
    fields={'databasePath','walletEndpoint','walletUsername','walletPassword','nodeEndpoint','accountNumber','genesisHash',
            'network','startHeight','maxReorgDepth','intervalMs','webhookDestinations','webhookKeyringPath'}
    if set(worker) not in (fields,fields|{'webhookCaPath'}):raise ValueError('unknown worker fields')
    if worker['databasePath']!=private+'/gateway.sqlite3' or worker['webhookKeyringPath']!=private+'/keyring.json':
        raise ValueError('foreign worker data')
    if (worker['walletEndpoint']!=env['facade']['DISCRETE_PAY_WALLETD_ENDPOINT']
        or worker['walletUsername']!=env['facade']['DISCRETE_PAY_WALLETD_USERNAME']
        or worker['walletPassword']!=env['facade']['DISCRETE_PAY_WALLETD_PASSWORD']
        or worker['network']!=env['gateway']['DISCRETE_PAY_GATEWAY_NETWORK']):raise ValueError('worker identity mismatch')
    node=loopback(worker['nodeEndpoint'],'/json_rpc')
    if wallet==node or wallet in ports or node in ports:raise ValueError('RPC/listener collision')
    if not re.fullmatch('[a-f0-9]{64}',worker['genesisHash']) or not re.fullmatch('[a-z0-9][a-z0-9-]{0,31}',worker['network']):
        raise ValueError('invalid chain identity')
    for key,minimum,maximum in (('startHeight',0,2**53-1),('maxReorgDepth',1,1000),('intervalMs',100,60000)):
        if type(worker[key]) is not int or not minimum<=worker[key]<=maximum:raise ValueError('invalid worker bound')
    if not isinstance(worker['webhookDestinations'],list) or len(worker['webhookDestinations'])>100:raise ValueError('invalid destinations')
    addresses=set()
    for d in worker['webhookDestinations']:
        if set(d)!={'url','address'}:raise ValueError('invalid destination fields')
        p=urlsplit(d['url']); ip=ipaddress.IPv4Address(d['address'])
        if p.scheme!='https' or not p.hostname or p.username or p.password or p.fragment or ip.is_unspecified or ip.is_multicast:
            raise ValueError('invalid explicit HTTPS destination')
        addresses.add(str(ip))
    if request['caPem'] is not None:
        if worker.get('webhookCaPath')!=private+'/ca.pem' or not isinstance(request['caPem'],str):raise ValueError('invalid CA input')
    elif 'webhookCaPath' in worker:raise ValueError('missing CA input')
    if not isinstance(request['keyring'],dict) or not 1<=len(request['keyring'])<=32 or any(not re.fullmatch('[a-zA-Z0-9_-]{1,64}',k)
       or not isinstance(v,str) or not re.fullmatch('[a-f0-9]{64}',v) for k,v in request['keyring'].items()):raise ValueError('invalid keyring')
    if (request['databaseSnapshot'] is None)!=(request['journalSnapshot'] is None):raise ValueError('paired database/journal snapshots required')
    return ports,sorted(addresses)


def unit(role, release, addresses):
    if role not in APPS or not re.fullmatch('/opt/discrete-pay/releases/[a-f0-9]{64}',str(release)):raise ValueError('foreign unit release')
    allow=' '.join(['localhost',*(addresses if role=='worker' else [])])
    return f'''[Unit]
Description=Discrete Pay application {role}
PartOf={TARGET}
After=network.target
StartLimitIntervalSec=60
StartLimitBurst=10
[Service]
Type=exec
User={USER}
Group={USER}
WorkingDirectory={release}/pay
EnvironmentFile={ROOT}/env/{role}
ExecStart={release}/bin/node {release}/pay/dist/{APPS[role]}
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
IPAddressAllow={allow}
ReadWritePaths={ROOT}/private
ReadOnlyPaths={ROOT}/private/worker.json {ROOT}/private/keyring.json
ReadOnlyPaths=-{ROOT}/private/ca.pem
TasksMax=64
MemoryMax=256M
StandardOutput=journal
StandardError=journal
'''


def name(role):return 'discrete-pay-app-'+role+'.service'


def package(path):
    for directory in [path,*path.parents]:
        if directory.resolve()!=directory or directory.stat().st_uid!=0 or stat.S_IMODE(directory.stat().st_mode)&0o022:
            raise ValueError('bundle directory is not root controlled')
    regular(path/'manifest.json')
    if digest(path/'manifest.json')!=MANIFEST:raise ValueError('unqualified manifest')
    m=json.loads((path/'manifest.json').read_text())
    if m['payCommit']!=PAY:raise ValueError('wrong Pay commit')
    found={}
    for f in path.rglob('*'):
        if f.is_symlink() or not (f.is_file() or f.is_dir()):raise ValueError('nonregular bundle')
        if f.stat().st_uid!=0 or stat.S_IMODE(f.stat().st_mode)&0o022:raise ValueError('mutable bundle input')
        if f.is_file():regular(f);found[f.relative_to(path).as_posix()]=digest(f)
    if found!={**m['files'],'manifest.json':MANIFEST}:raise ValueError('bundle content mismatch')
    return m


def verify(state):
    if state['root']!=str(ROOT) or state['payCommit']!=PAY:raise ValueError('foreign install state')
    for path,value in state['immutable'].items():
        p=Path(path);regular(p)
        if digest(p)!=value['sha256'] or p.stat().st_uid!=value['uid'] or stat.S_IMODE(p.stat().st_mode)!=value['mode']:
            raise ValueError('owned deployment file changed')


def load_state():
    path=ROOT/'install.json';regular(path)
    if path.stat().st_uid!=0 or stat.S_IMODE(path.stat().st_mode)!=0o600 or ROOT.stat().st_uid!=0:
        raise ValueError('install state is not root controlled')
    return json.loads(path.read_text())


def install_units(state):
    for filename,text in state['unitText'].items():
        if filename not in {name(r) for r in APPS}|{TARGET}:raise ValueError('foreign unit')
        write_once(SYSTEM/filename,text.encode(),0o644)
    call(['systemd-analyze','verify',*[str(SYSTEM/n) for n in state['unitText']]])
    call(['systemctl','daemon-reload'])


def prepare(file):
    regular(file,True)
    if file.stat().st_size>65536:raise ValueError('request too large')
    request=json.loads(file.read_text());ports,addresses=config(request)
    source=Path(request['bundlePath']);m=package(source)
    if ROOT.exists():
        state=load_state()
        if state['requestSha256']!=digest(file) or state['phase']!='prepared':raise ValueError('existing deployment retained')
        # Interrupted unit publication may resume; never rewrite application data.
        for path,value in state['immutable'].items():
            if Path(path).parent!=SYSTEM and digest(Path(path))!=value['sha256']:raise ValueError('prepared input changed')
        install_units(state);verify(state);return
    for n in [TARGET,*[name(r) for r in APPS]]:
        if (SYSTEM/n).exists() or call(['systemctl','show',n,'-p','LoadState','--value'])!='not-found':raise ValueError('unit name conflict')
    for port in ports:
        with socket.socket() as s:s.bind(('127.0.0.1',port))
    # Require root-private, quiescent paired inputs; never copy a live WAL database.
    for key in ('databaseSnapshot','journalSnapshot'):
        if request[key] is not None:
            src=Path(request[key]);regular(src,True)
            if any(Path(str(src)+suffix).exists() for suffix in ('-wal','-shm','-journal')):raise ValueError('snapshot is not quiescent')
            with closing(sqlite3.connect(src.as_uri()+'?mode=ro',uri=True)) as db:
                if db.execute('PRAGMA integrity_check').fetchone()!=('ok',):raise ValueError('snapshot integrity failed')
    import pwd
    try:pwd.getpwnam(USER)
    except KeyError:pass
    else:raise ValueError('existing runtime identity; refuse adoption')
    stage=Path(tempfile.mkdtemp(prefix='.discrete-pay-prepare-',dir=ROOT.parent));stage.chmod(0o700)
    release=ROOT/'releases'/MANIFEST;dest=stage/'releases'/MANIFEST
    dest.mkdir(parents=True);shutil.copytree(source/'pay',dest/'pay');(dest/'bin').mkdir()
    shutil.copyfile(source/'bin/node',dest/'bin/node')
    for p in dest.rglob('*'):
        if p.is_file() and digest(p)!=m['files'][p.relative_to(dest).as_posix()]:raise ValueError('copied package changed')
    for p in [stage/'releases',dest,*dest.rglob('*')]:p.chmod(0o755 if p.is_dir() or p==dest/'bin/node' else 0o644)
    (stage/'env').mkdir(mode=0o700);private=stage/'private';private.mkdir(mode=0o700)
    for role in APPS:write_once(stage/'env'/role,env_text(role,request['environments'][role]).encode())
    write_once(private/'worker.json',json.dumps(request['worker']).encode())
    write_once(private/'keyring.json',json.dumps(request['keyring']).encode())
    if request['caPem'] is not None:write_once(private/'ca.pem',request['caPem'].encode())
    if request['databaseSnapshot'] is None:
        code="import {DiscretePayStore} from './dist/src/persistence/store.js'; const s=new DiscretePayStore(process.argv[1]); s.close();"
        subprocess.run([str(dest/'bin/node'),'--input-type=module','-e',code,str(private/'gateway.sqlite3')],
                       cwd=dest/'pay',check=True,capture_output=True,timeout=30)
    else:
        for key,filename in (('databaseSnapshot','gateway.sqlite3'),('journalSnapshot','allocations.sqlite3')):
            shutil.copyfile(request[key],private/filename)
    call(['useradd','--system','--user-group','--home-dir','/nonexistent','--shell','/usr/sbin/nologin',USER])
    identity=pwd.getpwnam(USER)
    for p in [private,*private.iterdir()]:os.chown(p,identity.pw_uid,identity.pw_gid);p.chmod(0o700 if p.is_dir() else 0o600)
    values={name(r):unit(r,release,addresses) for r in APPS}
    values[TARGET]='[Unit]\nDescription=Discrete Pay application target\nWants='+' '.join(values)+'\nAfter=network.target\n\n[Install]\nWantedBy=multi-user.target\n'
    immutable={str(ROOT/p.relative_to(stage)):{'sha256':digest(p),'uid':p.stat().st_uid,'mode':stat.S_IMODE(p.stat().st_mode)}
               for p in stage.rglob('*') if p.is_file() and p.name not in ('gateway.sqlite3','allocations.sqlite3')}
    for n,v in values.items():immutable[str(SYSTEM/n)]={'sha256':hashlib.sha256(v.encode()).hexdigest(),'uid':0,'mode':0o644}
    state={'root':str(ROOT),'release':str(release),'payCommit':PAY,'phase':'prepared','requestSha256':digest(file),
           'immutable':immutable,'unitText':values,'ports':ports,'uid':identity.pw_uid}
    atomic(stage/'install.json',state);stage.chmod(0o755);stage.rename(ROOT)
    install_units(state);verify(state)


def main():
    if os.geteuid()!=0:raise ValueError('root required')
    import fcntl
    fd=os.open('/run/lock/discrete-pay-install.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    action=sys.argv[1]
    if action=='prepare':prepare(Path(sys.argv[2]));print('PREPARED: application files and disabled units; no wallet or public port changes');return
    state=load_state();verify(state)
    if action=='verify':print(json.dumps({'payCommit':PAY,'phase':state['phase'],'services':4,'filesMatch':True}));return
    if action=='start':
        try:
            call(['systemctl','start',TARGET])
            for role in APPS:
                if call(['systemctl','is-active',name(role)])!='active':raise ValueError('application not active')
        except Exception:
            call(['systemctl','stop',TARGET,*[name(r) for r in APPS]]);raise
        state['phase']='started-not-accepted'
    elif action=='stop':
        call(['systemctl','stop',TARGET,*[name(r) for r in APPS]]);state['phase']='stopped-data-retained'
    else:raise ValueError('expected prepare/start/verify/stop')
    atomic(ROOT/'install.json',state);print('STATE: '+state['phase']+'; application data retained')


if __name__=='__main__':
    try:main()
    except Exception:
        # Operator input contains secrets; never serialize exception text or commands.
        print('REFUSED: inspect protected inputs and retained installation state',file=sys.stderr);sys.exit(1)
