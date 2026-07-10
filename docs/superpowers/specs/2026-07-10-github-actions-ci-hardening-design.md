# GitHub Actions CI: Repo-Wide Coverage + Hardening Design

Date: 2026-07-10
Status: approved

Addresses `findings.md` #6 ("The repo's stated guardrails are stronger than
its actual enforcement") and guardrails #1 ("Add repo-wide CI") and #4 ("Ban
committed bypasses") from the "Guardrails Before More AI Development"
section. The specific Justfile bypass #6 cited was already fixed separately
(commit `f601eb8`, re-enabling pyrefly in `traceformat`'s `ci` recipe); the
remaining, larger gap this design closes is that **no GitHub Actions CI
exists for `oidtrace` or `traceformat` at all**, and the one existing CI
workflow (`oidviz-ci.yml`) plus the deploy workflow have no explicit
`permissions:` block and pin third-party actions to mutable version tags
rather than commit SHAs.

## Problem

- `oidtrace` and `traceformat` are uv-workspace Python packages with a full
  local toolchain (ruff, pyrefly, pytest, vulture, Robot Framework) defined
  in their Justfiles, but nothing runs any of it in CI. A PR can merge
  without lint, types, or tests ever running.
- `oidviz-ci.yml` and `deploy-oidviz.yml` have no `permissions:` block (so
  they run with the repo's default token permissions) and pin actions like
  `actions/checkout@v4` to tags an upstream maintainer could move.
- There's no automated check that the workflow files themselves stay
  secured — pinning, permissions, and trigger safety are things a future
  edit could quietly regress.

## Design

### New/changed files

| File | Change |
|---|---|
| `.github/workflows/traceformat-ci.yml` | New |
| `.github/workflows/oidtrace-ci.yml` | New |
| `.github/workflows/actions-security.yml` | New (zizmor) |
| `.github/dependabot.yml` | New |
| `.github/workflows/oidviz-ci.yml` | Hardened only — same triggers/steps |
| `.github/workflows/deploy-oidviz.yml` | Hardened only — same triggers/steps |

### Triggers

| Workflow | Fires on |
|---|---|
| `traceformat-ci.yml` | `pull_request` + `push:main`, paths `traceformat/**` |
| `oidtrace-ci.yml` | `pull_request` + `push:main`, paths `oidtrace/**`, `traceformat/**` |
| `oidviz-ci.yml` | `pull_request` + `push:main`, paths `oidviz/**`, `traceformat/**` (broadened from `oidviz/**` only) |
| `deploy-oidviz.yml` | unchanged (`push:main` paths `oidviz/**`, `workflow_dispatch`) |
| `actions-security.yml` | `pull_request` + `push:main`, paths `.github/workflows/**`, `.github/dependabot.yml` |

`oidtrace-ci.yml` and `oidviz-ci.yml` both trigger on `traceformat/**` because
`oidtrace` imports it as a workspace dependency, and `oidviz` generates its
TypeScript record types from `traceformat/trace-format.schema.json` — a
change there can silently break either downstream consumer. This is a broad
path filter (all of `traceformat/**`, not just `src/` or the schema file)
rather than a narrower one, traded for simplicity.

Each workflow is a single job. Steps run in the same order as that
package's `just ci` (or `just hook`), sequentially, stopping at the first
failure — matching the existing `oidviz-ci.yml` shape and the documented
rationale in `docs/dev-guidelines/web-guardrails.md` (run cheapest/fastest
checks first, fail fast). Parallel per-concern jobs were considered and
rejected: `oidviz`'s checks are all sub-5-seconds combined, where per-job
checkout/setup overhead would dominate; for consistency, `oidtrace` and
`traceformat` use the same single-job shape even though their steps
individually take longer.

### Job steps

**`traceformat-ci.yml`** (`working-directory: traceformat`):
checkout → `astral-sh/setup-uv` (cache enabled, keyed on `uv.lock`) →
`uv sync --locked` → `just lint-schema` → `just types-fresh` → `just lint`
→ `just types` → `just test`.

**`oidtrace-ci.yml`** (`working-directory: oidtrace`):
checkout → `astral-sh/setup-uv` → `uv sync --locked` →
`apt-get install -y snmp` → `just lint` → `just types` → `just deadcode` →
`REQUIRE_REFERENCE_TOOLS=1 just test-all` → `just robot` →
`just robot-reference`.

The `snmp` apt package provides `snmpwalk`/`snmpbulkwalk`, which the
`reference_tools`-marked pytest tests and the one `reference_tools`-tagged
Robot spec (`spec_rfc7860_reference.robot`) shell out to against a local
emulator — no network access is needed, so this is safe to run on every PR.
This replaces the package's local default (`just ci`, which runs plain
`just test` + `just robot` and excludes `reference_tools`) with fuller
coverage in CI specifically, since reference-tool cross-validation is
exactly the kind of protocol-correctness check findings.md flags as
currently untested in CI.

**`oidviz-ci.yml`**: unchanged steps (`bun install` → Playwright browser
install → `just ci`).

**`actions-security.yml`**: checkout → run `zizmor --min-severity medium
.github/workflows`, non-zero exit fails the job. zizmor is a static
analyzer purpose-built for GitHub Actions workflows: it flags unpinned
`uses:`, overly broad `permissions:`, dangerous trigger/checkout
combinations (e.g. `pull_request_target` with PR-head checkout), and
script-injection risk from untrusted `${{ }}` expansion inside `run:`
steps. This is a hard gate, not advisory — an unenforced check repeats the
exact "guardrails stronger than enforcement" pattern findings.md is about.

### Security baseline (applied to every workflow, including the two existing ones)

- Explicit `permissions:` block on every workflow, least privilege:
  `contents: read` for all CI/scan workflows; `deploy-oidviz.yml` keeps its
  existing `contents: read` / `pages: write` / `id-token: write`.
- Every `uses:` pinned to a full 40-character commit SHA with a trailing
  `# vX.Y.Z` comment for human readability.
- Every `actions/checkout` step sets `persist-credentials: false` — nothing
  in any of these workflows needs to push back to the repo.
- `concurrency: {group: "${{ github.workflow }}-${{ github.ref }}",
  cancel-in-progress: true}` on every CI/scan workflow, so superseded pushes
  to the same PR/branch don't pile up runs. `deploy-oidviz.yml` keeps its
  existing `pages`-scoped concurrency group unchanged.
- `.github/dependabot.yml`: one `github-actions` ecosystem entry, weekly
  schedule. Dependabot understands SHA-pinned `uses:` lines and opens PRs
  that bump both the SHA and its version comment, so the pinning policy
  doesn't silently go stale from lack of manual tracking.

## Scope

Out of scope, deliberately:

- Branch protection / required-status-check configuration. This is a
  GitHub repo-settings change, not something expressible in workflow YAML —
  worth doing once these workflows exist and have a green run to point at,
  but it's a manual follow-up outside this change.
- CodeQL, `dependency-review-action`, or secret-scanning workflows. Not
  part of what was asked (repo-wide CI, split small/targeted, secured); adding
  them now would be scope creep beyond findings.md's guardrail #1 and #4.
- Narrowing the `traceformat/**` path filters on `oidtrace-ci.yml` /
  `oidviz-ci.yml` to only the specific sub-paths each consumer actually
  reads (e.g. just the schema file for `oidviz`). Considered and rejected
  in favor of the simpler broad filter.
- Running `oidviz`'s checks as parallel per-concern jobs. Considered and
  rejected — see Design above.

## Files touched

- `.github/workflows/traceformat-ci.yml` (new)
- `.github/workflows/oidtrace-ci.yml` (new)
- `.github/workflows/actions-security.yml` (new)
- `.github/dependabot.yml` (new)
- `.github/workflows/oidviz-ci.yml` (hardening edits only)
- `.github/workflows/deploy-oidviz.yml` (hardening edits only)
