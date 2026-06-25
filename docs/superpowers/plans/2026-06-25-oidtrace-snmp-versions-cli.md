# OIDTrace SNMP Version CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure `oidtrace walk` into three sub-subcommands (`v1`, `v2c`, `v3`); v2c retains full functionality; v1 and v3 are stubbed with a runtime error.

**Architecture:** Single-file change to `cli.py`. `_build_parser` gains one level of depth — `walk` becomes a sub-parser group with `v1`, `v2c`, `v3` as children. `main` dispatches on `args.version`. Tests drive the contract; implementation follows each test batch.

**Tech Stack:** Python stdlib argparse, pytest, `just` for task runner.

**Spec:** `docs/superpowers/specs/2026-06-25-oidtrace-snmp-versions-cli-design.md`

## Global Constraints

- Breaking change accepted: `oidtrace walk <host>` → `oidtrace walk v2c <host>`. No backwards-compat shim.
- `--bulk-size` must NOT appear on the `v1` subcommand.
- v1 and v3 stubs: exit 2, message to stderr naming the version, no trace file written.
- All existing flag names and defaults on the v2c path are unchanged.
- `just test` must pass after every task. `just ci` must pass at the final review step.
- No implementation code in tests — test only observable outcomes (exit code, stderr text, file presence).

---

## Files

- Modify: `oidtrace/src/oidtrace/cli.py`
- Modify: `oidtrace/tests/integration/test_cli.py`

---

### Task 1: Update existing integration tests to the `walk v2c` invocation shape

**Outcome:** Every existing test calls `main(["walk", "v2c", host, ...])` instead of
`main(["walk", host, ...])`. Tests fail at this point because the CLI has not changed
yet — that failure is the proof the tests are meaningful.

**Files:**
- Modify: `oidtrace/tests/integration/test_cli.py`

- [ ] In `test_cli.py`, find every `main(["walk", host, ...])` call and insert `"v2c"` as
  the second element, making it `main(["walk", "v2c", host, ...])`. Touch no other logic.

- [ ] Run `just test`.
  Expected: the updated tests fail (the CLI still parses `walk <host>` directly; inserting
  `"v2c"` makes `host` parse as an unrecognised argument or wrong positional).

- [ ] Commit the test changes alone.
  Message: `test(cli): update invocations to walk v2c ahead of restructure`

---

### Task 2: Restructure `_build_parser` and `main` dispatch

**Outcome:** `oidtrace walk v2c <host> [opts]` is functionally identical to the old
`oidtrace walk <host> [opts]`. All tests from Task 1 pass. `oidtrace walk` with no
sub-subcommand prints walk-level help to stderr and exits 2.

**Files:**
- Modify: `oidtrace/src/oidtrace/cli.py`
- Modify: `oidtrace/tests/integration/test_cli.py`

**Interfaces produced:**

`_add_shared_args(p: argparse.ArgumentParser) -> None`
Adds these flags to `p`: `host` (positional), `--port`, `--out`, `--label`,
`--timeout`, `--retries`, `--start-oid`, `--time-budget`, `--give-up-after`, `-v/--verbose`.
Defaults are identical to those in the current `walk` parser.

After a successful v2c parse:
- `args.subcommand == "walk"`
- `args.version == "v2c"`
- All other attribute names match the current `walk` namespace (e.g. `args.bulk_size`,
  `args.community`, `args.host`).

After `oidtrace walk` with no sub-subcommand:
- `args.version is None`

- [ ] Add one new test: `main(["walk"])` returns 2 and stderr contains walk-level usage
  or help text (check for `"v1"`, `"v2c"`, or `"v3"` OR `"usage"` in stderr). Run it →
  expect FAIL.

- [ ] Restructure `_build_parser`:
  - Extract a `_add_shared_args(p)` helper that registers all shared flags.
  - Make `walk` a sub-parser group (`dest="version"`).
  - Add `v1`, `v2c`, `v3` as children. Call `_add_shared_args` on each.
  - `v2c` additionally gets `--community` and `--bulk-size`.
  - `v1` additionally gets `--community` only.
  - `v3` additionally gets `--user`, `--auth-proto`, `--auth-pass`, `--priv-proto`,
    `--priv-pass`.

- [ ] Update `main`:
  - Dispatch order: `args.subcommand != "walk"` → help + exit 2 (unchanged).
  - `args.version is None` → print walk-level help to stderr, exit 2.
  - `args.version == "v2c"` → existing walk logic, unchanged.
  - `args.version in ("v1", "v3")` → stub (next task).

- [ ] Run `just test`. Expected: all tests pass including the new `main(["walk"])` test.

- [ ] Commit.
  Message: `feat(cli): restructure walk into v1/v2c/v3 sub-subcommands`

---

### Task 3: Runtime stubs for v1 and v3

**Outcome:** `oidtrace walk v1 <host>` and `oidtrace walk v3 <host> --user admin`
parse without argparse error but immediately exit 2. Stderr names the version and
states it is not yet implemented. No trace file is written.

**Files:**
- Modify: `oidtrace/tests/integration/test_cli.py`
- Modify: `oidtrace/src/oidtrace/cli.py`

- [ ] Add two failing tests:

  **`test_walk_v1_not_implemented`** — `main(["walk", "v1", "127.0.0.1", "--out",
  str(tmp_path)])` returns 2; stderr contains `"v1"` and `"implement"`
  (case-insensitive); no `.oidtrace.jsonl.gz` file exists in `tmp_path`.

  **`test_walk_v3_not_implemented`** — `main(["walk", "v3", "127.0.0.1", "--user",
  "admin", "--out", str(tmp_path)])` returns 2; stderr contains `"v3"` and
  `"implement"`; no trace file in `tmp_path`.

- [ ] Run both new tests → expect FAIL (v1/v3 branches currently fall through or are
  absent).

- [ ] Add the stub branches to `main` for `v1` and `v3`: print a message to stderr
  naming the version, return 2 before any network or file operations.

- [ ] Run `just test` → all tests pass.

- [ ] Commit.
  Message: `feat(cli): stub v1 and v3 with not-implemented error`

---

### Review checkpoint

Run `just ci` (ruff → pyrefly → vulture → pytest). Expected: clean pass.

Then verify manually against a real or emulator target:

| Command | Expected |
|---------|----------|
| `oidtrace walk v2c <host> --timeout 1.0 --retries 1 --give-up-after 2` | Walk runs, trace file written, terminal summary printed |
| `oidtrace walk v1 <host>` | Exits immediately, stderr names v1 + not implemented, no trace file |
| `oidtrace walk v3 <host> --user public` | Exits immediately, stderr names v3 + not implemented, no trace file |
| `oidtrace walk` | Walk-level help on stderr, exit 2 |
| `oidtrace walk v2c` (no host) | argparse error for missing positional, exit 2 |

Only proceed to merge once `just ci` is clean and all five manual checks pass.
