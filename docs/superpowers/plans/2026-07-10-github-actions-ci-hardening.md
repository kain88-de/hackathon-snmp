# GitHub Actions CI Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give `oidtrace` and `traceformat` GitHub Actions CI for the first time, and bring all workflows (new and existing) to one secured standard, closing `findings.md` #6 and guardrails #1/#4.

**Architecture:** Six workflow-level changes, each independently reviewable: two new component CI workflows (`traceformat-ci.yml`, `oidtrace-ci.yml`) mirroring the existing `oidviz-ci.yml` shape; hardening edits to the two existing workflows (`oidviz-ci.yml`, `deploy-oidviz.yml`); a new Dependabot config for the `github-actions` ecosystem; and a new `actions-security.yml` workflow that runs `zizmor` against `.github/` on every workflow-file change and hard-fails on findings. A final task adds a CI badge to each component README (creating one for `oidviz`, which currently has none) and pushes a real PR to prove every path-filtered trigger fires and passes on GitHub's actual infrastructure — not just locally.

**Tech Stack:** GitHub Actions YAML, `zizmor` (Trail of Bits, static analysis for GH Actions workflows), `astral-sh/setup-uv`, existing `just`/`uv` toolchain in `oidtrace`/`traceformat`, existing `bun`/`just` toolchain in `oidviz`.

## Global Constraints

These apply to every workflow file touched in this plan (copied from `docs/superpowers/specs/2026-07-10-github-actions-ci-hardening-design.md`):

- Every workflow has an explicit `permissions:` block. Least privilege: `contents: read` for CI/scan workflows. `deploy-oidviz.yml` sets `pages: write` / `id-token: write` **at job level only** (on the `deploy` job), not at workflow level — zizmor's `excessive-permissions` audit flags workflow-level grants of these as overly broad when only one job needs them.
- Every `uses:` is pinned to a full 40-character commit SHA with a trailing `# vX.Y.Z` comment. Never pin to a mutable tag (e.g. `@v4`).
- Every `actions/checkout` step sets `with: persist-credentials: false`.
- Every CI/scan workflow has `concurrency: {group: "<workflow-name>-ci-${{ github.ref }}", cancel-in-progress: true}`. `deploy-oidviz.yml` keeps its existing `pages`-scoped group unchanged.
- `.github/dependabot.yml` uses the `github-actions` ecosystem with a `cooldown: {default-days: 7}` (zizmor's `dependabot-cooldown` audit requires this — it prevents Dependabot from immediately proposing a brand-new action release before the community has had a chance to notice something malicious in it).
- Verification for every task: (1) the file is valid YAML, (2) `zizmor` reports zero findings against it, (3) where applicable, the local commands the workflow runs (`just <target>`) are actually run and pass first.
- All action versions and commit SHAs below were confirmed live via `git ls-remote` against the real upstream repos on 2026-07-10, and every workflow file's exact content below was verified clean with `zizmor@1.26.1` before being written into this plan — copy them verbatim, don't re-derive them.

---

### Task 1: Add `traceformat-ci.yml`

**Files:**
- Create: `.github/workflows/traceformat-ci.yml`

**Interfaces:**
- Produces: a workflow named "Traceformat CI" triggered on `pull_request` and `push:main` for paths `traceformat/**`. No dependency on other tasks in this plan.

- [ ] **Step 1: Create a working branch**

```bash
git checkout -b ci/repo-wide-actions-hardening
```

- [ ] **Step 2: Create the workflow file**

```yaml
name: Traceformat CI

on:
  pull_request:
    paths: [traceformat/**]
  push:
    branches: [main]
    paths: [traceformat/**]

permissions:
  contents: read

concurrency:
  group: traceformat-ci-${{ github.ref }}
  cancel-in-progress: true

jobs:
  ci:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: traceformat
    steps:
      - uses: actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5 # v4.3.1
        with:
          persist-credentials: false
      - uses: extractions/setup-just@dd310ad5a97d8e7b41793f8ef055398d51ad4de6 # v2.0.0
      - uses: astral-sh/setup-uv@11f9893b081a58869d3b5fccaea48c9e9e46f990 # v8.3.2
        with:
          enable-cache: true
          cache-dependency-glob: "uv.lock"
      - run: uv sync --locked
      - run: just lint-schema
      - run: just types-fresh
      - run: just lint
      - run: just types
      - run: just test
```

- [ ] **Step 3: Validate YAML syntax**

Run:
```bash
uv run --with pyyaml python3 -c "import yaml; yaml.safe_load(open('.github/workflows/traceformat-ci.yml')); print('valid yaml')"
```
Expected: `valid yaml`

- [ ] **Step 4: Run zizmor against the new file**

Run: `uvx "zizmor@1.26.1" --offline .github/workflows/traceformat-ci.yml`
Expected: `No findings to report. Good job!` and exit code 0

- [ ] **Step 5: Confirm the steps the workflow runs actually pass locally**

Run:
```bash
cd traceformat
uv sync --locked
just lint-schema
just types-fresh
just lint
just types
just test
cd ..
```
Expected: every command exits 0; `just test` ends with `... passed` and no failures.

- [ ] **Step 6: Commit**

```bash
git add .github/workflows/traceformat-ci.yml
git commit -m "ci: add traceformat CI workflow"
```

---

### Task 2: Add `oidtrace-ci.yml`

**Files:**
- Create: `.github/workflows/oidtrace-ci.yml`

**Interfaces:**
- Produces: a workflow named "OIDTrace CI" triggered on `pull_request`/`push:main` for paths `oidtrace/**` and `traceformat/**` (oidtrace imports traceformat as a workspace dependency). Independent of Task 1's file, but on the same branch.

- [ ] **Step 1: Create the workflow file**

```yaml
name: OIDTrace CI

on:
  pull_request:
    paths: [oidtrace/**, traceformat/**]
  push:
    branches: [main]
    paths: [oidtrace/**, traceformat/**]

permissions:
  contents: read

concurrency:
  group: oidtrace-ci-${{ github.ref }}
  cancel-in-progress: true

jobs:
  ci:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: oidtrace
    steps:
      - uses: actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5 # v4.3.1
        with:
          persist-credentials: false
      - uses: extractions/setup-just@dd310ad5a97d8e7b41793f8ef055398d51ad4de6 # v2.0.0
      - uses: astral-sh/setup-uv@11f9893b081a58869d3b5fccaea48c9e9e46f990 # v8.3.2
        with:
          enable-cache: true
          cache-dependency-glob: "uv.lock"
      - run: sudo apt-get update && sudo apt-get install -y snmp
      - run: uv sync --locked
      - run: just lint
      - run: just types
      - run: just deadcode
      - run: REQUIRE_REFERENCE_TOOLS=1 just test-all
      - run: just robot
      - run: just robot-reference
```

`snmp` provides `snmpwalk`/`snmpbulkwalk`, which the `reference_tools`-marked pytest
tests and the `reference_tools`-tagged Robot spec (`spec_rfc7860_reference.robot`)
shell out to against a locally-started emulator — no network access required, so
this is safe to run on every PR. This intentionally runs `test-all` (not the
package's local default `test`, which excludes `reference_tools`) plus both
`robot` and `robot-reference`, giving CI fuller protocol coverage than the local
default.

- [ ] **Step 2: Validate YAML syntax**

Run:
```bash
uv run --with pyyaml python3 -c "import yaml; yaml.safe_load(open('.github/workflows/oidtrace-ci.yml')); print('valid yaml')"
```
Expected: `valid yaml`

- [ ] **Step 3: Run zizmor against the new file**

Run: `uvx "zizmor@1.26.1" --offline .github/workflows/oidtrace-ci.yml`
Expected: `No findings to report. Good job!` and exit code 0

- [ ] **Step 4: Confirm the steps the workflow runs actually pass locally**

Run:
```bash
cd oidtrace
uv sync --locked
just lint
just types
just deadcode
REQUIRE_REFERENCE_TOOLS=1 just test-all
just robot
just robot-reference
cd ..
```
Expected: every command exits 0; the pytest run ends with `... passed` (no
skips — if `snmpwalk`/`snmpbulkwalk` aren't installed locally, install the
`snmp` package first, matching the workflow's own step). Robot Framework
prints `X tests, X passed, 0 failed` for both `just robot` and `just
robot-reference`.

- [ ] **Step 5: Clean up Robot Framework output artifacts**

Robot Framework writes `output.xml`, `log.html`, `report.html` into
`oidtrace/` on every run; these aren't tracked by git and shouldn't be
committed.

Run:
```bash
git status --porcelain oidtrace/
rm -f oidtrace/output.xml oidtrace/log.html oidtrace/report.html
```
Expected: after the `rm`, `git status --porcelain oidtrace/` prints nothing.

- [ ] **Step 6: Commit**

```bash
git add .github/workflows/oidtrace-ci.yml
git commit -m "ci: add oidtrace CI workflow"
```

---

### Task 3: Harden `oidviz-ci.yml`

**Files:**
- Modify: `.github/workflows/oidviz-ci.yml` (entire file replaced — see below)

**Interfaces:**
- Produces: the same "OIDViz CI" workflow, now also triggered by `traceformat/**` changes (oidviz generates its record types from `traceformat/trace-format.schema.json`), with the shared security baseline applied. Steps and their order are unchanged.

- [ ] **Step 1: Read the current file to confirm no unrelated drift since this plan was written**

Run: `cat .github/workflows/oidviz-ci.yml`
Expected: matches the six `steps:` (`checkout@v4`, `setup-bun@v2`, `setup-just@v2`, `bun install`, playwright install, `just ci`) with no `permissions:` or `concurrency:` block — the same shape this task replaces.

- [ ] **Step 2: Replace the file contents**

```yaml
name: OIDViz CI

on:
  pull_request:
    paths: [oidviz/**, traceformat/**]
  push:
    branches: [main]
    paths: [oidviz/**, traceformat/**]

permissions:
  contents: read

concurrency:
  group: oidviz-ci-${{ github.ref }}
  cancel-in-progress: true

jobs:
  ci:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: oidviz
    steps:
      - uses: actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5 # v4.3.1
        with:
          persist-credentials: false
      - uses: oven-sh/setup-bun@0c5077e51419868618aeaa5fe8019c62421857d6 # v2.2.0
      - uses: extractions/setup-just@dd310ad5a97d8e7b41793f8ef055398d51ad4de6 # v2.0.0
      - run: bun install
      - run: bunx playwright install --with-deps chromium firefox
      - run: just ci
```

- [ ] **Step 3: Validate YAML syntax**

Run:
```bash
uv run --with pyyaml python3 -c "import yaml; yaml.safe_load(open('.github/workflows/oidviz-ci.yml')); print('valid yaml')"
```
Expected: `valid yaml`

- [ ] **Step 4: Run zizmor against the updated file**

Run: `uvx "zizmor@1.26.1" --offline .github/workflows/oidviz-ci.yml`
Expected: `No findings to report. Good job!` and exit code 0 (the pre-existing
file fails this same command with 3 `unpinned-uses` errors, 1
`excessive-permissions` warning, and 1 `artipacked` warning — confirm the
before/after difference if in doubt: `git stash`, re-run, `git stash pop`).

- [ ] **Step 5: Confirm `just ci` still passes locally**

Run:
```bash
cd oidviz
bun install
bunx playwright install --with-deps chromium firefox
just ci
cd ..
```
Expected: exits 0; this is unchanged behavior, only the surrounding workflow YAML changed.

- [ ] **Step 6: Commit**

```bash
git add .github/workflows/oidviz-ci.yml
git commit -m "ci: harden oidviz-ci.yml (permissions, SHA pinning, concurrency, traceformat trigger)"
```

---

### Task 4: Harden `deploy-oidviz.yml`

**Files:**
- Modify: `.github/workflows/deploy-oidviz.yml` (entire file replaced — see below)

**Interfaces:**
- Produces: the same two-job (`build`, `deploy`) deploy workflow, unchanged trigger (`push:main` on `oidviz/**`, plus `workflow_dispatch`), with `permissions:` moved from workflow-level to job-level and the security baseline applied.

- [ ] **Step 1: Read the current file to confirm no unrelated drift since this plan was written**

Run: `cat .github/workflows/deploy-oidviz.yml`
Expected: `permissions:` block at the top level (`contents: read`, `pages:
write`, `id-token: write`), two jobs (`build`, `deploy`), unpinned
`actions/checkout@v4`, `oven-sh/setup-bun@v2`,
`actions/upload-pages-artifact@v3`, `actions/deploy-pages@v4`.

- [ ] **Step 2: Replace the file contents**

```yaml
name: Deploy OIDViz to GitHub Pages

on:
  push:
    branches: [main]
    paths: [oidviz/**]
  workflow_dispatch:

concurrency:
  group: pages
  cancel-in-progress: true

jobs:
  build:
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5 # v4.3.1
        with:
          persist-credentials: false
      - uses: oven-sh/setup-bun@0c5077e51419868618aeaa5fe8019c62421857d6 # v2.2.0
      - run: bun install
        working-directory: oidviz
      - run: bun run build
        working-directory: oidviz
      - uses: actions/upload-pages-artifact@56afc609e74202658d3ffba0e8f6dda462b719fa # v3.0.1
        with:
          path: oidviz/dist

  deploy:
    needs: build
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pages: write
      id-token: write
    environment:
      name: github-pages
      url: ${{ steps.deploy.outputs.page_url }}
    steps:
      - id: deploy
        uses: actions/deploy-pages@d6db90164ac5ed86f2b6aed7e0febac5b3c0c03e # v4.0.5
```

Note the `deploy` job's `permissions:` block includes `contents: read` even
though it doesn't checkout the repo — this is the minimum GitHub allows you
to declare explicitly alongside `pages: write`/`id-token: write`; omitting
it does not reduce the job's actual access, it only removes the explicit
statement of it.

- [ ] **Step 3: Validate YAML syntax**

Run:
```bash
uv run --with pyyaml python3 -c "import yaml; yaml.safe_load(open('.github/workflows/deploy-oidviz.yml')); print('valid yaml')"
```
Expected: `valid yaml`

- [ ] **Step 4: Run zizmor against the updated file**

Run: `uvx "zizmor@1.26.1" --offline .github/workflows/deploy-oidviz.yml`
Expected: `No findings to report. Good job!` and exit code 0 (the pre-existing
file fails this same command with 4 `unpinned-uses` errors, 2
`excessive-permissions` errors, and 1 `artipacked` warning).

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/deploy-oidviz.yml
git commit -m "ci: harden deploy-oidviz.yml (job-scoped permissions, SHA pinning, persist-credentials)"
```

No local dry-run for this one — it deploys to GitHub Pages via OIDC and only
runs on `push:main` or manual dispatch, so its real trigger is exercised
after merge, not from a feature branch. YAML validity and zizmor are the
achievable local checks; Task 7 confirms deployment behavior is unaffected
in practice for `oidviz-ci.yml`'s equivalent build step.

---

### Task 5: Add `.github/dependabot.yml`

**Files:**
- Create: `.github/dependabot.yml`

**Interfaces:**
- Produces: a Dependabot config that keeps every pinned action SHA (and its
  `# vX.Y.Z` comment) current via weekly PRs, with a 7-day cooldown so a
  brand-new release isn't proposed the moment it's published.

- [ ] **Step 1: Create the file**

```yaml
version: 2
updates:
  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
    cooldown:
      default-days: 7
```

- [ ] **Step 2: Validate YAML syntax**

Run:
```bash
uv run --with pyyaml python3 -c "import yaml; yaml.safe_load(open('.github/dependabot.yml')); print('valid yaml')"
```
Expected: `valid yaml`

- [ ] **Step 3: Run zizmor against the repo root, collecting all input kinds**

Run: `uvx "zizmor@1.26.1" --offline --collect=all .`
Expected: `No findings to report. Good job!` and exit code 0. (Without
`--collect=all`, zizmor's default `INPUT` scoping under a bare `.` already
includes Dependabot configs too — this explicit form is just to be
unambiguous. If you see `dependabot-cooldown`, the `cooldown:` block above
is missing or malformed — re-check the YAML indentation.)

- [ ] **Step 4: Commit**

```bash
git add .github/dependabot.yml
git commit -m "ci: add dependabot config for github-actions ecosystem"
```

---

### Task 6: Add `actions-security.yml` (zizmor gate)

**Files:**
- Create: `.github/workflows/actions-security.yml`

**Interfaces:**
- Produces: a workflow named "GitHub Actions Security Scan" that runs
  `zizmor` against the whole repo (workflows + composite actions +
  Dependabot config) on any PR/push touching `.github/workflows/**` or
  `.github/dependabot.yml`, and fails the job (non-zero exit, zizmor's
  default behavior — do not pass `--no-exit-codes`) if it finds anything.
  This is the automated enforcement of every Global Constraint above, going
  forward.

- [ ] **Step 1: Create the workflow file**

```yaml
name: GitHub Actions Security Scan

on:
  pull_request:
    paths: [.github/workflows/**, .github/dependabot.yml]
  push:
    branches: [main]
    paths: [.github/workflows/**, .github/dependabot.yml]

permissions:
  contents: read

concurrency:
  group: actions-security-${{ github.ref }}
  cancel-in-progress: true

jobs:
  zizmor:
    runs-on: ubuntu-latest
    env:
      ZIZMOR_VERSION: 1.26.1
    steps:
      - uses: actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5 # v4.3.1
        with:
          persist-credentials: false
      - uses: astral-sh/setup-uv@11f9893b081a58869d3b5fccaea48c9e9e46f990 # v8.3.2
      - run: uvx "zizmor@${ZIZMOR_VERSION}" --format=github .
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

`--format=github` emits GitHub Actions workflow-command-formatted
annotations instead of SARIF, so no `security-events: write` permission or
SARIF-upload step is needed — `contents: read` is sufficient. `GH_TOKEN` is
the default, automatically-provided per-run token (not a new secret to
configure); it only enables zizmor's *online* audits (e.g. checking whether
a pinned SHA still corresponds to the tag it claims). Passing
`ZIZMOR_VERSION` as a job `env:` (not inlined into the `run:` string) keeps
the version bump a one-line diff for Dependabot/manual updates.

- [ ] **Step 2: Validate YAML syntax**

Run:
```bash
uv run --with pyyaml python3 -c "import yaml; yaml.safe_load(open('.github/workflows/actions-security.yml')); print('valid yaml')"
```
Expected: `valid yaml`

- [ ] **Step 3: Run zizmor against the new file itself**

Run: `uvx "zizmor@1.26.1" --offline .github/workflows/actions-security.yml`
Expected: `No findings to report. Good job!` and exit code 0

- [ ] **Step 4: Run zizmor against the whole repo one more time, as a final sanity check of every file this plan has touched so far**

Run: `uvx "zizmor@1.26.1" --offline --collect=all .`
Expected: `No findings to report. Good job!` and exit code 0

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/actions-security.yml
git commit -m "ci: add zizmor security scan for workflow files"
```

---

### Task 7: Add CI badges, push, and verify all workflows pass live on GitHub

This task pushes a branch to `origin` and opens a real pull request —
confirm with the user before running the push/PR steps if you're an
autonomous worker; this is the kind of visible, externally-observable
action that warrants a checkpoint.

**Why this task exists:** `traceformat-ci.yml`, `oidtrace-ci.yml`, and
`oidviz-ci.yml` all trigger on path filters (`traceformat/**`,
`oidtrace/**`, `oidviz/**`). A PR containing only the `.github/` changes
from Tasks 1-6 would never actually exercise those three workflows for
real — only `actions-security.yml` would fire, since it's the only one
whose path filter matches `.github/**`. Adding one genuinely useful,
permanent line (a CI status badge) inside each component directory makes
this PR itself trigger every workflow this plan adds or touches, proving
they work on GitHub's real infrastructure rather than only passing local
simulation.

**Files:**
- Modify: `oidtrace/README.md`
- Modify: `traceformat/README.md`
- Create: `oidviz/README.md` (oidviz currently has no README)

**Interfaces:**
- Consumes: all six files from Tasks 1-6, already committed on the
  `ci/repo-wide-actions-hardening` branch.

- [ ] **Step 1: Add a CI badge to `oidtrace/README.md`**

Read the current first line (`# oidtrace`) and insert a badge line
immediately after it, before the blank line that follows:

```markdown
# oidtrace

[![OIDTrace CI](https://github.com/kain88-de/hackathon-snmp/actions/workflows/oidtrace-ci.yml/badge.svg)](https://github.com/kain88-de/hackathon-snmp/actions/workflows/oidtrace-ci.yml)

`oidtrace walk` records an SNMP walk against a single device as a highly detailed,
```

(Only the two new lines are inserted; the rest of the file is unchanged.)

- [ ] **Step 2: Add a CI badge to `traceformat/README.md`**

Insert immediately after the `# traceformat` line, before the blank line
that follows:

```markdown
# traceformat

[![Traceformat CI](https://github.com/kain88-de/hackathon-snmp/actions/workflows/traceformat-ci.yml/badge.svg)](https://github.com/kain88-de/hackathon-snmp/actions/workflows/traceformat-ci.yml)

The shared package holding the **types of the trace format**. Every
```

(Only the two new lines are inserted; the rest of the file is unchanged.)

- [ ] **Step 3: Create `oidviz/README.md`**

```markdown
# oidviz

[![OIDViz CI](https://github.com/kain88-de/hackathon-snmp/actions/workflows/oidviz-ci.yml/badge.svg)](https://github.com/kain88-de/hackathon-snmp/actions/workflows/oidviz-ci.yml)

Renders an `oidtrace` trace as a self-contained, offline-capable HTML
report: verdict panel, latency waterfall, subtree heat, run comparison.
Shares its rendering with the `doctor` report. See the root
[`README.md`](../README.md) for how it fits into the wider toolset and
[`docs/dev-guidelines/web-guardrails.md`](../docs/dev-guidelines/web-guardrails.md)
for this package's toolchain conventions.
```

- [ ] **Step 4: Commit the badge changes**

```bash
git add oidtrace/README.md traceformat/README.md oidviz/README.md
git commit -m "docs: add CI status badges to component READMEs"
```

- [ ] **Step 5: Push the branch**

Confirm with the user before running this step.

```bash
git push -u origin ci/repo-wide-actions-hardening
```

- [ ] **Step 6: Open a pull request**

Confirm with the user before running this step.

```bash
gh pr create --title "Add repo-wide GitHub Actions CI + harden all workflows" --body "$(cat <<'EOF'
## Summary
- Adds CI for oidtrace and traceformat (previously untested in GitHub Actions at all)
- Hardens all workflows: explicit least-privilege permissions, every action pinned to a commit SHA, concurrency groups, persist-credentials: false
- Adds a zizmor-based scan (.github/workflows/actions-security.yml) that hard-fails on future regressions to any of the above
- Adds Dependabot config to keep pinned SHAs current with a 7-day cooldown
- Adds CI badges to each component README (also creates oidviz/README.md)

Addresses findings.md #6 and guardrails #1/#4.
See docs/superpowers/specs/2026-07-10-github-actions-ci-hardening-design.md for the full design.

## Test plan
- [ ] traceformat-ci.yml runs and passes
- [ ] oidtrace-ci.yml runs and passes (including reference-tool coverage)
- [ ] oidviz-ci.yml runs and passes
- [ ] actions-security.yml runs and passes
EOF
)"
```

- [ ] **Step 7: Watch the checks and confirm every workflow passes**

Run: `gh pr checks --watch`

Expected: `traceformat-ci`, `oidtrace-ci`, `oidviz-ci`, and `actions-security
/ zizmor` all report `pass`. If any fails, read its log with `gh run view
--log-failed` before making further changes — do not guess at a fix.

- [ ] **Step 8: Report back**

Once all checks are green, tell the user the PR is ready for review at the
URL `gh pr create` printed. Do not merge without explicit instruction —
merging is the user's call, not an automatic follow-on to a green CI run.

---

## Post-merge follow-up (not part of this plan's tasks — flag to the user, don't do automatically)

- Branch protection / required status checks for the four new/changed
  workflow names is a repo-settings change (Settings → Branches), not
  something expressible in these YAML files. Worth doing once this PR has
  a green run to point at.
