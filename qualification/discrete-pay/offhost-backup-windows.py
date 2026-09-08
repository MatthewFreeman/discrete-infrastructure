# Preserved executed helper. Run its copy from the Pay workspace's
# build/server-bootstrap directory alongside the owner's protected resume_host
# adapter; do not embed credentials or treat this as a production backup job.
"""Encrypted off-host rehearsal for the existing disposable archive only.

No code is uploaded. Plain archive bytes travel only through pinned SSH and RAM.
The separate encrypted RSA test key uses the existing serveradmin key passphrase
already held in the owner's vault; this is not a production retention policy.
"""
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import tarfile
from resume_host import connect, state

root=Path(r'C:\Users\Admin\.ssh\discrete-pay-test-backup-20260907')
assert root.is_dir()
openssl=r'C:\Program Files\FireDaemon OpenSSL 3\bin\openssl.exe'
private=root/'recipient-key.pem'
cert=root/'recipient-cert.pem'
current=os.environ.get('DISCRETE_PAY_BACKUP_FIXTURE')=='current-v0.9.10'
paged=os.environ.get('DISCRETE_PAY_BACKUP_FIXTURE')=='paged-main'
assert os.environ.get('DISCRETE_PAY_BACKUP_FIXTURE') in (None,'current-v0.9.10','paged-main')
fixture='run-refv70x9' if paged else 'run-zNSX1D' if current else 'run-ELNsoz'
cipher=root/('systemd-'+fixture+'.cms')
assert not cipher.exists(), 'preserve existing backup files'
assert (private.exists() and cert.exists()) if current or paged else not any(p.exists() for p in (private,cert))
passphrase=(state['keyPassphrase']+'\n').encode()
source='/opt/discrete-pay-qualification/backups/systemd-run-ELNsoz.tar.gz'
expected='4ae9345313bdb322a874ddcf8e65b58309b87dc8febd9a27dc4b7d2e46f65b2f'
if current or paged:
    service_path=Path(__file__).parents[1]/('infrastructure-pilot/qualification/discrete-pay/evidence/paged-service-merged-main.json' if paged else 'no-domain-evidence-2026-09-07/current-services.json')
    service=json.loads(service_path.read_text())
    assert service['result']=='PASS'
    source='/opt/discrete-pay-qualification/backups/systemd-'+fixture+'.tar.gz'
    assert service['backup']==source
    expected=service['backupSha256']

def run(args,data=None,check=True):
    result=subprocess.run([openssl,*args],input=data,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    if check: assert result.returncode==0,'OpenSSL operation failed (private details suppressed)'
    return result

if not (current or paged): run(['req','-new','-x509','-newkey','rsa:3072','-keyout',str(private),'-out',str(cert),
     '-days','365','-subj','/CN=Discrete-Pay-disposable-backup','-passout','stdin'],passphrase)
client=connect()
try:
    stdin,stdout,stderr=client.exec_command('sudo -k -S -p "" -- cat '+source,timeout=120)
    stdin.write(state['adminPassword']+'\n');stdin.flush();stdout.channel.shutdown_write()
    encrypt=subprocess.Popen([openssl,'cms','-encrypt','-binary','-aes-256-gcm','-outform','DER',
                              '-out',str(cipher),'-recip',str(cert)],stdin=subprocess.PIPE,
                             stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
    hashed=hashlib.sha256();size=0
    try:
        while True:
            chunk=stdout.read(1024*1024)
            if not chunk:break
            hashed.update(chunk);size+=len(chunk);encrypt.stdin.write(chunk)
        encrypt.stdin.close()
        assert stdout.channel.recv_exit_status()==0,'archive read failed'
        assert encrypt.wait(timeout=30)==0,'CMS encryption failed'
    finally:
        if encrypt.poll() is None:encrypt.kill();encrypt.wait()
    assert hashed.hexdigest()==expected,'archive changed since cold-restore test'
finally:client.close()

args=['cms','-decrypt','-binary','-inform','DER','-in',str(cipher),'-recip',str(cert),
      '-inkey',str(private),'-passin','stdin']
assert run(args,b'incorrect-disposable-passphrase\n',check=False).returncode!=0
plain=run(args,passphrase).stdout
assert hashlib.sha256(plain).hexdigest()==expected
restored=root/('sqlite-readback-paged' if paged else 'sqlite-readback-current' if current else 'sqlite-readback');restored.mkdir()
with tarfile.open(fileobj=io.BytesIO(plain),mode='r:gz') as tar:
    members=tar.getmembers()
    for member in members:
        parts=Path(member.name).parts
        assert parts[0]==fixture and '..' not in parts and not Path(member.name).is_absolute()
        assert member.isfile() or member.isdir()
    h=json.loads(tar.extractfile(fixture+'/service-handoff.json').read())
    dbname=Path(h['gatewayEnv']['DISCRETE_PAY_GATEWAY_DATABASE_PATH']).name
    for suffix in ('','-wal','-shm'):
        name=fixture+'/'+dbname+suffix
        if name in tar.getnames():
            (restored/(dbname+suffix)).write_bytes(tar.extractfile(name).read())
    database=sqlite3.connect('file:'+str(restored/dbname).replace('\\','/')+'?mode=ro',uri=True)
    try:
        assert database.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        row=database.execute('SELECT status, amount_atomic, confirmed_atomic FROM invoices WHERE id=?',(h['invoiceId'],)).fetchone()
        assert row and row[0]=='overpaid' and int(row[1])==12345 and int(row[2])==12346
    finally:database.close()

# Corrupted ciphertext must fail authentication; the original stays unchanged.
damaged=bytearray(cipher.read_bytes());damaged[-1]^=1
tamper=root/('tampered-test-paged.cms' if paged else 'tampered-test.cms');assert not tamper.exists();tamper.write_bytes(damaged)
badargs=[str(tamper) if value==str(cipher) else value for value in args]
assert run(badargs,passphrase,check=False).returncode!=0
tamper.unlink()
evidence={'result':'PASS','scope':'off-host encrypted backup/decryption and SQLite readback of disposable fixture; not production retention',
          'sourceArchiveSha256':expected,'encryptedArchiveSha256':hashlib.sha256(cipher.read_bytes()).hexdigest(),
          'archiveBytes':size,'archiveMembers':len(members),'cipher':'OpenSSL CMS AES-256-GCM with RSA3072 recipient',
          'checks':['pinned SSH archive stream; no plaintext tar on local disk','wrong key passphrase refused',
                    'decrypted archive exactly matches cold-restored source','all archive paths and object types validated',
                    'SQLite integrity_check ok; exact overpaid12346 against expected12345','tampered ciphertext refused'],
          'privateArtifacts':str(root),'keyPassphraseSource':'existing serveradmin SSH-key passphrase; separate encrypted RSA test key retained locally'}
output=Path(__file__).parents[1]/'no-domain-evidence-2026-09-07/offhost-backup.json'
if current: output=output.with_name('current-offhost-backup.json')
if paged: output=output.with_name('paged-offhost-backup.json')
output.write_text(json.dumps(evidence,indent=2),encoding='utf8')
print('PASS: encrypted off-host backup, wrong-passphrase/tamper refusal and exact payment SQLite readback')
print('Secret-free evidence:',output)
