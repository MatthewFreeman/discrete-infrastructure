# Bootstrap a Clean Debian 12 IPv4-Only VPS

This runbook builds the standard Discrete server baseline from a newly created Debian 12 VPS.
The finished host is intentionally IPv4-only. Discrete services use TCP only.

> **Important**
>
> Keep the original root SSH session open until final verification is complete.
> Use the VPS IPv4 address for every access test.
> Do not remove provider access to IPv4 TCP `22` before `finalize` succeeds and a fresh
> `serveradmin` login on IPv4 TCP `22822` has been tested.

---

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
| Inbound UDP | none |
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
- a dedicated read-only GitHub deploy key;
- Git-managed deployment, rollback, audit, and verification.

The bootstrap does **not** create the VPS itself. Provider plans, regions, IPv4 addresses,
recovery consoles, snapshots, and provider-side firewall rules remain provider-specific.

---

# Deployment procedure

## 1. Create the VPS

Create a new VPS with:

- Debian 12;
- a public IPv4 address;
- provider console or recovery access;
- provider firewall rules allowing IPv4 traffic only:

| Protocol | Port | Purpose |
|---|---:|---|
| TCP | `22` | Temporary root SSH during bootstrap |
| TCP | `22822` | Administrative SSH |
| TCP | `9330` | Discrete P2P |
| TCP | `9331` | Discrete RPC HTTP |
| TCP | `9332` | Discrete RPC HTTPS |
| ICMP | n/a | IPv4 diagnostics and Path MTU handling |

Do not add inbound UDP rules.
Do not add IPv6 firewall rules.
Do not remove provider access to IPv4 TCP `22` yet.

A provider may initially assign an IPv6 address to the guest. The bootstrap removes guest
IPv6 addresses and routes. Provider-side IPv6 can be disabled after the guest migration and
verification succeed.

---

## 2. Log in as root over IPv4

Use the provider-supplied root credentials and the public IPv4 address.
Keep this session open until all final access tests pass.

---

## 3. Install Git and clone the repository

```bash
apt-get update
apt-get install -y ca-certificates git
```

Clone the private repository:

```bash
git clone \
  https://github.com/MatthewFreeman/discrete-infrastructure.git \
  /opt/discrete-infrastructure

cd /opt/discrete-infrastructure
```

GitHub will prompt for credentials. Use:

- your GitHub username;
- a temporary fine-grained personal access token as the password;
- access limited to this repository;
- repository permission: **Contents: Read-only**.

Do not place the token directly in the clone URL.

---

## 4. Run the `prepare` phase

```bash
cd /opt/discrete-infrastructure

ADMIN_USER=serveradmin \
  bash bootstrap/run.sh prepare
```

The script will:

1. validate Debian 12;
2. wait for provider package-manager activity and install required packages;
3. install and apply the managed IPv4-only sysctl policy;
4. remove all guest IPv6 addresses and routes;
5. require that no IPv6 listening socket remains;
6. remove `ntp`, `ntpsec`, `chrony`, and `openntpd` when installed;
7. install and enable client-only `systemd-timesyncd`;
8. verify that the clock is synchronized and no process listens on UDP `123`;
9. create `serveradmin` and add it to `sudo`;
10. keep root SSH on IPv4 TCP `22`;
11. enable admin SSH on IPv4 TCP `22822`;
12. activate the temporary IPv4 two-port nftables policy;
13. remove UFW and residual UFW tables;
14. configure IPv4-only Fail2Ban for TCP `22` and TCP `22822`;
15. generate a dedicated GitHub deploy key.

The bootstrap waits for up to five minutes when provider processes such as
`unattended-upgrades` hold APT or dpkg locks. Lock-wait or retry messages during this
period are expected. Do not kill package-manager processes or delete lock files.

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

`Deploy key ready` may show `yes` on a supported rerun after the key has already been
registered.

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

If GitHub prompts for credentials during `git pull`, use the same temporary credentials
specified in step 3. Re-running `prepare` before `finalize` is supported.

---

## 5. Register the GitHub deploy key

Display the public key:

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
<server-name> discrete infrastructure pull key
```

Paste the public key and leave **Allow write access** disabled.

Verify the deploy key from the VPS:

```bash
git ls-remote \
  git@github-discrete:MatthewFreeman/discrete-infrastructure.git \
  HEAD
```

Expected result: a commit SHA followed by `HEAD`, without a username or token prompt.

---

## 6. Test both IPv4 SSH access paths

Do not close the original root session.

From a new terminal, test root on temporary IPv4 TCP `22`:

```bash
ssh -4 -p 22 root@<VPS_IPV4>
```

From another new terminal, test `serveradmin` on IPv4 TCP `22822`:

```bash
ssh -4 -p 22822 serveradmin@<VPS_IPV4>
```

Inside the administrative session:

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

---

## 7. Run the `finalize` phase

From the still-open root or administrative session:

```bash
cd /opt/discrete-infrastructure

ADMIN_USER=serveradmin \
  bash bootstrap/run.sh finalize
```

When prompted, type:

```text
serveradmin
```

The script will:

1. revalidate the IPv4-only host state;
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

The root account itself is not deleted or locked. Root remains available through `sudo -i`,
the provider console or recovery environment, and provider password-reset facilities when
offered.

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
  bash bootstrap/run.sh status
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

The audit prints:

- every listening TCP socket and owning process;
- every listening UDP socket and owning process;
- IPv6 interface, address, route, and listener state;
- all active nftables tables;
- the complete `ip discrete_filter input` chain.

For the clean baseline before Discrete services are installed:

- the only public TCP listener is `sshd` on IPv4 TCP `22822`;
- there is no TCP listener on port `22`;
- there are no IPv6 addresses, routes, or listening sockets;
- there is no UDP listener on port `123`;
- a provider DHCP client may listen on IPv4 UDP `68` and must not be removed without proving
  that the VPS uses static network configuration;
- nftables allows IPv4 TCP `22822`, `9330`, `9331`, and `9332`;
- TCP `9330` through `9332` may be allowed without listeners until Discrete is installed.

The successful audit ends with:

```text
IPv4-only verification passed.
Port audit result: PASS
```

This local audit does not prove provider-firewall behavior or Internet reachability. Those
remain provider-specific and require a scan from a separate external host.

---

## 11. Normal future updates

The VPS deploy key is read-only. Edit and commit managed configuration from GitHub or a
trusted workstation.

On the server:

```bash
cd /opt/discrete-infrastructure
git pull --ff-only
./install.sh
./scripts/audit-ports.sh
```

`./install.sh` reconciles IPv4-only networking and client-only time synchronization before
applying managed configuration and running the complete verification suite.

Never edit Git-managed files directly under `/etc`, except during emergency recovery.

---

# Safety and recovery behavior

The bootstrap is deliberately two-phase. Disabling IPv6 does not alter the existing IPv4
address or the current IPv4 SSH transport. The managed SSH configuration is validated before
reload. If final SSH runtime validation fails, the script restores temporary IPv4 access on
TCP `22` and TCP `22822`.

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

</details>

<details>
<summary><strong>APT and dpkg lock handling</strong></summary>

Provider images may start `apt-daily` or `unattended-upgrades` immediately after boot. The
bootstrap entrypoint waits up to five minutes for dpkg locks and retries lock-related APT
failures. It does not kill package-manager processes or delete lock files.

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
