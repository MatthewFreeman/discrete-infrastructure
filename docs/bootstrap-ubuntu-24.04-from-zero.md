# Bootstrap a Clean Ubuntu Server 24.04 LTS IPv4-Only VPS

This runbook builds the Discrete server baseline from a newly created Ubuntu Server 24.04 LTS VPS.
The finished host is intentionally IPv4-only. Discrete services use TCP only.

> **Support status: experimental**
>
> The Debian 12 path is the clean-room validated reference. This Ubuntu 24.04 path has separate
> platform checks and entrypoints, but it must not be marked supported until this complete runbook
> succeeds on a fresh Ubuntu Server 24.04 LTS VPS.

> **Important**
>
> Use an Ubuntu Server 24.04 LTS release image, not a daily or development image.
> Keep the original SSH session open until fresh root and `serveradmin` IPv4 sessions have been
> tested. Use the VPS IPv4 address for every access test. Do not remove provider access to IPv4
> TCP `22` before `finalize` succeeds and a fresh `serveradmin` login on IPv4 TCP `22822` has been
> tested.

For the operating-system chooser, see:

[`bootstrap-platforms.md`](bootstrap-platforms.md)

---

## Final network contract

| Item | Required state |
|---|---|
| Host operating system | Ubuntu Server 24.04 LTS |
| Host network stack | IPv4-only |
| IPv6 addresses and routes | none |
| IPv6 listening sockets | none |
| OpenSSH activation | `ssh.service`, not `ssh.socket` |
| SSH | IPv4 TCP `22822` |
| Discrete P2P | IPv4 TCP `9330` |
| Discrete RPC HTTP | IPv4 TCP `9331` |
| Discrete RPC HTTPS | IPv4 TCP `9332` |
| Inbound UDP | none |
| Host firewall | nftables `table ip discrete_filter` |
| Fail2Ban | nftables `table ip f2b-table` |
| Time synchronization | client-only `systemd-timesyncd` |

The Ubuntu bootstrap reuses the shared managed SSH, nftables, Fail2Ban, sysctl, deployment,
rollback, audit, and verification implementation. Ubuntu-specific code handles:

- strict Ubuntu 24.04 platform validation;
- conversion from Ubuntu 24.04 OpenSSH socket activation to deterministic `ssh.service` mode;
- copying the original cloud user's SSH key to temporary root access when required;
- copying the resulting root key to `serveradmin`;
- Ubuntu-specific entrypoint and future-update filenames.

The bootstrap does **not** create the VPS itself. Provider plans, regions, IPv4 addresses,
recovery consoles, snapshots, and provider-side firewall rules remain provider-specific.

---

# Deployment procedure

## 1. Create the VPS

Create a new VPS with:

- Ubuntu Server 24.04 LTS;
- a public IPv4 address;
- provider console or recovery access;
- a provider-generated root password or an SSH key assigned to the initial cloud user.

Do not select a daily, development, desktop, container, or custom application image.

Do **not** configure guest firewall rules manually in the provider panel as part of this step.
The bootstrap installs and manages the Ubuntu host firewall through nftables.

### Optional provider firewall

A provider firewall is a separate network layer outside the VPS. The repository cannot create,
modify, or verify it. If no provider firewall is attached, leave the provider panel unchanged
during bootstrap.

If a provider firewall is intentionally attached during bootstrap, allow only:

| Protocol | Port | Purpose |
|---|---:|---|
| TCP | `22` | Temporary SSH during bootstrap |
| TCP | `22822` | Administrative SSH test and final access |
| ICMP | n/a | IPv4 diagnostics and Path MTU handling |

Do not add inbound UDP rules or IPv6 rules. Provider rules for TCP `9330`, `9331`, and `9332`
are not required for the baseline bootstrap. Add them only after the corresponding Discrete
services are installed, listening, and intended to be reachable from the Internet.

---

## 2. Log in over IPv4 and enter a root login shell

Ubuntu cloud images commonly use an initial user such as `ubuntu` instead of direct root login.
Use the access method supplied by the provider.

### Path A: provider permits direct root login

```bash
ssh -4 root@<VPS_IPV4>
whoami
```

Expected output:

```text
root
```

### Path B: provider supplies an initial cloud user

The usual username is `ubuntu`, but use the actual username shown by the provider:

```bash
ssh -4 <INITIAL_USER>@<VPS_IPV4>
sudo -i
whoami
```

Expected output:

```text
root
```

Remember the initial username. It will be passed as `BOOTSTRAP_SOURCE_USER` during `prepare` so
its existing SSH public key can be copied to temporary root access and then to `serveradmin`.

Keep this original session open throughout `prepare` and the fresh-login tests.

---

## 3. Install Git and clone the repository

Run these commands from the root shell:

```bash
apt-get update
apt-get install -y ca-certificates git
```

The repository is private. Before cloning it, create the temporary least-privilege token described
in:

[Create the temporary GitHub bootstrap token](create-github-access-token.md)

Then clone the repository:

```bash
git clone \
  https://github.com/MatthewFreeman/discrete-infrastructure.git \
  /opt/discrete-infrastructure

cd /opt/discrete-infrastructure
```

When GitHub prompts for credentials, enter:

```text
Username: <your GitHub username>
Password: <paste the temporary github_pat_ token>
```

Do not use the GitHub account password. Do not place the token directly in the clone URL. Delete
the temporary token after the deploy-key verification in step 5 succeeds.

---

## 4. Run the Ubuntu `prepare` phase

### When the original login was direct root

```bash
cd /opt/discrete-infrastructure

ADMIN_USER=serveradmin \
  bash bootstrap/run-ubuntu-24.04.sh prepare
```

### When the original login used a cloud user

Replace `<INITIAL_USER>` with the provider username, commonly `ubuntu`:

```bash
cd /opt/discrete-infrastructure

BOOTSTRAP_SOURCE_USER=<INITIAL_USER> \
ADMIN_USER=serveradmin \
  bash bootstrap/run-ubuntu-24.04.sh prepare
```

The script validates that the host is exactly Ubuntu 24.04. It will stop before changing the host
when run on Debian, another Ubuntu release, or an unidentified operating system.

During `prepare`, the script will:

1. validate Ubuntu Server 24.04;
2. wait for provider package-manager activity and install required packages;
3. disable Ubuntu OpenSSH socket activation and enable regular `ssh.service` mode;
4. install and apply the managed IPv4-only sysctl policy;
5. remove all guest IPv6 addresses and routes;
6. reject every IPv6 listener except the narrowly documented transient loopback X11 case;
7. disable X11 forwarding for all new SSH sessions;
8. remove conflicting NTP server packages when installed;
9. install and enable client-only `systemd-timesyncd`;
10. verify that no process listens on UDP `123`;
11. copy the initial cloud user's SSH key to temporary root access when root has no key;
12. create `serveradmin`, add it to `sudo`, and request a strong password;
13. copy the temporary root SSH key to `serveradmin` when available;
14. keep root SSH on IPv4 TCP `22`;
15. enable administrative SSH on IPv4 TCP `22822`;
16. activate the temporary IPv4 two-port nftables policy;
17. remove UFW and residual UFW tables;
18. configure IPv4-only Fail2Ban for TCP `22` and TCP `22822`;
19. generate a dedicated GitHub deploy key.

Ubuntu 24.04 uses OpenSSH socket activation on standard installations. The Ubuntu entrypoint
intentionally disables `ssh.socket` and enables `ssh.service`, because the bootstrap must manage
two temporary SSH ports and then one final port through validated configuration reloads.

The bootstrap waits for up to five minutes when provider processes such as `apt-daily` or
`unattended-upgrades` hold APT or dpkg locks. Do not kill package-manager processes or delete lock
files.

Expected final banner:

```text
PREPARE PHASE COMPLETE

Network stack:          IPv4 only
IPv6 addresses/routes: none
IPv6 listeners:        none
SSH ports:             22 and 22822
Administrative user:  serveradmin
Root SSH login:        temporarily allowed
Firewall:              ip discrete_filter
UFW:                   removed
Fail2Ban table:        ip f2b-table
Fail2Ban SSH ports:    22 and 22822
Time synchronization: systemd-timesyncd client
UDP 123 listener:      none
Deploy key ready:      no
```

`IPv6 listeners` may instead report a transient loopback X11 listener belonging to the original
session. In that case, follow step 6 exactly before running `finalize`.

Do not run `finalize` yet.

### If `prepare` stops before the final banner

Do not continue to the next step. Correct the implementation, update the checkout, and rerun the
same Ubuntu phase:

```bash
cd /opt/discrete-infrastructure
git pull --ff-only

BOOTSTRAP_SOURCE_USER=<INITIAL_USER> \
ADMIN_USER=serveradmin \
  bash bootstrap/run-ubuntu-24.04.sh prepare
```

For a direct-root image, omit `BOOTSTRAP_SOURCE_USER`.

Returning to the shell prompt without the final banner is a failed phase even if no `ERROR:` line
was printed.

---

## 5. Register the GitHub deploy key

Display the generated public key:

```bash
cat /root/.ssh/discrete_infrastructure_deploy.pub
```

Copy the complete line beginning with `ssh-ed25519`.

In GitHub, open:

```text
Repository
→ Settings
→ Deploy keys
→ Add deploy key
```

Recommended title:

```text
<server-name> ubuntu-24.04 discrete infrastructure pull key
```

Paste the public key and leave **Allow write access** disabled.

Verify the deploy key from the VPS:

```bash
git ls-remote \
  git@github-discrete:MatthewFreeman/discrete-infrastructure.git \
  HEAD
```

Expected result: a commit SHA followed by `HEAD`, without a username or token prompt.

Delete the temporary GitHub token after this verification succeeds.

---

## 6. Test both IPv4 SSH access paths

Do not close the original session.

From a new terminal, test temporary root access on IPv4 TCP `22`:

```bash
ssh -4 -p 22 root@<VPS_IPV4>
```

When `prepare` was started from a cloud user with `BOOTSTRAP_SOURCE_USER`, use the same private key
that was used for that cloud user. The bootstrap copies the corresponding authorized key to root
only for the temporary migration period.

From another new terminal, test `serveradmin` on IPv4 TCP `22822`:

```bash
ssh -4 -p 22822 serveradmin@<VPS_IPV4>
```

Inside the `serveradmin` session:

```bash
whoami
sudo -v
sudo -i
whoami
```

Expected output:

```text
serveradmin
root
```

Do not continue until both fresh IPv4 SSH sessions work.

If `prepare` reported a transient `[::1]:60xx` X11 listener, keep the fresh `serveradmin` session
open, close the original session, and verify from the fresh root shell:

```bash
ss -6 -H -lntup
```

Expected output: none.

Verify Ubuntu is using service mode rather than socket activation:

```bash
systemctl is-enabled ssh.service
systemctl is-active ssh.service
systemctl is-enabled ssh.socket || true
systemctl is-active ssh.socket || true
```

Expected important state:

```text
ssh.service: enabled and active
ssh.socket: disabled and inactive
```

---

## 7. Run the Ubuntu `finalize` phase

Run `finalize` as root from the fresh `serveradmin` IPv4 session:

```bash
sudo -i
whoami
```

Expected output:

```text
root
```

Then run:

```bash
cd /opt/discrete-infrastructure

ADMIN_USER=serveradmin \
  bash bootstrap/run-ubuntu-24.04.sh finalize
```

When prompted to confirm the administrative SSH test, type:

```text
serveradmin
```

The script will:

1. revalidate Ubuntu 24.04 and the IPv4-only host state;
2. revalidate client-only time synchronization;
3. verify that UFW is absent;
4. verify both temporary IPv4 SSH firewall rules;
5. verify the read-only GitHub deploy key;
6. require confirmation of the admin SSH test;
7. apply final IPv4-only SSH on TCP `22822`;
8. disable direct root SSH;
9. remove temporary TCP `22` access;
10. apply the final IPv4 nftables policy;
11. apply the final IPv4-only Fail2Ban policy;
12. verify effective SSH configuration and kernel listeners;
13. run the complete final-state verification;
14. write the finalized-state marker only after every check passes.

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
Git origin:            git@github-discrete:MatthewFreeman/discrete-infrastructure.git
```

---

## 8. Perform final access tests

Keep the current session open until these tests finish.

Fresh IPv4 admin login must succeed:

```bash
ssh -4 -p 22822 serveradmin@<VPS_IPV4>
```

Then:

```bash
sudo -i
whoami
```

Expected result: `root`.

Direct root SSH must be denied:

```bash
ssh -4 -o ConnectTimeout=5 -p 22822 root@<VPS_IPV4>
```

IPv4 TCP `22` must be closed. From PowerShell:

```powershell
Test-NetConnection <VPS_IPV4> -Port 22
Test-NetConnection <VPS_IPV4> -Port 22822
```

Expected:

```text
TCP 22:     False
TCP 22822:  True
```

Verify OpenSSH activation mode:

```bash
systemctl is-active ssh.service
systemctl is-active ssh.socket || true
```

Expected:

```text
ssh.service: active
ssh.socket: inactive
```

---

## 9. Run final verification

```bash
cd /opt/discrete-infrastructure
./scripts/verify.sh all
```

Expected output:

```text
IPv4-only final-state verification passed.
SSH final-state verification passed.
UFW is absent and no legacy UFW tables remain.
nftables final-state verification passed.
Fail2Ban final-state verification passed.
Time synchronization final-state verification passed.
Complete final-state verification passed.
```

Inspect recorded state:

```bash
ADMIN_USER=serveradmin \
  bash bootstrap/run-ubuntu-24.04.sh status
```

Expected important state:

```text
addressfamily inet
port 22822
permitrootlogin no
passwordauthentication yes
pubkeyauthentication yes

IPv6 interface flags: all disabled
IPv6 addresses: none
IPv6 routes: none
IPv6 listeners: none

sshd listener: IPv4 TCP 22822
no sshd listener: TCP 22

table ip discrete_filter
table ip f2b-table
no table inet discrete_filter
no table inet f2b-table
no table ip6 filter

UFW: absent
Server replied: pong
systemd-timesyncd: active
NTP synchronized: yes
no listener: UDP 123
```

---

## 10. Audit all listening ports

```bash
cd /opt/discrete-infrastructure
./scripts/audit-ports.sh
```

For the clean baseline before Discrete services are installed:

- the only public TCP listener is `sshd` on IPv4 TCP `22822`;
- there is no TCP listener on port `22`;
- there are no IPv6 addresses, routes, or listening sockets;
- there is no UDP listener on port `123`;
- a provider DHCP client may listen on IPv4 UDP `68`;
- nftables allows IPv4 TCP `22822`, `9330`, `9331`, and `9332`;
- TCP `9330` through `9332` may be allowed without listeners until Discrete is installed.

The successful audit ends with:

```text
IPv4-only verification passed.
Port audit result: PASS
```

This local audit does not prove provider-firewall behavior or Internet reachability. Those require
an external scan from a separate host.

---

## 11. Normal future Ubuntu updates

The VPS deploy key is read-only. Edit and commit managed configuration from GitHub or a trusted
workstation.

On the Ubuntu server:

```bash
cd /opt/discrete-infrastructure
git pull --ff-only
./install-ubuntu-24.04.sh
./scripts/audit-ports.sh
```

Do not run Debian's `install.sh` as the documented Ubuntu update path. Do not run Ubuntu's
installer on Debian.

---

# Validation gate before declaring Ubuntu supported

Ubuntu 24.04 remains experimental until all of the following are recorded on a newly created VPS:

1. `prepare` reaches its documented final banner;
2. temporary root TCP `22` and `serveradmin` TCP `22822` both work;
3. `finalize` reaches its documented final banner;
4. fresh `serveradmin` TCP `22822` works after finalization;
5. direct root login is denied;
6. TCP `22` is closed;
7. `ssh.service` is active and `ssh.socket` is inactive;
8. complete verification passes;
9. port audit passes;
10. an external IPv4 scan matches the intended exposure;
11. the VPS survives a reboot and all final checks still pass.

Only after this clean-room test succeeds should the Ubuntu status in
[`bootstrap-platforms.md`](bootstrap-platforms.md) be changed from experimental to supported.
