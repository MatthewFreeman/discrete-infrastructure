# IP certificate — certificate-only stage

This profile obtains a trusted IP SAN certificate without buying a domain. It
does not expose the payment application, walletd, merchant API or private test
fixtures. The standalone ACME responder owns port80 only during validation.
The existing host firewall must permit inbound TCP80. No general web server is
started or stopped by renewal. Do not reuse this mode after another server binds80:
first qualify webroot validation and a narrowly scoped certificate reload hook.

## Installation and issuance

On the dedicated Debian12 host, Certbot5.8.0 is isolated in the root-controlled
`/opt/discrete-pay-acme/venv`, not installed into shared system Python:

```sh
install -d -m0700 /opt/discrete-pay-acme
python3 -m venv --without-pip /opt/discrete-pay-acme/venv
python3 -m pip --isolated --python /opt/discrete-pay-acme/venv install \
  --index-url https://pypi.org/simple certbot==5.8.0
```

First prove HTTP-01 issuance using separate staging config/work/log directories.
Then issue using the production CA, retaining its account and renewal state in
the normal `/etc/letsencrypt`, `/var/lib/letsencrypt`, `/var/log/letsencrypt` paths:

```sh
/opt/discrete-pay-acme/venv/bin/certbot certonly --non-interactive --agree-tos \
  --register-unsafely-without-email --standalone \
  --http-01-address <owned-public-ip> --preferred-challenges http \
  --required-profile shortlived --ip-address <owned-public-ip> \
  --cert-name discrete-pay-ip
```

Account registration above has no email/contact notifications. Expiry and renewal
failures need operational monitoring; successful issuance is not permanent
availability. Keep Certbot/dependencies maintained separately, not auto-upgraded
during certificate renewal. The account and certificate private keys stay on the
host and must not be copied into Git, browser storage or an application UID.

Verify IP SAN, validity period, issuer, chain with the system CA store, matching
certificate/private public keys, and root0600 private-key permissions. A staged
certificate is not trusted. Never turn off certificate verification to obtain a
passing result.

## Renewal

Install the two supplied root-owned0644 units only if their names are unused.
Validate with `systemd-analyze verify`, run `daemon-reload`, then enable/start
`discrete-pay-ip-renew.timer`. It checks every6hours with15minutes jitter and
after boot. Certbot decides when renewal is due; the timer does not force issuance
on every check. The service renews only `discrete-pay-ip` and has a10minute timeout.
Test actual ACME renewal using `renew --dry-run --cert-name discrete-pay-ip` under
the same service sandbox before claiming the scheduled path is configured.

No deploy/reload hook is installed in this certificate-only stage because no
public HTTPS consumer exists. Before connecting a real HTTPS edge, install and
test the specific consumer's reload hook; renewal on disk does not reload a server.

Rollback: stop/disable only `discrete-pay-ip-renew.timer`, retain certificate,
account and renewal data, and leave unrelated services/firewall untouched.

Sources: [IP certificates](https://letsencrypt.org/2026/01/15/6day-and-ip-general-availability.html),
[Certbot IP support](https://letsencrypt.org/2026/03/11/shorter-certs-certbot).
