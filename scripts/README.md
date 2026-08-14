# Compatibility script entrypoints

These paths remain stable for existing runbooks, installed systemd units, and operator automation.
Canonical host scripts live under [`modules/host/scripts/`](../modules/host/scripts/).

New logic must not be added here. Each shell file delegates to its matching canonical file.
