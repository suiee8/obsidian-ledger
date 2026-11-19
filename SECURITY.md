# Security policy

## Reporting a vulnerability

Submit vulnerability reports privately through the repository's [GitHub Security tab](https://github.com/suiee8/obsidian-ledger/security). Include the affected version or
commit, steps to reproduce, and the impact you expect. Do not attach real trade data.

You can expect an acknowledgement within a few days. This is a local-first project maintained
on a best-effort basis; there is no bug bounty.

## Scope

The app is designed to run on your own computer with the API on `127.0.0.1`. Reports about the
opt-in public mode (`LEDGER_PUBLIC=1`) and the file importers are especially welcome. For controls and deployment boundaries, see the [threat model](docs/threat-model.md) and [security notes](docs/security.md).
