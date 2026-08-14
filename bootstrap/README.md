# Compatibility bootstrap entrypoints

These paths remain stable for existing runbooks and automation. Canonical host-bootstrap
implementation lives under [`modules/host/bootstrap/`](../modules/host/bootstrap/).

New logic must not be added here. Each shell file delegates to its matching canonical file.
