from pathlib import Path
import hashlib,sys
from resume_host import connect,command
conf=Path(__file__).with_name('gui-forward.conf').read_bytes().replace(b'\r\n',b'\n')
digest=hashlib.sha256(conf).hexdigest()
target='/etc/ssh/sshd_config.d/000-pay-gui-temporary.conf'
cleanup='/opt/discrete-pay-qualification/imports/restore-gui-forward.sh'
rollback=('#!/bin/sh\nset -eu\nif test -f '+target+'; then\n test "$(sha256sum '+target+' | cut -d " " -f1)" = '+digest+'\n rm -- '+target+'\n /usr/sbin/sshd -t\n systemctl reload ssh\nfi\n').encode()
client=connect()
try:
 if sys.argv[1]=='enable':
  command(client,'guard temporary forwarding scope','test ! -e '+target+'; sshd -T -C user=serveradmin,host=localhost,addr=127.0.0.1 | grep -Fx "allowtcpforwarding no"')
  with client.open_sftp() as s:
   for name,data in [('pay-gui-forward.conf',conf),('pay-gui-restore.sh',rollback)]:
    with s.open('/home/serveradmin/'+name,'wb') as f:f.write(data)
    s.chmod('/home/serveradmin/'+name,0o600)
  command(client,'arm rollback then permit only test GUI destination','set -eu; install -o root -g root -m 700 /home/serveradmin/pay-gui-restore.sh '+cleanup+'; systemd-run --unit=pay-gui-forward-rollback --on-active=30m '+cleanup+'; install -o root -g root -m 600 /home/serveradmin/pay-gui-forward.conf '+target+'; if ! sshd -t; then '+cleanup+'; exit 1; fi; sshd -T -C user=serveradmin,host=localhost,addr=127.0.0.1 | grep -E "^(allowtcpforwarding|permitopen|gatewayports|passwordauthentication|permitrootlogin) "; systemctl reload ssh')
  fresh=connect()
  try:command(fresh,'independent key login after reload','id -u')
  finally:fresh.close()
 elif sys.argv[1]=='restore':
  command(client,'restore exact temporary forwarding exception',cleanup+'; systemctl stop pay-gui-forward-rollback.timer; sshd -T -C user=serveradmin,host=localhost,addr=127.0.0.1 | grep -Fx "allowtcpforwarding no"')
 else:raise ValueError('unknown action')
finally:client.close()
