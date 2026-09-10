# Node module

Planned canonical implementation for installing and operating an official Discrete node release.

Current state:

- official Universal Linux amd64 is the accepted default artifact family;
- Discrete v0.9.5 release-selection benchmarks and lifecycle evidence are published;
- production installation and automatic-update implementation are not yet present.

The module will grow only with tested implementation. Planned lifecycle:

```text
preflight -> install -> verify -> update -> rollback -> backup -> uninstall
```

See [`docs/node/`](../../docs/node/) and the authoritative
[`component-status.md`](../../docs/component-status.md).
