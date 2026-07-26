Bootstrap from a clean Debian 12 VPS

This procedure builds the server baseline from a newly created Debian 12 VPS.

The bootstrap uses two access phases:

Phase

Root SSH

Admin SSH

Firewall

prepare

TCP 22 allowed

TCP 22822 allowed

nftables allows both ports

finalize

disabled

TCP 22822 allowed

nftables removes TCP 22

The script removes UFW before the server becomes dependent on theGit-managed nftables policy. Provider images sometimes ship with UFW enabled,even when the user did not ask for it, because surprise firewalls areapparently considered a feature.

Covered by the bootstrap

base packages;

the serveradmin administrative account;

temporary root SSH on TCP 22;

administrative SSH on TCP 22822;

final denial of direct root SSH access;

removal of UFW and residual UFW nftables tables;

nftables as the only host firewall;

Fail2Ban;

a dedicated read-only GitHub deploy key;

Git-managed deployment, rollback, and verification.

It does not create the VPS at the provider. Provider plans, regions,public IPs, recovery consoles, snapshots, and provider firewalls remainprovider-specific.

1. Create the VPS

Create a VPS with:

Debian 12;

a public IPv4 address;

provider console or recovery access;

provider firewall rules allowing:

TCP 22 during bootstrap;

TCP 22822 for administrative SSH;

TCP 9330 for Discrete P2P;

TCP 9331 for Discrete RPC HTTP;

TCP 9332 for Discrete RPC HTTPS;

ICMP and ICMPv6 when supported.

Do not remove provider access to TCP 22 until finalize has completed anda fresh serveradmin login on TCP 22822 has been tested.

2. Log in as root

Use the provider-supplied root access.

Keep the initial root session open until the complete bootstrap and final SSHtests are finished.

3. Install Git and clone the private repository

apt-get update
apt-get install -y ca-certificates git

git clone \
  https://github.com/OWNER/discrete-infrastructure.git \
  /opt/discrete-infrastructure

cd /opt/discrete-infrastructure

For a private repository, Git prompts for credentials.

Use:

your GitHub username;

a temporary fine-grained personal access token as the password;

repository access limited to this repository;

Contents: Read-only.

Do not place the token directly in the clone URL.

4. Run the prepare phase

cd /opt/discrete-infrastructure

ADMIN_USER=serveradmin \
  bash bootstrap/debian.sh prepare

The prepare phase:

validates Debian 12;

installs required packages;

creates serveradmin;

asks for its password when needed;

copies root authorized_keys to the new account when appropriate;

keeps SSH on TCP 22;

adds SSH on TCP 22822;

activates a temporary nftables policy that allows both SSH ports;

removes UFW and residual UFW tables;

reapplies nftables as the only host firewall;

configures Fail2Ban to monitor TCP 22 and TCP 22822 during bootstrap;

generates a dedicated GitHub deploy key.

5. Register the deploy key

In GitHub, open:

Repository
  -> Settings
  -> Deploy keys
  -> Add deploy key

Paste the public key printed by the prepare phase.

Leave Allow write access disabled.

6. Test both access paths

Do not close the original root session.

Test a fresh root session:

Host: VPS public IP
Port: 22
User: root

Then test a fresh administrative session:

Host: VPS public IP
Port: 22822
User: serveradmin

Inside the administrative session:

whoami
sudo -v
sudo -i
whoami

Expected result:

serveradmin
root

Do not run finalize until both fresh sessions work.

7. Finalize the baseline

From the still-open administrative or root session:

cd /opt/discrete-infrastructure

ADMIN_USER=serveradmin \
  bash bootstrap/debian.sh finalize

The finalize phase:

verifies that UFW is absent;

verifies both temporary SSH firewall rules;

verifies the read-only GitHub deploy key;

requires explicit confirmation of the admin SSH test;

removes temporary root SSH access;

applies the final SSH configuration on TCP 22822;

applies the final nftables policy without TCP 22;

reapplies the final Fail2Ban policy for TCP 22822 only;

runs the complete verification suite;

records the finalized state.

8. Perform final access tests

Keep the current session open.

A fresh serveradmin login on TCP 22822 must succeed.

A fresh root login must be denied.

The root account itself is not deleted or locked. Root remains availablethrough:

sudo -i;

provider console or recovery environment;

provider password-reset facilities when offered.

9. Inspect the resulting state

cd /opt/discrete-infrastructure

ADMIN_USER=serveradmin \
  bash bootstrap/debian.sh status

Expected important state:

port 22822
permitrootlogin no
passwordauthentication yes
table inet discrete_filter
table inet f2b-table
UFW: absent
Server replied: pong

10. Normal future updates

The VPS deploy key is read-only.

Edit and commit configuration from GitHub or a trusted workstation. On theserver:

cd /opt/discrete-infrastructure
git pull --ff-only
./install.sh

Never edit managed files directly under /etc except during emergencyrecovery.

Implementation note: pipefail and service checks

The bootstrap runs with set -Eeuo pipefail. Service-output checks must notuse grep -q in a pipeline because grep -q may exit as soon as it finds amatch, causing the producer to receive SIGPIPE and making the whole pipelinelook failed. The script therefore lets grep consume the complete input andredirects its output to /dev/null.

Implementation note: SSH listener cutover

systemctl reload ssh may return before sshd has reopened every configuredlistening socket. The bootstrap therefore polls the kernel listener table forup to 10 seconds before declaring either TCP 22 or TCP 22822 unavailable.On failure it prints the active listeners and recent SSH service logs.
