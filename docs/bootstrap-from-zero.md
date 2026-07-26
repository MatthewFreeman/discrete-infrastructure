# Bootstrap a Clean Debian 12 VPS

This runbook builds the standard Discrete server baseline from a newly created Debian 12 VPS.

> **Important**
>
> Keep the original root SSH session open until the final verification is complete.
> Do not remove provider access to TCP `22` before `finalize` succeeds and a fresh
> `serveradmin` login on TCP `22822` has been tested.

---

## What the bootstrap does

| Phase | Root SSH | Admin SSH | Host firewall |
|---|---|---|---|
| `prepare` | TCP `22` allowed | TCP `22822` allowed | nftables allows both ports |
| `finalize` | Direct root SSH disabled | TCP `22822` allowed | nftables removes TCP `22` |

The bootstrap installs and configures:

- base packages;
- the `serveradmin` administrative account;
- temporary root SSH on TCP `22`;
- administrative SSH on TCP `22822`;
- nftables as the only host firewall;
- removal of UFW and residual UFW tables;
- Fail2Ban protection;
- a dedicated read-only GitHub deploy key;
- Git-managed deployment, rollback, and verification.

The bootstrap does **not** create the VPS itself. Provider plans, regions, IP addresses,
recovery consoles, snapshots, and provider-side firewall rules remain provider-specific.

---

# Deployment procedure

## 1. Create the VPS

Create a new VPS with:

- Debian 12;
- a public IPv4 address;
- provider console or recovery access;
- provider firewall rules allowing:

| Protocol | Port | Purpose |
|---|---:|---|
| TCP | `22` | Temporary root SSH during bootstrap |
| TCP | `22822` | Administrative SSH |
| TCP | `9330` | Discrete P2P |
| TCP | `9331` | Discrete RPC HTTP |
| TCP | `9332` | Discrete RPC HTTPS |
| ICMP / ICMPv6 | n/a | Diagnostics and normal IPv6 operation |

Do not remove provider access to TCP `22` yet.

---

## 2. Log in as root

Use the provider-supplied root credentials.

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

GitHub will prompt for credentials.

Use:

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
  bash bootstrap/debian.sh prepare
```

The script will:

1. validate Debian 12;
2. install required packages;
3. create `serveradmin`;
4. ask for a strong password;
5. add `serveradmin` to `sudo`;
6. keep root SSH on TCP `22`;
7. enable admin SSH on TCP `22822`;
8. activate the temporary two-port nftables policy;
9. remove UFW and residual UFW tables;
10. configure Fail2Ban for TCP `22` and TCP `22822`;
11. generate a dedicated GitHub deploy key.

Expected final banner:

```text
PREPARE PHASE COMPLETE

SSH ports:             22 and 22822
Administrative user:  serveradmin
Root SSH login:        temporarily allowed
UFW:                   removed
Fail2Ban SSH ports:    22 and 22822
Deploy key ready:      no
```

Do not run `finalize` yet.

---

## 5. Register the GitHub deploy key

Display the public key:

```bash
cat /root/.ssh/discrete_infrastructure_deploy.pub
```

Copy the complete line beginning with:

```text
ssh-ed25519
```

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

Paste the public key.

Leave **Allow write access** disabled.

Verify the deploy key from the VPS:

```bash
git ls-remote \
  git@github-discrete:MatthewFreeman/discrete-infrastructure.git \
  HEAD
```

Expected result: a commit SHA followed by `HEAD`, without a username or token prompt.

---

## 6. Test both SSH access paths

Do not close the original root session.

### Test root on TCP 22

From a new terminal:

```bash
ssh -p 22 root@<VPS_IP>
```

This login must succeed during the `prepare` phase.

### Test `serveradmin` on TCP 22822

From another new terminal:

```bash
ssh -p 22822 serveradmin@<VPS_IP>
```

Inside the new session:

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

Do not continue until both fresh SSH sessions work.

---

## 7. Run the `finalize` phase

From the still-open root or administrative session:

```bash
cd /opt/discrete-infrastructure

ADMIN_USER=serveradmin \
  bash bootstrap/debian.sh finalize
```

When prompted, type:

```text
serveradmin
```

The script will:

1. verify that UFW is absent;
2. verify both temporary SSH firewall rules;
3. verify the read-only GitHub deploy key;
4. require confirmation of the admin SSH test;
5. apply the final SSH configuration on TCP `22822`;
6. disable direct root SSH;
7. remove temporary TCP `22` access;
8. apply the final single-port nftables policy;
9. apply the final Fail2Ban policy for TCP `22822`;
10. verify the effective SSH configuration and real kernel listeners;
11. remove any recreated UFW tables;
12. run the complete final-state verification;
13. write the finalized-state marker only after every check passes.

Expected final banner:

```text
BOOTSTRAP FINALIZED

Administrative SSH:    serveradmin@server:22822
Direct root SSH:       disabled
Temporary SSH port:    closed
UFW:                   absent
Firewall:              inet discrete_filter
Fail2Ban:              active
Git origin:            git@github-discrete:MatthewFreeman/discrete-infrastructure.git
```

---

## 8. Perform final access tests

Keep the current session open until these tests finish.

### Fresh admin login must succeed

```bash
ssh -p 22822 serveradmin@<VPS_IP>
```

Then:

```bash
sudo -i
whoami
```

Expected result:

```text
root
```

### Direct root SSH must be denied

```bash
ssh -o ConnectTimeout=5 -p 22822 root@<VPS_IP>
```

Expected result: authentication denied.

### TCP 22 must be closed

From PowerShell:

```powershell
Test-NetConnection <VPS_IP> -Port 22
Test-NetConnection <VPS_IP> -Port 22822
```

Expected:

```text
TCP 22:     False
TCP 22822:  True
```

The root account itself is not deleted or locked. Root remains available through:

- `sudo -i`;
- the provider console or recovery environment;
- provider password-reset facilities, when offered.

---

## 9. Run the final verification

```bash
cd /opt/discrete-infrastructure

./scripts/verify.sh all
```

Expected output:

```text
SSH final-state verification passed.
UFW is absent and no legacy UFW tables remain.
nftables final-state verification passed.
Fail2Ban final-state verification passed.
Complete final-state verification passed.
```

Inspect the recorded state:

```bash
ADMIN_USER=serveradmin \
  bash bootstrap/debian.sh status
```

Expected important state:

```text
port 22822
permitrootlogin no
passwordauthentication yes
pubkeyauthentication yes

sshd listener: TCP 22822
no sshd listener: TCP 22

table inet discrete_filter
table inet f2b-table

no table ip filter
no table ip6 filter

UFW: absent
Server replied: pong
```

---

## 10. Normal future updates

The VPS deploy key is read-only.

Edit and commit managed configuration from GitHub or a trusted workstation.

On the server:

```bash
cd /opt/discrete-infrastructure
git pull --ff-only
./install.sh
```

Never edit Git-managed files directly under `/etc`, except during emergency recovery.

---

# Safety and recovery behavior

The bootstrap is deliberately two-phase.

If the final SSH runtime check fails, the script restores the temporary two-port
SSH configuration so TCP `22` remains available for recovery.

The finalized-state marker is not written unless all final checks pass.

---

# Implementation notes

These details explain why the scripts contain several checks that may otherwise
look unnecessarily defensive. Linux administrators call this “experience.”
Everyone else calls it “why is this script 700 lines?”

<details>
<summary><strong>pipefail and service checks</strong></summary>

The bootstrap uses:

```bash
set -Eeuo pipefail
```

A pipeline must not use `grep -q` where the producer may receive `SIGPIPE`
after `grep` exits early. The scripts allow `grep` to consume the full input and
redirect its output to `/dev/null`.

</details>

<details>
<summary><strong>SSH listener cutover</strong></summary>

`systemctl reload ssh` may return before `sshd` has reopened every configured
listening socket.

The bootstrap polls the kernel listener table for up to 10 seconds before declaring
TCP `22` or TCP `22822` unavailable. On failure it prints the active listeners and
recent SSH logs.

</details>

<details>
<summary><strong>Fail2Ban port verification</strong></summary>

Fail2Ban 1.0.2 does not provide a direct `get <jail> port` client command.

During `prepare`, the bootstrap verifies the active nftables rule instead. The
`f2b-table` rule for `addr-set-sshd` must contain both TCP `22` and TCP `22822`.

During the final state, only TCP `22822` may remain.

</details>

<details>
<summary><strong>Fail2Ban nftables initialization</strong></summary>

Fail2Ban normally creates `f2b-table` only after the first ban.

The infrastructure configuration sets:

```ini
actionstart_on_demand=false
```

This creates the nftables action immediately, allowing the deployment to verify
the real enforcement path before the first hostile login attempt. The bootstrap
and final verifier wait up to 10 seconds for the table to appear.

</details>

<details>
<summary><strong>Final-state verification contract</strong></summary>

The final SSH configuration explicitly requires:

```text
Port 22822
PermitRootLogin no
PasswordAuthentication yes
PubkeyAuthentication yes
```

The verification suite confirms:

- `sshd -T` reports exactly TCP `22822`;
- `sshd` listens on TCP `22822`;
- `sshd` does not listen on TCP `22`;
- nftables allows TCP `22822` and does not allow TCP `22`;
- Fail2Ban protects TCP `22822` and does not target TCP `22`;
- neither `table ip filter` nor `table ip6 filter` exists;
- no UFW chains remain anywhere in the nftables ruleset.

</details>
