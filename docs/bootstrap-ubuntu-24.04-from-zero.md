# Bootstrap a Clean Ubuntu Server 24.04 LTS IPv4-Only VPS

This runbook builds the Discrete server baseline from a newly created Ubuntu Server 24.04 LTS VPS.
The finished host is intentionally IPv4-only. Discrete services use TCP only.

**Support status:** experimental. Debian 12 remains the clean-room validated reference. Ubuntu
24.04 must complete this entire runbook on a fresh VPS, survive a reboot, and pass an external scan
before it is marked supported.

> [!WARNING]
> Use only the Ubuntu filenames and commands from this document. Do not substitute Debian's
> `bootstrap/run.sh` or `install.sh` on an Ubuntu VPS.

> [!IMPORTANT]
> **Before opening the first SSH connection, disable X11 forwarding in the SSH client and keep it
> disabled for every session in this runbook.**
> Keep the original SSH session open until a fresh temporary-access session and a fresh
> `serveradmin` session have both been tested. Then close the temporary-access session and the
> original session, and continue from the fresh administrative session exactly as described in
> step 7. Closing the original session also removes any transient X11 listener reported by
> `prepare`. Use the VPS IPv4 address for every access test. Do not remove provider access to IPv4
> TCP `22` before `finalize` succeeds and a fresh `serveradmin` login on IPv4 TCP `22822` has been
> tested.

## Final network contract

| Item | Required state |
|---|---|
| Operating system | Ubuntu Server 24.04 LTS |
| Host network stack | IPv4-only |
| IPv6 addresses and routes | none |
| IPv6 listening sockets | none |
| OpenSSH activation | `ssh.service` enabled and active; `ssh.socket` disabled and inactive |
| Administrative SSH | IPv4 TCP `22822` |
| Direct root SSH | disabled |
| Temporary SSH port | TCP `22` closed after finalization |
| Discrete P2P | IPv4 TCP `9330` |
| Discrete RPC HTTP | IPv4 TCP `9331` |
| Discrete RPC HTTPS | IPv4 TCP `9332` |
| Host firewall inbound UDP | no inbound accept rules |
| Host firewall | nftables `table ip discrete_filter` |
| Fail2Ban | nftables `table ip f2b-table` |
| Time synchronization | client-only `systemd-timesyncd` |

Ubuntu cloud images commonly provide a non-root user such as `ubuntu` and keep the root account
locked. This bootstrap does **not** unlock root on that path. The original cloud user remains
available temporarily on TCP `22`, and its SSH public keys are copied directly to `serveradmin`
when a usable `authorized_keys` file exists.

---

# Deployment procedure

## 1. Create the VPS

Create a new VPS with:

- an Ubuntu Server 24.04 LTS release image;
- a public IPv4 address;
- provider console or recovery access;
- either direct root credentials or an SSH key assigned to the provider's initial cloud user.

Do not select a daily, development, desktop, container, or preconfigured application image.

Do **not** configure guest firewall rules manually in the provider panel. The bootstrap installs
and manages the Ubuntu host firewall through nftables. It opens the required host-side ports
itself.

### Optional provider firewall

A provider firewall is a separate network layer outside the VPS. The repository cannot create,
modify, or verify it. If no provider firewall is attached, leave the provider panel unchanged
during bootstrap.

If a provider firewall is intentionally attached during bootstrap, allow only:

| Protocol | Port | Purpose |
|---|---:|---|
| TCP | `22` | Temporary migration access |
| TCP | `22822` | Administrative SSH test and final access |
| ICMP | n/a | IPv4 diagnostics and Path MTU handling |

Do not add inbound UDP rules or IPv6 rules. Keep provider access to IPv4 TCP `22` until
`finalize` succeeds and a fresh `serveradmin` login on IPv4 TCP `22822` has been tested.

Provider rules for TCP `9330`, `9331`, and `9332` are not required for the baseline bootstrap.
Add them only after the corresponding Discrete services are installed, listening, and intended
to be reachable from the Internet.

A provider may initially assign an IPv6 address to the guest. The bootstrap removes guest IPv6
addresses and routes. Provider-side IPv6 can be disabled after the guest migration and verification
succeed.

---

## 2. Log in over IPv4

Open the first SSH connection **from your local computer**. Do not run an SSH connection command
inside another VPS shell.

Before creating the session, explicitly verify that X11 forwarding is disabled. Do not rely on a
client default or a previously saved session: an X11-enabled original connection can create a
loopback IPv6 listener that remains until the session closes.

Use the provider-supplied authentication method and choose the matching path:

| Path | Use when | Host | Username | TCP port |
|---|---|---|---|---:|
| A: direct root | the provider permits direct root login | `<VPS_IPV4>` | `root` | `22` |
| B: cloud user | the provider supplies a non-root initial user | `<VPS_IPV4>` | `<INITIAL_USER>` | `22` |

The initial cloud username is commonly `ubuntu`, but use the exact value documented by the
provider. Enter the public VPS IPv4 address literally, not a hostname.

### MobaXterm or PuTTY

Use the client's **New session** or **Session** window to create an SSH connection with the
settings for the selected path. In MobaXterm, open **Advanced SSH settings** and clear
**X11-forwarding**. In PuTTY, open **Connection > SSH > X11** and clear
**Enable X11 forwarding**. Authenticate with the provider password or the private key assigned
when the VPS was created.

### OpenSSH from a local terminal

Open PowerShell, Command Prompt, Windows Terminal, a macOS or Linux terminal, or the local terminal
in MobaXterm.

For Path A, run:

```bash
ssh -4 -o ForwardX11=no -p 22 root@<VPS_IPV4>
```

For Path B, replace `<INITIAL_USER>` and run:

```bash
ssh -4 -o ForwardX11=no -p 22 <INITIAL_USER>@<VPS_IPV4>
```

On the first connection, SSH may ask you to confirm the server host key. Compare its fingerprint
with the provider's value when one is available.

### Enter and verify a root shell

For Path A, run inside the VPS session:

```bash
whoami
```

For Path B, run inside the VPS session:

```bash
whoami
sudo -i
whoami
```

For Path A, `whoami` must print `root`. For Path B, the first `whoami` must print the exact initial
username and the final `whoami` must print `root`.

This first connection is called the **original SSH terminal** in later steps. On Path B, remember
the exact initial username; step 5 passes it through `BOOTSTRAP_SOURCE_USER`.

Keep the original SSH terminal open until both fresh-login tests have succeeded in step 7.

Some SSH clients, including MobaXterm configurations, may request X11 forwarding automatically.
The bootstrap disables X11 forwarding for all new sessions. A loopback-only listener such as
`[::1]:6010` may nevertheless remain attached to the original session until that session closes.

---

## 3. Wait for first-boot provisioning

Ubuntu cloud images may still be running cloud-init after the first SSH login. Do not race it while
it is configuring packages, networking, or SSH.

From the root shell in the original SSH terminal:

```bash
if command -v cloud-init >/dev/null 2>&1; then
  cloud-init status --wait
fi
```

Continue only after cloud-init reaches a completed state. If it reports an error, stop and collect:

```bash
cloud-init status --long
journalctl -u cloud-init-local -u cloud-init -u cloud-config -u cloud-final --no-pager
```

Do not continue until the provider image has completed first-boot provisioning successfully.

---

## 4. Verify Ubuntu 24.04, install Git, and clone the public repository

Confirm the provider created the requested operating system before changing the host:

```bash
. /etc/os-release
printf 'ID=%s VERSION_ID=%s\n' "$ID" "$VERSION_ID"
```

Required output: `ID=ubuntu VERSION_ID=24.04`.

Install Git and the CA certificate bundle:

```bash
apt-get update
apt-get install -y ca-certificates git
```

Clone the public repository anonymously over HTTPS:

```bash
git clone \
  https://github.com/MatthewFreeman/discrete-infrastructure.git \
  /opt/discrete-infrastructure

cd /opt/discrete-infrastructure
```

A GitHub account, personal access token, deploy key, username, and password are not required.
Do not configure a Git credential helper on the VPS.

Before running any repository code, verify the checkout:

```bash
cd /opt/discrete-infrastructure

git remote get-url origin
git status --short --branch
```

The first command must print
`https://github.com/MatthewFreeman/discrete-infrastructure.git`. The second command must print
exactly one line: `## main...origin/main`. Do not run `prepare` if the URL or branch differs, if
the branch reports that it is ahead or behind, or if any additional line reports a modified,
staged, or untracked file.

---

## 5. Run the Ubuntu `prepare` phase

Use only the command for the login path selected in step 2.

### Path A: original login was direct root

```bash
cd /opt/discrete-infrastructure

ADMIN_USER=serveradmin \
  bash bootstrap/run-ubuntu-24.04.sh prepare
```

### Path B: original login used a cloud user

Replace `<INITIAL_USER>` with the exact provider username:

```bash
cd /opt/discrete-infrastructure

BOOTSTRAP_SOURCE_USER=<INITIAL_USER> \
ADMIN_USER=serveradmin \
  bash bootstrap/run-ubuntu-24.04.sh prepare
```

When `serveradmin` is created for the first time, `prepare` pauses and asks for a password:

- at `New password:`, enter a strong password; the terminal deliberately displays no characters
  while you type;
- at `Retype new password:`, enter the same password again.

Store this password securely. Step 7 uses it for the first `sudo` check and as an SSH fallback.
On Path B, the script also copies the initial user's SSH public keys to `serveradmin` when a usable
`authorized_keys` file exists.

The script will:

1. require exactly Ubuntu 24.04;
2. verify the canonical Git origin, a clean working tree, and anonymous HTTPS access;
3. wait for provider package-manager activity and install required packages;
4. install the Ubuntu IPv4 reassertion service;
5. disable `ssh.socket` and enable regular `ssh.service`;
6. apply the managed IPv4-only sysctl policy;
7. remove all guest IPv6 addresses and routes;
8. reject every IPv6 listener except a loopback-only `sshd` X11 listener belonging to the
   already-open original session;
9. disable X11 forwarding for all new SSH sessions;
10. configure client-only `systemd-timesyncd` and verify that no process listens on UDP `123`;
11. create `serveradmin` and add it to `sudo`;
12. on Path B, copy the initial user's SSH public keys directly to `serveradmin` when available;
13. keep the selected temporary access user on IPv4 TCP `22`;
14. enable `serveradmin` on IPv4 TCP `22822`;
15. activate the temporary IPv4 two-port nftables policy;
16. remove UFW and residual UFW tables;
17. configure IPv4-only Fail2Ban for TCP `22` and TCP `22822`.

The bootstrap waits for up to five minutes when provider processes such as cloud-init or
`unattended-upgrades` hold APT or dpkg locks. Lock-wait or retry messages during this period are
expected. Do not kill package-manager processes or delete lock files.

The final banner must begin with **PREPARE PHASE COMPLETE**. Every row below is common to both
paths unless the following path-specific table overrides it:

| Field | Required value |
|---|---|
| Network stack | `IPv4 only` |
| IPv6 addresses/routes | `none` |
| IPv6 listeners | `none` |
| SSH ports | `22 and 22822` |
| Administrative user | `serveradmin` |
| Firewall | `ip discrete_filter` |
| UFW | `removed` |
| Fail2Ban table | `ip f2b-table` |
| Fail2Ban SSH ports | `22 and 22822` |
| Time synchronization | `systemd-timesyncd client` |
| UDP 123 listener | `none` |
| Repository access | `public anonymous HTTPS` |

Path-specific rows must be:

| Field | Path A: direct root | Path B: cloud user |
|---|---|---|
| Temporary SSH user | `root on TCP 22` | `<INITIAL_USER> on TCP 22` |
| Root SSH login | `temporarily allowed` | `disabled; root account remains locked` |

`IPv6 listeners` may instead report
`transient loopback X11; close original session before finalize`.

Look for this line in the final banner printed in the original SSH terminal where step 5 ran
`prepare`. The fresh login commands in step 7 do not print this status. If the line appears, note
it and keep the original SSH terminal open. Step 7 tells you exactly when to close it, after both
fresh SSH access paths have been tested.

Do not run `finalize` yet.

### If `prepare` stops before the final banner

Keep the original SSH terminal open and do not continue to the next deployment step. Save the
complete `prepare` output, especially the first `ERROR:` line, and collect:

```bash
cd /opt/discrete-infrastructure

journalctl -u ssh.service -u ssh.socket -u nftables -u fail2ban -u systemd-timesyncd \
  -n 200 --no-pager

ss -4 -H -lntup
ss -6 -H -lntup
nft list ruleset
```

After the repository implementation has been corrected, update the checkout:

```bash
cd /opt/discrete-infrastructure
git pull --ff-only
```

Then rerun the same Path A or Path B `prepare` command documented above. Re-running `prepare`
before `finalize` is supported. Returning to the shell prompt without the final banner is a failed
phase even when no `ERROR:` line was printed.

---

## 6. Verify anonymous repository access

Verify that the checkout can read the public repository without credentials:

```bash
GIT_TERMINAL_PROMPT=0 git ls-remote \
  https://github.com/MatthewFreeman/discrete-infrastructure.git \
  HEAD
```

Expected result: a commit SHA followed by `HEAD`, without a username, password, token, or SSH-key
prompt. Do not continue if anonymous HTTPS access fails.

---

## 7. Test both fresh IPv4 SSH access paths

Do not close the original SSH terminal.

Using the same local SSH client method described in step 2, create two **additional** SSH
connections from your local computer. Do not run an SSH connection command inside the original
VPS shell or any other existing VPS session.

Use these settings for the selected path:

| Session name used below | Path | Host | Username | TCP port |
|---|---|---|---|---:|
| Fresh temporary-access test | A | `<VPS_IPV4>` | `root` | `22` |
| Fresh temporary-access test | B | `<VPS_IPV4>` | `<INITIAL_USER>` | `22` |
| Fresh administrative | A or B | `<VPS_IPV4>` | `serveradmin` | `22822` |

Enter the VPS IPv4 address literally, not a hostname. Before opening either connection, recheck
that X11 forwarding is disabled in each new or saved client session. Keep both connections in
separate local windows or tabs.

- **MobaXterm or PuTTY:** create one new GUI session for the matching temporary-access row and one
  for the administrative row.
- **OpenSSH:** open two new local terminals. In the temporary-access terminal, run the matching
  command:

  Path A:

  ```bash
  ssh -4 -o ForwardX11=no -p 22 root@<VPS_IPV4>
  ```

  Path B:

  ```bash
  ssh -4 -o ForwardX11=no -p 22 <INITIAL_USER>@<VPS_IPV4>
  ```

  In the fresh administrative terminal, run:

  ```bash
  ssh -4 -o ForwardX11=no -p 22822 serveradmin@<VPS_IPV4>
  ```

Use the copied SSH key or the password created during step 5 for the `serveradmin` login.

Inside the fresh temporary-access session, run:

```bash
whoami
```

For Path A, the result must be `root`. For Path B, it must be the exact initial username.

Inside the fresh administrative session:

```bash
whoami
sudo -v
sudo -i
whoami
```

The first `whoami` must print `serveradmin`; the final `whoami` must print `root`. When `sudo -v`
asks for a password, enter the `serveradmin` password created during step 5. The terminal
deliberately displays no characters while you type it.

Do not continue until both fresh IPv4 SSH sessions work.

From the root shell inside the fresh administrative session, verify Ubuntu's SSH activation mode:

```bash
printf 'ssh.service enabled: '; systemctl is-enabled ssh.service
printf 'ssh.service active:  '; systemctl is-active ssh.service
printf 'ssh.socket enabled:  '; systemctl is-enabled ssh.socket || true
printf 'ssh.socket active:   '; systemctl is-active ssh.socket || true
sshd -T | grep -E '^(addressfamily|port|permitrootlogin) '
ss -6 -H -lntup
```

Required state:

| Check | Path A | Path B |
|---|---|---|
| `ssh.service enabled` | `enabled` | `enabled` |
| `ssh.service active` | `active` | `active` |
| `ssh.socket enabled` | `disabled` | `disabled` |
| `ssh.socket active` | `inactive` | `inactive` |
| `addressfamily` | `inet` | `inet` |
| `port` | both `22` and `22822` | both `22` and `22822` |
| `permitrootlogin` | `yes` | `no` |
| `ss -6 -H -lntup` | no output | no output |

If the IPv6 check shows only a transient loopback `sshd` X11 listener belonging to the original
session, continue with the session cleanup immediately below. Any other IPv6 listener is a failure.

After both fresh SSH access tests have succeeded, three SSH terminals are open:

1. the **original SSH terminal** that ran `prepare`;
2. the **fresh temporary-access test terminal** on IPv4 TCP `22`;
3. the **fresh `serveradmin` terminal** on IPv4 TCP `22822`, currently in a root login shell because
   `sudo -i` was run above.

Before continuing, leave only the fresh `serveradmin` terminal open:

1. Keep the fresh `serveradmin` terminal on TCP `22822` open.
2. Close the fresh temporary-access test terminal on TCP `22`.
3. Close the original SSH terminal that ran `prepare`. It is now safe to close because both fresh
   access paths have been tested.
4. Return to the remaining `serveradmin` terminal and verify its current state:

   ```bash
   whoami
   ss -6 -H -lntup
   ```

   `whoami` must print `root`, and the `ss` command must print nothing. If `whoami` does not print
   `root`, run `sudo -i` and repeat both checks.

Do not continue unless the `serveradmin` terminal remains connected, `whoami` prints `root`, and
`ss -6 -H -lntup` prints nothing.

> **Why closing the original terminal matters:** If `prepare` reported a transient X11 listener,
> that listener belongs to the original SSH session and disappears when the session closes. New
> sessions cannot recreate it because the managed SSH configuration sets `X11Forwarding no`.

---

## 8. Run the Ubuntu `finalize` phase

Continue in the same fresh `serveradmin` terminal retained at the end of step 7. That terminal is
already connected over IPv4 TCP `22822`, and step 7 confirmed that it is in a root login shell.

Verify the current user:

```bash
whoami
```

The result must be `root`. If it is not, run `sudo -i` and verify again.

From the verified root shell:

```bash
cd /opt/discrete-infrastructure

ADMIN_USER=serveradmin \
  bash bootstrap/run-ubuntu-24.04.sh finalize
```

When prompted to confirm the administrative SSH test, type `serveradmin`.

The script will:

1. revalidate Ubuntu 24.04 and the IPv4-only host state;
2. enforce `ssh.service` mode and revalidate client-only time synchronization;
3. verify that UFW is absent;
4. verify both temporary IPv4 SSH firewall rules;
5. verify anonymous HTTPS access to the public repository;
6. require confirmation of the administrative SSH test;
7. apply final IPv4-only SSH on TCP `22822`;
8. disable direct root SSH and remove temporary TCP `22` access;
9. apply the final IPv4 nftables and Fail2Ban policies;
10. run the complete final-state verification;
11. write the finalized-state marker only after every check passes.

The final banner must begin with **BOOTSTRAP FINALIZED** and report:

| Field | Required value |
|---|---|
| Network stack | `IPv4 only` |
| IPv6 addresses/routes | `none` |
| IPv6 listeners | `none` |
| Administrative SSH | `serveradmin@server:22822` |
| Direct root SSH | `disabled` |
| Temporary SSH port | `closed` |
| Firewall | `ip discrete_filter` |
| UFW | `absent` |
| Fail2Ban table | `ip f2b-table` |
| Fail2Ban | `active` |
| Time synchronization | `systemd-timesyncd client` |
| UDP 123 listener | `none` |
| Git origin | `https://github.com/MatthewFreeman/discrete-infrastructure.git` |

### If `finalize` stops before the final banner

Keep the current `serveradmin` terminal open. Do not reboot, disconnect, rerun `finalize`, or
continue to step 9. The phase may already have changed SSH or firewall state, so the correct
recovery depends on where it stopped.

From the same root shell, collect:

```bash
cd /opt/discrete-infrastructure

ADMIN_USER=serveradmin \
  bash bootstrap/run-ubuntu-24.04.sh status --verbose

./scripts/audit-ports.sh --verbose

journalctl -u ssh.service -u ssh.socket -u nftables -u fail2ban \
  -n 200 --no-pager
```

These commands may report failures because finalization is incomplete; that output is diagnostic.
Save the complete `finalize` output, especially the first `ERROR:` line, together with all three
diagnostic outputs. Use them to correct the repository implementation or obtain failure-specific
recovery instructions before running `finalize` again. If the SSH connection drops, use the
provider console or recovery access instead of repeatedly attempting SSH.

---

## 9. Perform final access tests

Keep the existing `serveradmin` terminal that ran `finalize` open until a fresh post-finalization
login has succeeded.

From your local computer, create one **additional** SSH connection using the same client method
introduced in step 2:

| Session name used below | Host | Username | TCP port |
|---|---|---|---:|
| Fresh post-finalization admin | `<VPS_IPV4>` | `serveradmin` | `22822` |

- **MobaXterm or PuTTY:** create a new GUI session with the settings in the table.
- **OpenSSH:** open a new local terminal and run:

  ```bash
  ssh -4 -o ForwardX11=no -p 22822 serveradmin@<VPS_IPV4>
  ```

Inside the fresh post-finalization administrative session:

```bash
whoami
sudo -i
whoami
```

The first `whoami` must print `serveradmin`; the final `whoami` must print `root`.

### Confirm that direct root SSH is denied

From another new local window or tab, attempt a connection with these settings:

| Host | Username | TCP port |
|---|---|---:|
| `<VPS_IPV4>` | `root` | `22822` |

- **MobaXterm or PuTTY:** create a temporary GUI session with the settings in the table.
- **OpenSSH:** run from a new local terminal:

  ```bash
  ssh -4 -o ForwardX11=no -o ConnectTimeout=5 -o NumberOfPasswordPrompts=1 -p 22822 root@<VPS_IPV4>
  ```

The test passes only if no root shell opens. An authentication error such as `Permission denied`
is expected. A successful root shell is a failed test.

### Confirm that temporary TCP port 22 is closed

From your local computer:

- **MobaXterm or PuTTY:** attempt a temporary SSH session to `<VPS_IPV4>` on TCP `22`; it must not
  open a shell.
- **OpenSSH:** run from a new local terminal:

  ```bash
  ssh -4 -o ForwardX11=no -o ConnectTimeout=5 -p 22 serveradmin@<VPS_IPV4>
  ```

  The connection must be refused or time out without opening a shell.
- **PowerShell, optional numeric check:**

  ```powershell
  Test-NetConnection <VPS_IPV4> -Port 22
  Test-NetConnection <VPS_IPV4> -Port 22822
  ```

  `TcpTestSucceeded` must be `False` for TCP `22` and `True` for TCP `22822`.

Inside the fresh post-finalization administrative session, confirm Ubuntu's activation mode:

```bash
printf 'ssh.service enabled: '; systemctl is-enabled ssh.service
printf 'ssh.service active:  '; systemctl is-active ssh.service
printf 'ssh.socket enabled:  '; systemctl is-enabled ssh.socket || true
printf 'ssh.socket active:   '; systemctl is-active ssh.socket || true
```

The four results must be `enabled`, `active`, `disabled`, and `inactive`, in that order.

After all tests succeed:

1. Keep the fresh post-finalization `serveradmin` terminal open; it is already in a root login
   shell.
2. Close the older `serveradmin` terminal that ran `finalize` and close the failed root/port-22
   test windows.
3. Continue with step 10 in the remaining fresh post-finalization terminal.

The root account is not unlocked on the cloud-user path. Root remains available through `sudo -i`,
the provider console or recovery environment, and provider password-reset facilities when offered.

---

## 10. Run final verification and the local port audit

Continue in the fresh post-finalization `serveradmin` terminal retained at the end of step 9. It
must still be in a root login shell. Confirm before continuing:

```bash
whoami
```

The result must be `root`.

Run the human-readable final status:

```bash
cd /opt/discrete-infrastructure

ADMIN_USER=serveradmin \
  bash bootstrap/run-ubuntu-24.04.sh status
```

The command checks, in order:

1. the finalized-state marker;
2. the canonical Git origin;
3. the administrative user and `sudo` access;
4. the IPv4-only network state;
5. SSH configuration and listeners;
6. the nftables firewall and UFW removal;
7. Fail2Ban configuration;
8. time synchronization and UDP `123`;
9. the Git working tree.

Every row must begin with `[PASS]`, and the final line must be `Overall status: PASS`. If a check
fails, `[FAIL]` appears in the expected position and its diagnostic is printed immediately below
it. Do not continue until every check passes.

Run the readable listening-port audit:

```bash
cd /opt/discrete-infrastructure

./scripts/audit-ports.sh
```

The clean-baseline results are:

| Check | Required result |
|---|---|
| Public TCP listeners | `sshd` on IPv4 TCP `22822` only |
| Temporary SSH port | no listener on TCP `22` |
| NTP server port | no listener on IPv4 UDP `123` |
| Public UDP listeners | none, or only the provider DHCP exception on UDP `68` |
| IPv6 interface policy | disabled on every current and future interface scope |
| IPv6 addresses, routes, and listeners | none |
| nftables tables | exactly `table ip discrete_filter` and `table ip f2b-table` |
| Firewall default policy | `drop` |
| Firewall TCP allowlist | only `22822`, `9330`, `9331`, and `9332` |

All 11 automated pass/fail checks must begin with `[PASS]`, and `Checks passed` must report
`11/11`. Additional `[INFO]` rows may appear; they provide context and are not included in the
passed-check count. A provider DHCP client listening on UDP `68` is one such informational note.
The summary must end with `IPv4-only verification passed.` and `Port audit result: PASS`.

For low-level troubleshooting only, use:

```bash
cd /opt/discrete-infrastructure

ADMIN_USER=serveradmin \
  bash bootstrap/run-ubuntu-24.04.sh status --verbose

./scripts/audit-ports.sh --verbose
```

This local audit does not prove provider-firewall behavior or Internet reachability. Step 12 tests
those from a separate external host.

---

## 11. Reboot validation

Reboot only after every check in steps 9 and 10 passes. The current SSH connection will close:

```bash
reboot
```

Wait for the VPS to return. From your local computer, open a fresh `serveradmin` connection using
the same MobaXterm, PuTTY, or OpenSSH method described earlier:

```bash
ssh -4 -o ForwardX11=no -p 22822 serveradmin@<VPS_IPV4>
```

Inside the VPS session:

```bash
sudo -i
whoami
cd /opt/discrete-infrastructure

ADMIN_USER=serveradmin \
  bash bootstrap/run-ubuntu-24.04.sh status

./scripts/audit-ports.sh

printf 'ssh.service active: '; systemctl is-active ssh.service
printf 'ssh.socket active:  '; systemctl is-active ssh.socket || true
ss -6 -H -lntup
```

Required results:

- `whoami` prints `root`;
- every status row and all 11 audit pass/fail rows begin with `[PASS]`;
- any `[INFO]` audit rows are informational and do not count as checks;
- the audit reports `Checks passed: 11/11`;
- the summaries end with `Overall status: PASS` and `Port audit result: PASS`;
- `ssh.service active` is `active`;
- `ssh.socket active` is `inactive`;
- `ss -6 -H -lntup` prints nothing.

Do not continue if the post-reboot login or any verification fails.

---

## 12. Run an external IPv4 scan

Run this step from a different Internet-connected computer, **not from the VPS itself**. Use a
local terminal with Nmap installed, such as PowerShell, Windows Terminal, a macOS or Linux terminal,
or MobaXterm's local terminal. A trusted external port-scanning service is also acceptable when it
can scan the complete TCP range and the specific ports below.

Scan every TCP port:

```bash
nmap -Pn -4 -p- <VPS_IPV4>
```

Before Discrete services are installed, the only open TCP port must be `22822/tcp`.

Verify the intended ports explicitly:

```bash
nmap -Pn -4 -p 22,22822,9330-9332 <VPS_IPV4>
```

Required result:

| Port | Required external state before Discrete is installed |
|---:|---|
| `22` | closed or filtered |
| `22822` | open |
| `9330`–`9332` | closed or filtered because no service is listening |

Provider-firewall behavior and Internet reachability can be proven only by this external test.
Save the scan output as clean-room validation evidence.

---

## 13. Normal future Ubuntu updates

Repeat this procedure whenever the repository contains an approved infrastructure update.

> [!IMPORTANT]
> After establishing the SSH connection, run all remaining commands **inside the VPS session**,
> not in a local PowerShell, Command Prompt, or MobaXterm local terminal. Run update commands from
> a root login shell, not as the unprivileged `serveradmin` user.

### Open a fresh administrative SSH session

Connect from your local computer using the same SSH client method introduced in step 2:

| Host | Username | TCP port |
|---|---|---:|
| `<VPS_IPV4>` | `serveradmin` | `22822` |

- **MobaXterm or PuTTY:** open the saved administrative session, or create one with the settings in
  the table.
- **OpenSSH:** open a new local terminal and run:

  ```bash
  ssh -4 -o ForwardX11=no -p 22822 serveradmin@<VPS_IPV4>
  ```

### Enter and verify a root login shell

Inside the new VPS session:

```bash
sudo -i
whoami
```

Required result: `root`. Do not continue if `whoami` prints anything else.

### Pull and apply the update

From the verified root shell:

```bash
cd /opt/discrete-infrastructure
git pull --ff-only
./install-ubuntu-24.04.sh
```

`git pull` must use anonymous read-only HTTPS and must not request a GitHub username, password,
token, or SSH key. Stop if the pull is not a fast-forward or if the installer reports an error.
Do not use Debian's `install.sh` as the Ubuntu update path.

### Run final status and the readable port audit

After the installer succeeds:

```bash
cd /opt/discrete-infrastructure

ADMIN_USER=serveradmin \
  bash bootstrap/run-ubuntu-24.04.sh status

./scripts/audit-ports.sh
```

Every status row and all 11 audit pass/fail rows must begin with `[PASS]`. Additional `[INFO]`
audit rows may appear and do not count as checks. The audit must report `Checks passed: 11/11`,
and the summaries must end with `Overall status: PASS` and `Port audit result: PASS`. If a check
fails, collect low-level diagnostics with `status --verbose` and `audit-ports.sh --verbose`
before changing anything else.

Do not close the working administrative session until the update, status, and audit all succeed.

### Operating rules

- Edit and commit managed configuration on GitHub or a trusted workstation, not directly on the
  VPS.
- Never edit Git-managed files under `/etc` except during emergency recovery.
- Keep the VPS checkout read-only: future updates must continue to use anonymous HTTPS pulls.
- Keep `ssh.service` enabled and `ssh.socket` disabled; the Ubuntu installer enforces this mode.

---

# Gate before marking Ubuntu supported

Ubuntu remains experimental until a newly created VPS records all of the following:

- cloud-init completes without error;
- `prepare` reaches the correct Path A or Path B banner;
- the selected temporary TCP `22` login works;
- a fresh `serveradmin` TCP `22822` login and `sudo -i` work;
- `ssh.service` is enabled and active while `ssh.socket` is disabled and inactive;
- `finalize` reaches its final banner;
- a fresh post-finalization `serveradmin` login works;
- direct root SSH is denied and TCP `22` is closed;
- final status and the local port audit pass;
- the VPS survives a reboot and every final check still passes;
- the external scan matches the intended exposure.

Only then change Ubuntu from `experimental` to `supported` in
[`bootstrap-platforms.md`](bootstrap-platforms.md).

---

# Safety and recovery behavior

The bootstrap is deliberately two-phase. Disabling IPv6 does not alter the existing IPv4 address
or the current IPv4 SSH transport. An SSH session that requested X11 forwarding before IPv6 was
disabled may retain a loopback-only `[::1]:60xx` proxy listener until that session closes.
`prepare` tolerates only that narrow transient case and disables X11 forwarding for every new
session. `finalize` remains strict and requires all IPv6 listeners to be gone.

On Path B, the bootstrap does not unlock root or require direct root SSH. The original cloud user
remains the temporary TCP `22` access path until finalization.

The managed SSH configuration is validated before reload. If final SSH runtime validation fails,
the script restores the temporary IPv4 SSH configuration. The finalized-state marker is not
written unless every final check passes.

---

# Implementation notes

<details>
<summary><strong>Ubuntu OpenSSH activation mode</strong></summary>

Ubuntu 24.04 cloud images commonly use `ssh.socket`. The bootstrap disables socket activation and
enables `ssh.service` because the migration must manage two temporary ports and one final port
deterministically. The Ubuntu update installer reapplies this service mode before managed
configuration is installed.

</details>

<details>
<summary><strong>Initial cloud-user key transfer</strong></summary>

When `BOOTSTRAP_SOURCE_USER` names the provider's initial non-root account, the bootstrap copies a
non-empty `authorized_keys` file directly into `serveradmin`'s home with the correct ownership and
permissions. It does not unlock root or depend on a root SSH key. The `serveradmin` password remains
available for `sudo` and as an SSH fallback while password authentication is enabled.

</details>

<details>
<summary><strong>IPv4 policy reassertion</strong></summary>

The Ubuntu entrypoint installs a platform-specific boot service before `prepare` and `finalize`.
That service reapplies the managed IPv4-only sysctl policy and removes guest IPv6 addresses and
routes after Ubuntu networking has initialized. The future-update installer also reconciles this
service before applying shared managed configuration.

</details>

<details>
<summary><strong>Shared managed components</strong></summary>

Ubuntu reuses the common SSH policy, nftables rules, Fail2Ban configuration, deployment, rollback,
audit, and verification logic. The platform-specific entrypoints add Ubuntu release validation,
OpenSSH service activation, cloud-user key handling, and post-network IPv4 reassertion.

</details>
