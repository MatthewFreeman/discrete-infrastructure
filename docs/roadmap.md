# Roadmap

## Current structural milestone

- Make `modules/host/` the canonical host implementation.
- Preserve stable root operator commands and installed-service paths through compatibility
  entrypoints.
- Keep published ADR and benchmark URLs stable.
- Re-run clean-room host validation before describing the new layout as behaviorally validated.

## Node lifecycle

Add tested implementation under `modules/node/` in this order:

```text
preflight -> install -> verify -> update -> rollback -> backup -> uninstall
```

Use official upstream artifacts by default. Automatic updates should be enabled by default only
after provenance, checksum, failure recovery, rollback, and service-health behavior are proven.

## Later modules

Explorer, web-wallet, commerce, and connectivity-map modules appear only with real implementation
or an accepted design document. Deployment profiles appear only when at least two stable modules
can be composed. Shared abstractions appear only after code is genuinely reused.
