# Hackathon Project

## Structure

Two packages under this repo:
- `emulator/` — SNMP device emulator library
- `trouble-shooter/` — FastAPI service that walks/checks SNMP devices, uses the emulator in tests

## Running CI

Each package has its own `Justfile`. Run the full pipeline from inside the package directory:

```
cd trouble-shooter && just ci
cd emulator && just ci
```

`just ci` runs: format → lint → type-check → tests.

Always run `just ci` to verify changes before committing.
