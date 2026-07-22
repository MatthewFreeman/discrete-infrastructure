# Bootstrap from a clean Debian 12 VPS

This procedure builds the server baseline from a newly created Debian 12 VPS.

It covers:

- base packages;
- the `serveradmin` administrative account;
- SSH on TCP port `22822`;
- temporary safe root access during deployment;
- final denial of direct root SSH access;
- nftables;
- Fail2Ban;
- a dedicated read-only GitHub deploy key;
- Git-managed deployment, rollback, and verification.

It does **not** create the VPS at the provider. Provider plans, regions,
public IPs, recovery consoles, snapshots, and provider firewalls remain
provider-specific.

## 1. Create the VPS

Create a VPS with:

- Debian 12;
- a public IPv4 address;
- provider console or recovery access;
- provider firewall rules allowing:
  - TCP `22` temporarily for the first login;
  - TCP `22822` for administrative SSH;
  - TCP `9330` for Discrete P2P;
  - TCP `9331` for Discrete RPC HTTP;
  - TCP `9332` for Discrete RPC HTTPS;
  - ICMP and ICMPv6 when the provider firewall supports them.

Do not remove provider access to TCP `22` until the new TCP `22822` login has
been tested.

## 2. Log in as root

Use the provider-supplied root access.

Keep this initial root session open until the complete bootstrap and final SSH
tests are finished.

## 3. Install Git and clone the private repository

```bash
apt-get update
apt-get install -y ca-certificates git

git clone \
  https://github.com/OWNER/discrete-infrastructure.git \
  /opt/discrete-infrastructure

cd /opt/discrete-infrastructure
```

For a private repository, Git prompts for credentials.

Use:

- your GitHub username;
- a temporary fine-grained personal access token as the password;
- repository access limited to this repository;
- **Contents: Read-only**.

Do not place the token directly in the clone URL. That leaks it into shell
history and process listings, which is a remarkably efficient way to convert
a secret into public documentation.

The bootstrap later changes `origin` to a dedicated read-only SSH deploy key,
so the temporary token is not retained in the Git remote.

## 4. Run the prepare phase

```bash
cd /opt/discrete-infrastructure

ADMIN_USER=serveradmin \
  bash bootstrap/debian.sh prepare
```

The prepare phase:

1. validates Debian 12;
2. installs required packages;
3. creates `serveradmin`;
4. asks for the `serveradmin` password when needed;
5. copies root `authorized_keys` to the new account when appropriate;
6. moves SSH to port `22822`;
7. keeps direct root SSH temporarily enabled;
8. applies nftables and Fail2Ban;
9. creates a dedicated GitHub deploy key;
10. prints the deploy public key.

## 5. Register the deploy key

In GitHub, open:

```text
Repository
  -> Settings
  -> Deploy keys
  -> Add deploy key
```

Paste the public key printed by the prepare phase.

Use a descriptive title such as:

```text
Canada discrete infrastructure pull key
```

Leave **Allow write access** disabled.

Run the prepare phase again only when it stopped before completing. The script
is idempotent during the prepare stage.

## 6. Test the administrative login

Do not close the original root session.

Open a new SSH session:

```text
Host: VPS public IP
Port: 22822
User: serveradmin
```

Then test:

```bash
whoami
sudo -v
sudo -i
whoami
```

Expected result:

```text
serveradmin
root
```

## 7. Finalize the baseline

From the still-open administrative or root session:

```bash
cd /opt/discrete-infrastructure

ADMIN_USER=serveradmin \
  bash bootstrap/debian.sh finalize
```

The script requires explicit confirmation that the new administrative SSH
session works.

The finalize phase:

1. verifies the read-only GitHub deploy key;
2. switches Git `origin` to the SSH deploy key alias;
3. removes temporary root SSH access;
4. applies final SSH, nftables, and Fail2Ban configurations;
5. runs the complete verification suite;
6. records the finalized state under
   `/var/lib/discrete-infrastructure/bootstrap-finalized`.

## 8. Perform the final access tests

Keep the current session open.

Test a new login as `serveradmin` on port `22822`. It must succeed.

Test a new login as `root` on port `22822`. It must be denied.

The root account itself is not deleted or locked. Root remains available
through:

- `sudo -i`;
- the provider console or recovery environment;
- provider password-reset facilities when offered.

## 9. Inspect the resulting state

```bash
cd /opt/discrete-infrastructure

ADMIN_USER=serveradmin \
  bash bootstrap/debian.sh status
```

Expected important state:

```text
permitrootlogin no
passwordauthentication yes
table inet discrete_filter
table inet f2b-table
Server replied: pong
```

## 10. Normal future updates

The VPS deploy key is read-only.

Edit and commit configuration from GitHub or a trusted workstation. On the
server:

```bash
cd /opt/discrete-infrastructure
git pull --ff-only
./install.sh
```

Never edit managed files directly under `/etc` except during emergency
recovery. Otherwise Git becomes decorative furniture, a role already occupied
by enough enterprise tooling.
