# Discrete node

Node release qualification exists; production deployment automation does not yet exist.

Current evidence and decisions remain at stable published paths:

- [ADR 0001: use the official Universal Linux amd64 asset](../decisions/0001-use-official-universal-linux-amd64.md)
- [Discrete benchmark index](../benchmarks/README.md)
- [Discrete v0.9.5 benchmark suite](../benchmarks/discrete-v0.9.5/README.md)

Future implementation belongs under [`modules/node/`](../../modules/node/) and must cover preflight,
installation, verification, updates, rollback, backup, and uninstall before it is presented as a
beginner-safe deployment path.
