# Bootstrap a Clean Ubuntu Server 24.04 LTS IPv4-Only VPS

This runbook builds the Discrete server baseline from a newly created Ubuntu Server 24.04 LTS VPS.
The finished host is intentionally IPv4-only. Discrete services use TCP only.

> **Support status: experimental**
>
> Debian 12 remains the clean-room validated reference. Ubuntu 24.04 must complete this entire
> runbook on a fresh VPS, survive a reboot, and pass an external scan before it is marked supported.

> **Do not mix platforms**
>
> Use only the Ubuntu filenames and commands from this document. The Debian runbook remains at
> `docs/bootstrap-from-zero.md` and is intentionally unchanged.

---

## Final contract

| Item | Required state |
|---|---|
| Operating system | Ubuntu Server 24.04 LTS |
| Network stack | IPv4-only |
| IPv6 addresses, routes, listeners | none |
| OpenSSH activation | `ssh.service`, not `ssh.socket` |
| Administrative SSH | IPv4 TCP `22822` |
| Direct root SSH after finalization | disabled |
| Temporary SSH during migration | IPv4 TCP `22` |
| Discrete P2P | IPv4 TCP `9330` |
| Discrete RPC HTTP | IPv4 TCP `9331` |
| Discrete RPC HTTPS | IPv4 TCP `9332` |
| Inbound UDP | none |
| Host firewall | nftables `table ip discrete_filter` |
| Fail2Ban | nftables `table ip f2b-table` |
| Time synchronization | client-only `systemd-timesyncd` |

Ubuntu cloud images commonly provide a non-root user such as `ubuntu` and keep the root account
locked. This bootstrap does **not** unlock root on that path. Instead, the original cloud user stays
available temporarily on TCP `22`, and its SSH key is copied directly to `serveradmin`.

---

# Deployment procedure

## 1. Create the VPS

Create a new VPS with:

- Ubuntu Server 24.04 LTS release image;
- a public IPv4 address;
- provider console or recovery access;
- either direct root credentials or an SSH key assigned to the provider's initial cloud user.

Do not select a daily, development, desktop, container, or preconfigured application image.

Do not manually configure the guest firewall in the provider panel. The repository manages the
Ubuntu host firewall with nftables.

### Optional provider firewall

A provider firewall is outside the VPS and cannot be managed or verified by this repository. If no
provider firewall is attached, leave the provider panel unchanged during bootstrap.

If one is intentionally attached, allow only:

| Protocol | Port | Purpose |
|---|---:|---|
| TCP | `22` | Temporary migration access |
| TCP | `22822` | Administrative access test and final SSH |
| ICMP | n/a | IPv4 diagnostics and Path MTU handling |

Do not add inbound UDP or IPv6 rules. Ports `9330` through `9332` are not needed until Discrete
services are installed and intended to be public.

---

## 2. Log in over IPv4

Use exactly one of the following paths.

### Path A: the provider permits direct root login

From your workstation:

```bash
ssh -4 root@<VPS_IPV4>
```

On the VPS:

```bash
whoami
```

Expected:

```text
root
```

### Path B: the provider supplies an initial cloud user

The username is commonly `ubuntu`, but use the value documented by the provider:

```bash
ssh -4 <INITIAL_USER>@<VPS_IPV4>
```

On the VPS:

```bash
sudo -i
whoami
```

Expected:

```text
root
```

Remember the exact initial username. You will pass it through `BOOTSTRAP_SOURCE_USER` during
`prepare`.

Keep this original SSH session open until all fresh-login tests have passed.

---

## 3. Wait for first-boot provisioning

Ubuntu cloud images may still be running cloud-init after the first SSH login. Do not race it while
it is configuring packages, networking, or SSH.

From the root shell:

```bash
if command -v cloud-init >/dev/null 2>&1; then
  cloud-init status --wait
fi
```

Expected result: cloud-init reaches a completed state. If it reports an error, stop and inspect:

```bash
cloud-init status --long
journalctl -u cloud-init-local -u cloud-init -u cloud-config -u cloud-final --no-pager
```

Do not continue until the provider image has completed first-boot provisioning successfully.

---

## 4. Install Git and clone the public repository

From the root shell:

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

Confirm the selected operating system before changing the host:

```bash
. /etc/os-release
printf 'ID=%s VERSION_ID=%s\n' "$ID" "$VERSION_ID"
```

Required output:

```text
ID=ubuntu VERSION_ID=24.04
```

---

## 5. Run the Ubuntu `prepare` phase

### Path A: original login was direct root

```bash
cd /opt/discrete-infrastructure

ADMIN_USER=serveradmin \
  bash bootstrap/run-ubuntu-24.04.sh prepare
```

### Path B: original login used a cloud user

Replace `<INITIAL_USER>` with the actual provider username, commonly `ubuntu`:

```bash
cd /opt/discrete-infrastructure

BOOTSTRAP_SOURCE_USER=<INITIAL_USER> \
ADMIN_USER=serveradmin \
  bash bootstrap/run-ubuntu-24.04.sh prepare
```

During this phase, the script prompts you to set a strong password for `serveradmin`. Record it in
your password manager. The password is used as a fallback when the provider cloud user has no
usable `authorized_keys` file.

The script will:

1. require exactly Ubuntu 24.04;
2. install required packages with bounded APT lock waiting;
3. disable `ssh.socket` and enable regular `ssh.service`;
4. apply the IPv4-only sysctl policy;
5. remove IPv6 addresses and routes;
6. reject unexpected IPv6 listeners;
7. configure client-only `systemd-timesyncd`;
8. create `serveradmin` and add it to `sudo`;
9. on the cloud-user path, copy that user's SSH key directly to `serveradmin`;
10. keep the original access user on TCP `22`;
11. enable `serveradmin` on TCP `22822`;
12. install the temporary two-port nftables policy;
13. remove UFW and residual UFW tables;
14. configure Fail2Ban for TCP `22` and `22822`;
15. verify anonymous HTTPS access to the public repository.

### Expected banner for Path A

```text
PREPARE PHASE COMPLETE

Network stack:          IPv4 only
IPv6 addresses/routes: none
IPv6 listeners:        none
SSH ports:             22 and 22822
Administrative user:  serveradmin
Temporary SSH user:    root on TCP 22
Root SSH login:        temporarily allowed
Firewall:              ip discrete_filter
UFW:                   removed
Fail2Ban table:        ip f2b-table
Fail2Ban SSH ports:    22 and 22822
Time synchronization: systemd-timesyncd client
UDP 123 listener:      none
Repository access:     public anonymous HTTPS
```

### Expected banner for Path B

The displayed username matches the value passed through `BOOTSTRAP_SOURCE_USER`:

```text
PREPARE PHASE COMPLETE

Network stack:          IPv4 only
IPv6 addresses/routes: none
IPv6 listeners:        none
SSH ports:             22 and 22822
Administrative user:  serveradmin
Temporary SSH user:    <INITIAL_USER> on TCP 22
Root SSH login:        disabled; root account remains locked
Firewall:              ip discrete_filter
UFW:                   removed
Fail2Ban table:        ip f2b-table
Fail2Ban SSH ports:    22 and 22822
Time synchronization: systemd-timesyncd client
UDP 123 listener:      none
Repository access:     public anonymous HTTPS
```

If `IPv6 listeners` reports a transient loopback X11 listener, keep a fresh `serveradmin` session
open, close the original session, verify that `ss -6 -H -lntup` prints nothing, and only then run
`finalize`.

Do not run `finalize` yet.

### If `prepare` stops before the final banner

Do not continue. Preserve the original SSH session and collect:

```bash
cd /opt/discrete-infrastructure

journalctl -u ssh.service -u nftables -u fail2ban -u systemd-timesyncd \
  -n 200 --no-pager

ss -4 -H -lntup
ss -6 -H -lntup
nft list ruleset
```

After the implementation is corrected, update the checkout and rerun the same path:

```bash
cd /opt/discrete-infrastructure
git pull --ff-only
```

Path A rerun:

```bash
ADMIN_USER=serveradmin \
  bash bootstrap/run-ubuntu-24.04.sh prepare
```

Path B rerun:

```bash
BOOTSTRAP_SOURCE_USER=<INITIAL_USER> \
ADMIN_USER=serveradmin \
  bash bootstrap/run-ubuntu-24.04.sh prepare
```

Returning to the prompt without the final banner is a failed phase.

---

## 6. Verify anonymous repository access

Verify from the VPS:

```bash
GIT_TERMINAL_PROMPT=0 git ls-remote \
  https://github.com/MatthewFreeman/discrete-infrastructure.git \
  HEAD
```

Expected result: a commit SHA followed by `HEAD`, without a username, password, token, or SSH-key
prompt. Do not continue if anonymous HTTPS access fails.

---

## 7. Test both fresh IPv4 SSH paths

Do not close the original session.

### Path A: direct-root image

From a new terminal:

```bash
ssh -4 -p 22 root@<VPS_IPV4>
```

This temporary root login must succeed.

### Path B: cloud-user image

From a new terminal, use the same original user and private key:

```bash
ssh -4 -p 22 <INITIAL_USER>@<VPS_IPV4>
```

This fresh cloud-user login must succeed. Root remains locked and is not tested as a temporary SSH
user on this path.

### Both paths: test `serveradmin`

From another new terminal:

```bash
ssh -4 -p 22822 serveradmin@<VPS_IPV4>
```

Use the copied SSH key or the password set during `prepare`.

Inside the fresh `serveradmin` session:

```bash
whoami
sudo -v
sudo -i
whoami
```

Expected:

```text
serveradmin
root
```

Do not continue until the selected temporary TCP `22` path and the fresh `serveradmin` TCP `22822`
path both work.

Verify SSH activation and listeners from the fresh root shell:

```bash
systemctl is-enabled ssh.service
systemctl is-active ssh.service
systemctl is-enabled ssh.socket || true
systemctl is-active ssh.socket || true
sshd -T | grep -E '^(addressfamily|port|permitrootlogin) '
ss -4 -H -lntp
ss -6 -H -lntup
```

Required state:

```text
ssh.service: enabled and active
ssh.socket: disabled and inactive
AddressFamily: inet
Ports: 22 and 22822
IPv6 listeners: none
```

For Path A, `permitrootlogin` is temporarily `yes`. For Path B, it is `no`.

---

## 8. Run the Ubuntu `finalize` phase

Use the fresh `serveradmin` session, then enter a root login shell:

```bash
sudo -i
whoami
```

Expected:

```text
root
```

Run:

```bash
cd /opt/discrete-infrastructure

ADMIN_USER=serveradmin \
  bash bootstrap/run-ubuntu-24.04.sh finalize
```

When prompted to confirm the administrative SSH test, enter:

```text
serveradmin
```

Expected final banner:

```text
BOOTSTRAP FINALIZED

Network stack:          IPv4 only
IPv6 addresses/routes: none
IPv6 listeners:        none
Administrative SSH:    serveradmin@server:22822
Direct root SSH:       disabled
Temporary SSH port:    closed
Firewall:              ip discrete_filter
UFW:                   absent
Fail2Ban table:        ip f2b-table
Fail2Ban:              active
Time synchronization: systemd-timesyncd client
UDP 123 listener:      none
Git origin:            https://github.com/MatthewFreeman/discrete-infrastructure.git
```

Do not close the working session yet.

---

## 9. Perform final access tests

From a new terminal, the final administrative login must succeed:

```bash
ssh -4 -p 22822 serveradmin@<VPS_IPV4>
```

Then:

```bash
sudo -i
whoami
```

Expected: `root`.

Direct root SSH must fail:

```bash
ssh -4 -o ConnectTimeout=5 -p 22822 root@<VPS_IPV4>
```

TCP `22` must be closed. From PowerShell:

```powershell
Test-NetConnection <VPS_IPV4> -Port 22
Test-NetConnection <VPS_IPV4> -Port 22822
```

Expected:

```text
TCP 22:     False
TCP 22822:  True
```

On the VPS verify activation mode:

```bash
systemctl is-enabled ssh.service
systemctl is-active ssh.service
systemctl is-enabled ssh.socket || true
systemctl is-active ssh.socket || true
```

Required state:

```text
ssh.service: enabled and active
ssh.socket: disabled and inactive
```

---

## 10. Run complete verification and local audit

```bash
cd /opt/discrete-infrastructure

./scripts/verify.sh all
./scripts/audit-ports.sh
```

Required verification ending:

```text
Complete final-state verification passed.
```

Required audit ending:

```text
IPv4-only verification passed.
Port audit result: PASS
```

Inspect recorded state:

```bash
ADMIN_USER=serveradmin \
  bash bootstrap/run-ubuntu-24.04.sh status
```

Important final state:

```text
addressfamily inet
port 22822
permitrootlogin no
passwordauthentication yes
pubkeyauthentication yes

IPv6 addresses: none
IPv6 routes: none
IPv6 listeners: none

sshd listener: IPv4 TCP 22822
no sshd listener: TCP 22

table ip discrete_filter
table ip f2b-table
UFW: absent
systemd-timesyncd: active
NTP synchronized: yes
no listener: UDP 123
```

Before Discrete services are installed, the only public TCP listener should be `sshd` on IPv4 TCP
`22822`. The firewall may already allow TCP `9330` through `9332`, but no process should listen on
those ports yet.

---

## 11. Reboot validation

Only after all previous checks pass:

```bash
reboot
```

Wait for the VPS to return, then reconnect:

```bash
ssh -4 -p 22822 serveradmin@<VPS_IPV4>
```

On the VPS:

```bash
sudo -i
cd /opt/discrete-infrastructure

./scripts/verify.sh all
./scripts/audit-ports.sh

systemctl is-active ssh.service
systemctl is-active ssh.socket || true
ss -4 -H -lntup
ss -6 -H -lntup
```

The verification and audit must still pass. `ssh.service` must be active, `ssh.socket` inactive, and
there must be no IPv6 listener.

---

## 12. External IPv4 scan

Run this from a different host, not from the VPS itself:

```bash
nmap -Pn -4 -p- <VPS_IPV4>
```

For the clean baseline before Discrete is installed, the only open TCP port should be:

```text
22822/tcp
```

Also verify the intended ports explicitly:

```bash
nmap -Pn -4 -p 22,22822,9330-9332 <VPS_IPV4>
```

Expected before Discrete services are installed:

```text
22: closed or filtered
22822: open
9330-9332: closed or filtered because no service is listening
```

Provider-firewall behavior can only be proven by this external test.

---

## 13. Normal future Ubuntu updates

The VPS uses anonymous HTTPS for read-only pulls.

```bash
cd /opt/discrete-infrastructure
git pull --ff-only
./install-ubuntu-24.04.sh
./scripts/audit-ports.sh
```

Do not use Debian's `install.sh` as the documented Ubuntu update path.

---

# Gate before marking Ubuntu supported

Ubuntu remains experimental until a newly created VPS records all of the following:

1. cloud-init completes without error;
2. `prepare` reaches the correct Path A or Path B banner;
3. the selected temporary TCP `22` login works;
4. fresh `serveradmin` TCP `22822` login and `sudo -i` work;
5. `finalize` reaches its final banner;
6. fresh final `serveradmin` login works;
7. root SSH is denied;
8. TCP `22` is closed;
9. `ssh.service` is active and `ssh.socket` inactive;
10. complete verification passes;
11. local port audit passes;
12. the external scan matches the intended exposure;
13. the VPS survives reboot and every final check still passes.

Only then change Ubuntu from `experimental` to `supported` in
[`bootstrap-platforms.md`](bootstrap-platforms.md).
