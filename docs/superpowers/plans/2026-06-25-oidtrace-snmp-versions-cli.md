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
- Test only observable outcomes: exit code, stderr text, file presence.

---

## Files

- Modify: `oidtrace/src/oidtrace/cli.py`
- Modify: `oidtrace/tests/integration/test_cli.py`

---

### Task 1: Update existing tests to `walk v2c` invocation

- [ ] Change every `main(["walk", host, ...])` call in `test_cli.py` to
  `main(["walk", "v2c", host, ...])`.

- [ ] Run `just test` → tests fail (CLI unchanged). Commit test changes alone.

---

### Task 2: Restructure parser and dispatch

**Tests:**

| Test | Outcome |
|------|---------|
| `main(["walk"])` | exit 2, stderr contains walk-level help |
| All existing tests (now using `walk v2c`) | exit 0, behaviour unchanged |

**Interfaces:**
- `_add_shared_args(p: argparse.ArgumentParser) -> None` — shared flags across all three versions: `host`, `--port`, `--out`, `--label`, `--timeout`, `--retries`, `--start-oid`, `--time-budget`, `--give-up-after`, `-v/--verbose`
- After a v2c parse: `args.version == "v2c"`, all other attribute names unchanged from current
- After `oidtrace walk` with no sub-subcommand: `args.version is None`

- [ ] Write the `main(["walk"])` test, run it → FAIL. Implement. Run `just test` → pass. Commit.

---

### Task 3: Runtime stubs for v1 and v3

**Tests:**

| Test | Outcome |
|------|---------|
| `main(["walk", "v1", "127.0.0.1", "--out", tmp_path])` | exit 2, stderr contains `"v1"` and `"implement"`, no trace file in `tmp_path` |
| `main(["walk", "v3", "127.0.0.1", "--user", "admin", "--out", tmp_path])` | exit 2, stderr contains `"v3"` and `"implement"`, no trace file in `tmp_path` |

- [ ] Write both tests, run → FAIL. Implement stubs. Run `just test` → pass. Commit.

---

### Review checkpoint

Run `just ci` (ruff → pyrefly → vulture → pytest). Expected: clean pass.

Verify manually:

| Command | Expected |
|---------|----------|
| `oidtrace walk v2c <host> --timeout 1.0 --retries 1 --give-up-after 2` | Walk runs, trace file written, terminal summary printed |
| `oidtrace walk v1 <host>` | Exits immediately, stderr names v1 + not implemented, no trace file |
| `oidtrace walk v3 <host> --user public` | Exits immediately, stderr names v3 + not implemented, no trace file |
| `oidtrace walk` | Walk-level help on stderr, exit 2 |
| `oidtrace walk v2c` (no host) | argparse error for missing positional, exit 2 |

#### Test review

Spawn a review agent against the final state of `oidtrace/tests/integration/test_cli.py`
with this prompt:

---

Review `oidtrace/tests/integration/test_cli.py` for test quality. The file covers CLI
integration tests for an SNMP walk tool: the `walk v2c` live path (runs a real UDP
emulator in-process) and the `walk v1` / `walk v3` stub paths (must exit 2 immediately
with no network I/O). Tests call `main([...])` directly and assert on exit code, stderr
content, and file presence in `tmp_path`.

Apply the following checklist. For each item, cite the specific test(s) affected and
explain concretely why it is or is not a problem. Do not flag issues already guarded by
the type checker or linter.

**Anti-patterns to check:**
- **Brittle mocking** — any mocks verifying call sequences rather than outcomes?
  The emulator-thread pattern is intentional; flag only unexpected `unittest.mock` usage.
- **Always-passing tests** — do assertions have a realistic chance of failing? Check
  that string-presence assertions (e.g. `"v1" in stderr`) would fail if the stub
  printed the wrong message or nothing at all.
- **Vague failure messages** — if a test fails, does pytest output tell you what went
  wrong without reading the source?
- **Fixture soup** — is `EmulatorThread` used only where a live network exchange is
  genuinely required? Flag any v1/v3 stub test that starts an emulator unnecessarily.
- **Test doing multiple things** — can each test be named in one sentence describing
  one behaviour?
- **Wrong level** — do any v1/v3 stub tests reach into argparse internals or patch
  private functions? Correct level: call `main([...])`, observe outputs.
- **Redundant assertions** — do any tests re-check what `just ci` already guarantees?

**Red flags to answer explicitly:**
1. Does every test fail for a reason someone can act on?
2. Is anything being patched that we own (beyond the emulator thread pattern)?
3. Do test names describe behaviour or mechanism?
4. Are the v1/v3 stub tests at the right level, or do they over-specify internals?

Conclude with: a short list of issues to fix (severity: must-fix / nice-to-have), and a
one-line verdict on whether the test suite earns its place.

---

Only proceed to merge once `just ci` is clean, all five manual checks pass, and the
test review raises no must-fix issues.
