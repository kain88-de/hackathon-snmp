# OIDTrace SNMP Version CLI Design

Date: 2026-06-25
Status: approved

## Purpose

Extend the `oidtrace walk` command to express all three SNMP versions (v1, v2c, v3) at
the CLI level. The version is a sub-subcommand, not a flag, so each version gets exactly
the arguments it needs with no conditional gating. Only v2c is implemented at runtime;
v1 and v3 are stubbed with a clear "not yet implemented" error to reserve the interface
shape without hiding it.

## Command hierarchy

```
oidtrace walk v1  <host> [shared opts] --community <str>
oidtrace walk v2c <host> [shared opts] --community <str> --bulk-size <N>
oidtrace walk v3  <host> [shared opts] --user <str>
                                       [--auth-proto MD5|SHA|SHA-224|SHA-256|SHA-384|SHA-512]
                                       [--auth-pass <str>]
                                       [--priv-proto DES|AES|AES-192|AES-256]
                                       [--priv-pass <str>]
```

### Shared options (identical across v1, v2c, v3)

| Flag | Default | Description |
|------|---------|-------------|
| `host` | (required) | Target hostname or IP address |
| `--port` | 161 | UDP port |
| `--out` | `.` | Output directory |
| `--label` | None | Human label; used in filename and header |
| `--timeout` | 2.0 | Per-attempt timeout in seconds |
| `--retries` | 2 | Retransmissions after first send |
| `--start-oid` | `1.3.6.1` | Subtree root OID |
| `--time-budget` | None | Wall-time budget in seconds (unlimited if absent) |
| `--give-up-after` | 3 | Consecutive misses before UNRESPONSIVE |
| `-v/--verbose` | 0 | Increase verbosity: `-v` INFO, `-vv` DEBUG |

### v1-specific options

| Flag | Default | Description |
|------|---------|-------------|
| `--community` | `public` | SNMP v1 community string |

v1 uses GetNext (one OID per request). `--bulk-size` does not exist on the v1
subcommand.

### v2c-specific options

| Flag | Default | Description |
|------|---------|-------------|
| `--community` | `public` | SNMP v2c community string |
| `--bulk-size` | 10 | GetBulk max-repetitions |

### v3-specific options

| Flag | Default | Description |
|------|---------|-------------|
| `--user` | (required) | SNMPv3 security name (USM username) |
| `--auth-proto` | None | Auth protocol: `MD5`, `SHA`, `SHA-224`, `SHA-256`, `SHA-384`, `SHA-512` |
| `--auth-pass` | None | Auth passphrase |
| `--priv-proto` | None | Privacy protocol: `DES`, `AES`, `AES-192`, `AES-256` |
| `--priv-pass` | None | Privacy passphrase |

Security level is inferred from which credentials are supplied — no explicit
`--security-level` flag:

| Supplied | Security level |
|----------|---------------|
| `--user` only | noAuthNoPriv |
| `--user --auth-proto --auth-pass` | authNoPriv |
| `--user --auth-proto --auth-pass --priv-proto --priv-pass` | authPriv |

## Argparse structure

`_build_parser` is restructured: `walk` becomes a sub-parser group and `v1`, `v2c`, `v3`
are its children. Shared options are added to each parser via a helper
`_add_shared_args(p)` to avoid repetition.

```
parser
└── subparsers (dest="subcommand")
    └── "walk"
        └── subparsers (dest="version")
            ├── "v1"   ← shared args + --community
            ├── "v2c"  ← shared args + --community + --bulk-size
            └── "v3"   ← shared args + --user + --auth-proto + --auth-pass
                                                + --priv-proto + --priv-pass
```

`main` dispatches on `args.subcommand` then `args.version`:

```
"walk" + version=None   → print walk help, exit 2
"walk" + version="v2c"  → existing walk logic (unchanged)
"walk" + version="v1"   → error: SNMP v1 not yet implemented, exit 2
"walk" + version="v3"   → error: SNMP v3 not yet implemented, exit 2
```

## Error handling

Two new operator-error cases (exit 2, no trace written, message to stderr):

1. `oidtrace walk` with no version → print `walk` subcommand help
2. `oidtrace walk v1 …` or `oidtrace walk v3 …` → `error: SNMP v1 not yet implemented`

All existing error paths (bad `--start-oid`, DNS failure, socket error) remain on the
v2c branch unchanged.

## Breaking change

`oidtrace walk <host>` becomes `oidtrace walk v2c <host>`. Existing invocations break.
Acceptable: this is a developer tool with no external users at this stage.

## Out of scope for this spec

- v1 walker implementation (GetNext loop, `noSuchName` termination)
- v3 USM implementation (key localisation, auth/priv crypto)
- Changes to the trace format or `WalkSettings` for v1/v3
- `--bulk-size` behaviour for v1 (irrelevant; flag absent from v1 subcommand)
