# Bootstrap a Clean Debian 12 IPv4-Only VPS

This runbook builds the standard Discrete server baseline from a newly created Debian 12 VPS.
The finished host is intentionally IPv4-only. Discrete services use TCP only.

> [!IMPORTANT]
> **Before opening the first SSH connection, disable X11 forwarding in the SSH client and keep it
> disabled for every session in this runbook.**
> Keep the original root SSH session open until fresh root and `serveradmin` IPv4 sessions have
> been tested. Then close both root sessions and continue from the fresh administrative session,
> exactly as described in step 6. Closing the original session also removes any transient X11
> listener reported by `prepare`. Use the VPS IPv4 address for every access test.
> Do not remove provider access to IPv4 TCP `22` before `finalize` succeeds and a fresh
> `serveradmin` login on IPv4 TCP `22822` has been tested.

## Final network contract

| Item | Required state |
|---|---|
| Host network stack | IPv4-only |
| IPv6 addresses and routes | none |
| IPv6 listening sockets | none |
| SSH | IPv4 TCP `22822` |
| Discrete P2P | IPv4 TCP `9330` |
| Discrete RPC HTTP | IPv4 TCP `9331` |
| Discrete RPC HTTPS | IPv4 TCP `9332` |
| Host firewall inbound UDP | no inbound accept rules |
| Host firewall | nftables `table ip discrete_filter` |
| Fail2Ban | nftables `table ip f2b-table` |
| Time synchronization | client-only `systemd-timesyncd` |

The bootstrap installs and configures:

- base packages;
- the `serveradmin` administrative account;
- temporary root SSH on IPv4 TCP `22`;
- administrative SSH on IPv4 TCP `22822`;
- IPv6 disabled on every current and future interface;
- OpenSSH restricted to `AddressFamily inet`;
- nftables as the only host firewall, using the IPv4 `ip` family;
- removal of UFW and residual UFW tables;
- IPv4-only Fail2Ban protection;
- client-only time synchronization through `systemd-timesyncd`;
- removal of NTP server daemons that listen on UDP `123`;
- anonymous read-only access to the public GitHub repository over HTTPS;
- Git-managed deployment, rollback, audit, and verification.

The bootstrap does **not** create the VPS itself. Provider plans, regions, IPv4 addresses,
recovery consoles, snapshots, and provider-side firewall rules remain provider-specific.

---

# Deployment procedure

## 1. Create the VPS

Create a new VPS with:

- Debian 12;
- a public IPv4 address;
- provider console or recovery access.

Do **not** configure guest firewall rules manually in the provider panel as part of this step.
The bootstrap installs and manages the Debian host firewall through nftables. It opens the
required host-side ports itself.

### Optional provider firewall

A provider firewall is a separate network layer outside the VPS. The repository cannot create,
modify, or verify it. If no provider firewall is attached to the VPS, leave the provider panel
unchanged during bootstrap.

If a provider firewall is intentionally attached during bootstrap, allow only:

| Protocol | Port | Purpose |
|---|---:|---|
| TCP | `22` | Temporary root SSH during bootstrap |
| TCP | `22822` | Administrative SSH test and final access |
| ICMP | n/a | IPv4 diagnostics and Path MTU handling |

Do not add inbound UDP rules or IPv6 rules. Keep provider access to IPv4 TCP `22` until
`finalize` succeeds and a fresh `serveradmin` login on IPv4 TCP `22822` has been tested.

Provider rules for TCP `9330`, `9331`, and `9332` are not required for the baseline bootstrap.
Add them only after the corresponding Discrete services are installed, listening, and intended
to be reachable from the Internet.

A provider may initially assign an IPv6 address to the guest. The bootstrap removes guest
IPv6 addresses and routes. Provider-side IPv6 can be disabled after the guest migration and
verification succeed.

---

## 2. Log in as root over IPv4

Open the first SSH connection **from your local computer**. Do not run an SSH connection command
inside another VPS shell.

Before creating the session, explicitly verify that X11 forwarding is disabled. Do not rely on a
client default or a previously saved session: an X11-enabled original connection can create a
loopback IPv6 listener that remains until the session closes.

Use the provider-supplied authentication method and these connection settings:

| Host | Username | TCP port |
|---|---|---:|
| `<VPS_IPV4>` | `root` | `22` |

Enter the public VPS IPv4 address literally, not a hostname. Choose one of the two methods below.
Whichever method you use, this first connection is called the **original root terminal** in later
steps.

### MobaXterm or PuTTY

Use the client's **New session** or **Session** window to create an SSH connection with the
settings in the table. In MobaXterm, open **Advanced SSH settings** and clear **X11-forwarding**.
In PuTTY, open **Connection > SSH > X11** and clear **Enable X11 forwarding**. Authenticate with
the password supplied by the provider, or select the private key used when the VPS was created.

### OpenSSH from a local terminal

Open PowerShell, Command Prompt, Windows Terminal, a macOS or Linux terminal, or the local
terminal in MobaXterm, and run:

```bash
ssh -4 -o ForwardX11=no -p 22 root@<VPS_IPV4>
```

Authenticate with the password supplied by the provider. If the VPS was created with an SSH key,
use the matching private key instead. On the first connection, SSH may also ask you to confirm the
server host key; compare its fingerprint with the provider's value when one is available.

Keep the original root terminal open until fresh root and `serveradmin` IPv4 sessions have been
tested in step 6.

Some SSH clients, including MobaXterm configurations, may request X11 forwarding automatically.
The bootstrap disables X11 forwarding for all new sessions. A loopback-only listener such as
`[::1]:6010` may nevertheless remain attached to the original session until that session closes.
The `prepare` phase treats only an existing `sshd` listener on `[::1]:6000` through
`[::1]:6063` as a temporary migration exception; every other IPv6 listener is an error.

---

## 3. Verify Debian 12, install Git, and clone the public repository

Confirm the provider created the requested operating system before changing the host:

```bash
. /etc/os-release
printf 'ID=%s VERSION_ID=%s VERSION_CODENAME=%s\n' \
  "$ID" "$VERSION_ID" "$VERSION_CODENAME"
```

Required output: `ID=debian VERSION_ID=12 VERSION_CODENAME=bookworm`.

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

## 4. Run the `prepare` phase

```bash
cd /opt/discrete-infrastructure

ADMIN_USER=serveradmin \
  bash bootstrap/run.sh prepare
```

When `serveradmin` is created for the first time, `prepare` pauses and asks for a password:

- at `New password:`, enter a strong password; the terminal deliberately displays no characters
  while you type;
- at `Retype new password:`, enter the same password again.

Store this password securely. Step 6 uses it for the fresh `serveradmin` login and the first
`sudo` check.

The script will:

1. validate Debian 12;
2. verify the canonical Git origin, a clean working tree, and anonymous HTTPS access;
3. wait for provider package-manager activity and install required packages;
4. install and apply the managed IPv4-only sysctl policy;
5. remove all guest IPv6 addresses and routes;
6. reject every IPv6 listener except a loopback-only `sshd` X11 listener on `[::1]:6000`
   through `[::1]:6063` that belongs to the already-open original SSH session;
7. disable X11 forwarding for all new SSH sessions;
8. remove `ntp`, `ntpsec`, `chrony`, and `openntpd` when installed;
9. install and enable client-only `systemd-timesyncd`;
10. verify that the clock is synchronized and no process listens on UDP `123`;
11. create `serveradmin`, set its password interactively when needed, and add it to `sudo`;
12. keep root SSH on IPv4 TCP `22`;
13. enable admin SSH on IPv4 TCP `22822`;
14. activate the temporary IPv4 two-port nftables policy;
15. remove UFW and residual UFW tables;
16. configure IPv4-only Fail2Ban for TCP `22` and TCP `22822`.

The bootstrap waits for up to five minutes when provider processes such as
`unattended-upgrades` hold APT or dpkg locks. Lock-wait or retry messages during this
period are expected. Do not kill package-manager processes or delete lock files.

The final banner must begin with **PREPARE PHASE COMPLETE** and report:

| Field | Required value |
|---|---|
| Network stack | `IPv4 only` |
| IPv6 addresses/routes | `none` |
| IPv6 listeners | `none` |
| SSH ports | `22 and 22822` |
| Administrative user | `serveradmin` |
| Root SSH login | `temporarily allowed` |
| Firewall | `ip discrete_filter` |
| UFW | `removed` |
| Fail2Ban table | `ip f2b-table` |
| Fail2Ban SSH ports | `22 and 22822` |
| Time synchronization | `systemd-timesyncd client` |
| UDP 123 listener | `none` |
| Repository access | `public anonymous HTTPS` |

`IPv6 listeners` may instead report
`transient loopback X11; close original session before finalize`.

Look for this line in the final `PREPARE PHASE COMPLETE` banner printed in the original root
terminal where step 4 ran `bash bootstrap/run.sh prepare`. The fresh login commands in step 6 do
not print this status. If the line appears, note it and keep the original root terminal open.
Step 6 tells you exactly when to close it, after both fresh SSH access paths have been tested.

Do not run `finalize` yet.

### If `prepare` stops before the final banner

Do not continue to the next deployment step. After the repository implementation has been
corrected, update the checkout and rerun the same documented phase:

```bash
cd /opt/discrete-infrastructure

git pull --ff-only

ADMIN_USER=serveradmin \
  bash bootstrap/run.sh prepare
```

`git pull` must not prompt for credentials. Re-running `prepare` before `finalize` is supported.

Returning to the shell prompt without the final banner is a failed phase even when no `ERROR:` line
was printed. Do not continue.

---

## 5. Verify anonymous repository access

Verify that the checkout can read the public repository without credentials:

```bash
GIT_TERMINAL_PROMPT=0 git ls-remote \
  https://github.com/MatthewFreeman/discrete-infrastructure.git \
  HEAD
```

Expected result: a commit SHA followed by `HEAD`, without a username, password, token, or SSH-key
prompt. Do not continue if anonymous HTTPS access fails.

---

## 6. Test both IPv4 SSH access paths

Do not close the original root terminal.

Using the same local SSH client method described in step 2, create two **additional** SSH
connections from your local computer. Do not run an SSH connection command inside the original
VPS shell or any other existing VPS session.

Use these connection settings:

| Session name used below | Host | Username | TCP port |
|---|---|---|---:|
| Fresh root test | `<VPS_IPV4>` | `root` | `22` |
| Fresh administrative | `<VPS_IPV4>` | `serveradmin` | `22822` |

Enter the VPS IPv4 address literally, not a hostname. Before opening either connection, recheck
that X11 forwarding is disabled in each new or saved client session. Keep both connections in
separate local windows or tabs.

- **MobaXterm or PuTTY:** create one new GUI session for each row in the table.
- **OpenSSH:** open two new local terminals. In the fresh root test terminal, run:

  ```bash
  ssh -4 -o ForwardX11=no -p 22 root@<VPS_IPV4>
  ```

  In the fresh administrative terminal, run:

  ```bash
  ssh -4 -o ForwardX11=no -p 22822 serveradmin@<VPS_IPV4>
  ```

Inside the fresh root test session, verify the account:

```bash
whoami
```

The result must be `root`.

Inside the fresh administrative session:

```bash
whoami
sudo -v
sudo -i
whoami
```

The first `whoami` must print `serveradmin`; the final `whoami` must print `root`. When `sudo -v`
asks for a password, enter the `serveradmin` password created during step 4. The terminal
deliberately displays no characters while you type it.

Do not continue until both fresh IPv4 SSH sessions work.

After both fresh SSH access tests have succeeded, three SSH terminals are open:

1. the **original root terminal** that ran `prepare`;
2. the **fresh root test terminal** on IPv4 TCP `22`;
3. the **fresh `serveradmin` terminal** on IPv4 TCP `22822`, currently in a root login shell
   because `sudo -i` was run above.

Before continuing, leave only the fresh `serveradmin` terminal open:

1. Keep the fresh `serveradmin` terminal on TCP `22822` open.
2. Close the fresh root test terminal on TCP `22`. Its access test is complete.
3. Close the original root terminal that ran `prepare`. It is now safe to close because both
   fresh access paths have been tested.
4. Return to the remaining `serveradmin` terminal and verify its current state:

   ```bash
   whoami
   ss -6 -H -lntup
   ```

   `whoami` must print `root`. The `ss` command must print nothing. If `whoami` does not
   print `root`, run `sudo -i` and repeat both checks.

Do not continue unless the `serveradmin` terminal remains connected, `whoami` prints `root`,
and `ss -6 -H -lntup` prints nothing.

> **Why closing the original terminal matters:** If `prepare` reported a transient X11 listener,
> that listener belongs to the original SSH session and disappears when that session closes.
> New sessions cannot recreate it because the managed SSH configuration sets
> `X11Forwarding no`.

---

## 7. Run the `finalize` phase

Continue in the same fresh `serveradmin` terminal retained at the end of step 6. That terminal
is already connected over IPv4 TCP `22822`, and step 6 confirmed that it is in a root login shell.

Before running `finalize`, verify the current user:

```bash
whoami
```

The result must be `root`.

If `whoami` prints anything other than `root`, enter a root login shell and verify again:

```bash
sudo -i
whoami
```

Do not continue until `whoami` prints `root`.

From the verified root shell:

```bash
cd /opt/discrete-infrastructure

ADMIN_USER=serveradmin \
  bash bootstrap/run.sh finalize
```

When prompted, type `serveradmin`.

The script will:

1. revalidate the IPv4-only host state;
2. revalidate client-only time synchronization;
3. verify that UFW is absent;
4. verify both temporary IPv4 SSH firewall rules;
5. verify anonymous HTTPS access to the public repository;
6. require confirmation of the admin SSH test;
7. apply final IPv4-only SSH on TCP `22822`;
8. disable direct root SSH;
9. remove temporary TCP `22` access;
10. apply the final IPv4 nftables policy;
11. apply the final IPv4-only Fail2Ban policy;
12. verify effective SSH configuration and kernel listeners;
13. run the complete final-state verification;
14. write the finalized-state marker only after every check passes.

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
continue to step 8. The phase may already have changed SSH or firewall state, so the correct
recovery depends on where it stopped.

From the same root shell, collect the detailed status and port-audit output:

```bash
cd /opt/discrete-infrastructure

ADMIN_USER=serveradmin \
  bash bootstrap/run.sh status --verbose

./scripts/audit-ports.sh --verbose
```

The status and audit commands may report failures because finalization is incomplete; that output
is diagnostic. Save the complete `finalize` output, especially the first `ERROR:` line, together
with both diagnostic outputs. Use them to correct the repository implementation or obtain
failure-specific recovery instructions before running `finalize` again. If the SSH connection
drops, use the provider console or recovery access instead of repeatedly attempting SSH.

---

## 8. Perform final access tests

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

Inside the fresh post-finalization admin session:

```bash
whoami
sudo -i
whoami
```

The first `whoami` must print `serveradmin`; the final `whoami` must print `root`. Enter the
`serveradmin` password from step 4 if `sudo` asks for it.

### Confirm that direct root SSH is denied

From another new local window or tab, attempt a connection with these settings:

| Host | Username | TCP port |
|---|---|---:|
| `<VPS_IPV4>` | `root` | `22822` |

- **MobaXterm or PuTTY:** create a temporary GUI session with the settings in the table.
- **OpenSSH:** run this from a new local terminal:

  ```bash
  ssh -4 -o ForwardX11=no -o ConnectTimeout=5 -o NumberOfPasswordPrompts=1 -p 22822 root@<VPS_IPV4>
  ```

The test passes only if no root shell opens. An OpenSSH client should finish with an
authentication error such as `Permission denied`. A successful root shell is a failed test.

### Confirm that temporary TCP port 22 is closed

From your local computer:

- **MobaXterm or PuTTY:** attempt a temporary SSH session to `<VPS_IPV4>` as `root` on TCP `22`;
  it must not open a shell.
- **OpenSSH:** run this from a new local terminal:

  ```bash
  ssh -4 -o ForwardX11=no -o ConnectTimeout=5 -p 22 root@<VPS_IPV4>
  ```

  The connection must be refused or time out without opening a shell.
- **PowerShell, optional numeric check:**

  ```powershell
  Test-NetConnection <VPS_IPV4> -Port 22
  Test-NetConnection <VPS_IPV4> -Port 22822
  ```

  `TcpTestSucceeded` must be `False` for TCP `22` and `True` for TCP `22822`.

After all tests succeed:

1. Keep the fresh post-finalization `serveradmin` terminal open; it is already in a root login
   shell.
2. Close the older `serveradmin` terminal that ran `finalize` and close the failed root/port-22
   test windows.
3. Continue with steps 9 and 10 in the remaining fresh post-finalization terminal.

The root account itself is not deleted or locked. Root remains available through `sudo -i`,
the provider console or recovery environment, and provider password-reset facilities when
offered.

---

## 9. Run final verification

Continue in the fresh post-finalization `serveradmin` terminal retained at the end of step 8.
It must still be in a root login shell. Confirm before continuing:

```bash
whoami
```

The result must be `root`.

Run the human-readable final status:

```bash
cd /opt/discrete-infrastructure

ADMIN_USER=serveradmin \
  bash bootstrap/run.sh status
```

The command performs the complete final-state verification and prints one result per category in
this order:

1. finalized-state marker;
2. canonical Git origin;
3. administrative user and `sudo` access;
4. IPv4-only network state;
5. SSH configuration and listeners;
6. nftables firewall and UFW removal;
7. Fail2Ban configuration;
8. time synchronization and UDP `123`;
9. Git working tree.

Every row must begin with `[PASS]`, and the final line must be `Overall status: PASS`. If a check
fails, `[FAIL]` appears in the expected position and its diagnostic is printed immediately below
it. Do not continue until every check passes.

For low-level troubleshooting only, print the original raw socket, service, and configuration
details:

```bash
cd /opt/discrete-infrastructure

ADMIN_USER=serveradmin \
  bash bootstrap/run.sh status --verbose
```

---

## 10. Audit all listening ports

Continue in the same verified root shell:

```bash
cd /opt/discrete-infrastructure

./scripts/audit-ports.sh
```

The default output is a concise checklist in the same order a human should review it:

| Check | Required clean-baseline result |
|---|---|
| Public TCP listeners | `sshd` on IPv4 TCP `22822` only |
| Temporary SSH port | no listener on TCP `22` |
| NTP server port | no listener on IPv4 UDP `123` |
| Public UDP listeners | none, or only the provider DHCP exception on UDP `68` |
| IPv6 interface policy | disabled on every current and future interface scope |
| IPv6 addresses | none |
| IPv6 routes | none |
| IPv6 listeners | none |
| nftables tables | exactly `table ip discrete_filter` and `table ip f2b-table` |
| Firewall default policy | `drop` |
| Firewall TCP allowlist | only `22822`, `9330`, `9331`, and `9332` |

Every automated check must begin with `[PASS]`. When a provider DHCP client listens on UDP
`68`, the public-UDP check still passes and an `[INFO]` explanation follows it. A failed check
begins with `[FAIL]`, prints the relevant diagnostic immediately below it, and makes the command
exit nonzero.

The final summary must report all checks passed, followed by `IPv4-only verification passed.`
and `Port audit result: PASS`. The script now checks the documented baseline itself; do not
manually search a raw socket or nftables dump when all summary rows pass.

For troubleshooting, append the complete raw socket lists, nftables table list, and
`ip discrete_filter input` chain:

```bash
cd /opt/discrete-infrastructure

./scripts/audit-ports.sh --verbose
```

Use `--verbose` after a failed check or when preserving low-level diagnostics. The default
output deliberately omits those dumps so the pass/fail path remains readable.

This local audit does not prove provider-firewall behavior or Internet reachability. Those
remain provider-specific and require a scan from a separate external host.

---

## 11. Normal future updates

Repeat this procedure whenever the repository contains an approved infrastructure update.

> [!IMPORTANT]
> After establishing the SSH connection, run all remaining commands **inside the VPS session**,
> not in a local PowerShell, Command Prompt, or MobaXterm local terminal. Run the update commands
> from a root login shell;
> do not run them as the unprivileged `serveradmin` user.

### Open a fresh administrative SSH session

Connect from your local computer using the same SSH client method introduced in step 2:

| Host | Username | TCP port |
|---|---|---:|
| `<VPS_IPV4>` | `serveradmin` | `22822` |

- **MobaXterm or PuTTY:** open the saved administrative session, or create one with the settings
  in the table.
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
./install.sh
```

`git pull` must use anonymous read-only HTTPS and must not request a GitHub username, password,
token, or SSH key. Stop if the pull is not a fast-forward or if the installer reports an error.

### Run the readable port audit

After the installer succeeds:

```bash
cd /opt/discrete-infrastructure

./scripts/audit-ports.sh
```

Every check must begin with `[PASS]`, and the summary must end with
`Port audit result: PASS`. If a check fails, print the low-level diagnostics with:

```bash
cd /opt/discrete-infrastructure

./scripts/audit-ports.sh --verbose
```

Do not close the working administrative session until the update and audit both succeed.

### Operating rules

- Edit and commit managed configuration on GitHub or a trusted workstation, not directly on
  the VPS.
- Never edit Git-managed files under `/etc` except during emergency recovery.
- Keep the VPS checkout read-only: future updates must continue to use anonymous HTTPS pulls.

---

# Safety and recovery behavior

The bootstrap is deliberately two-phase. Disabling IPv6 does not alter the existing IPv4
address or the current IPv4 SSH transport. An SSH session that requested X11 forwarding before
IPv6 was disabled may retain a loopback-only `[::1]:60xx` proxy listener until that session
closes. `prepare` tolerates only that narrow transient case and disables X11 forwarding for every
new session. `finalize` remains strict and requires all IPv6 listeners to be gone.

The managed SSH configuration is validated before reload. If final SSH runtime validation fails,
the script restores temporary IPv4 access on TCP `22` and TCP `22822`.

The finalized-state marker is not written unless every final check passes.

---

# Implementation notes

<details>
<summary><strong>IPv4-only enforcement</strong></summary>

The repository installs `/etc/sysctl.d/99-discrete-ipv4-only.conf` with IPv6 disabled for
`all`, `default`, and `lo`. Applying `net.ipv6.conf.*.disable_ipv6=1` removes IPv6 addresses
and routes from affected interfaces. Verification enumerates every interface-specific
`disable_ipv6` flag rather than trusting only the aggregate `all` value.

OpenSSH explicitly requires `AddressFamily inet`. The nftables baseline uses `table ip`, not
`table inet`. Fail2Ban uses `allowipv6 = no` and `table_family=ip`.

During `prepare`, the only permitted transient IPv6 socket is an `sshd` X11 proxy bound to
`[::1]` on TCP `6000` through `6063` by the already-open original session. OpenSSH uses display
number 10 by default, which normally appears as TCP `6010`. The managed temporary and final SSH
configurations set `X11Forwarding no`, so fresh sessions cannot recreate it. Final verification
does not permit this exception.

</details>

<details>
<summary><strong>Grouped component application</strong></summary>

`./install.sh` first reconciles IPv4-only networking and client-only time synchronization. It
then applies the managed configuration and runs the complete verification suite.

`configs/manifest.tsv` may describe several managed files with the same component name. Those
rows form one transactional component. The installer backs up and installs all of the component's
files before validation, executes each distinct validation command once, and requires one shared
reload command and one shared verification command for the group.

If validation, reload, or verification fails, every target in the component is restored from the
same backup set. After a reload or verification failure, the installer reloads the restored
configuration once. This prevents partial multi-file service updates and avoids unnecessary
restarts such as restarting Fail2Ban separately for `fail2ban.local` and `jail.local`.

`Applied components` counts logical components rather than manifest rows. With the current
manifest, a normal full update applies three components: `ssh`, `nftables`, and `fail2ban`.
The two managed Fail2Ban files therefore produce one Fail2Ban restart, not two.

</details>

<details>
<summary><strong>APT and dpkg lock handling</strong></summary>

Provider images may start `apt-daily` or `unattended-upgrades` immediately after boot. The
bootstrap entrypoint waits up to five minutes for dpkg locks and retries lock-related APT
failures. It does not kill package-manager processes or delete lock files.

</details>

<details>
<summary><strong>Explicit phase success and failure diagnostics</strong></summary>

Bootstrap scripts run with `set -Eeuo pipefail`. A helper whose final operation is an expected
negative probe must return success explicitly after the probe passes. For example,
`nft list table ...` returning nonzero because a forbidden legacy table is absent must be handled
inside an `if` statement and must not become the helper's final status.

Any nonzero phase exit must print an `ERROR:` diagnostic before returning control to the shell. A
silent return to the prompt without the documented completion banner is an implementation defect,
not a successful or partially successful phase.

</details>

<details>
<summary><strong>Client-only time synchronization</strong></summary>

The baseline does not operate an NTP server. It removes `ntp`, `ntpsec`, `chrony`, and
`openntpd`, installs `systemd-timesyncd`, waits for `NTPSynchronized=yes`, and verifies that
no process listens on UDP `123`.

</details>

<details>
<summary><strong>Fail2Ban nftables initialization</strong></summary>

Fail2Ban normally creates its table only after the first ban. The infrastructure sets
`actionstart_on_demand=false`, so `table ip f2b-table` exists immediately and the real
enforcement path can be verified before the first hostile login attempt.

</details>

<details>
<summary><strong>Final-state verification contract</strong></summary>

The verification suite confirms:

- every IPv6 interface flag is disabled;
- no IPv6 address, route, or listening socket exists;
- `sshd -T` reports `addressfamily inet` and exactly TCP `22822`;
- SSH listens on IPv4 TCP `22822` and not on TCP `22`;
- `table ip discrete_filter` allows only the intended IPv4 ingress;
- neither `table inet discrete_filter` nor `table ip6 discrete_filter` remains;
- `table ip f2b-table` protects IPv4 TCP `22822` only;
- no IPv6 Fail2Ban table or set remains;
- `systemd-timesyncd` is active and synchronized;
- no process listens on UDP `123`;
- UFW and residual UFW chains are absent.

</details>
