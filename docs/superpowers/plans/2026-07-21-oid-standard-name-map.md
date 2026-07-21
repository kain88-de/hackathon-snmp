# OID Standard Name Map Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.
>
> **Deviation from the usual plan format:** per explicit instruction, this plan does not embed
> full code. Tasks describe the contract/outcome each change must satisfy; the implementer writes
> the actual code, following existing patterns in the codebase, and leans on `just types` / `just
> lint` / the test suite as the correctness gate rather than on this document. Code appears only
> where a fact would otherwise be easy to get subtly wrong or to re-derive expensively (an external
> library's actual behavior, an exact expected string) — never as a full implementation to copy.

**Goal:** Replace oidviz's hand-written, ~50-entry MIB-group label table with a ~950-entry table
compiled from real standard (IETF) MIBs, giving both the OID Tree and the Minimap+Detail hover
tooltip exact object names (`sysDescr`, `ifDescr`, ...) and short descriptions instead of coarse
group labels.

**Architecture:** A one-off Python script (`oidviz/scripts/gen_oid_names.py`, run via `uv run`, no
persistent dependency) compiles 14 standard MIB modules with `pysmi` and writes a committed,
generated TypeScript file (`oidviz/src/lib/oidNames.gen.ts`) that fully replaces today's
hand-written `oidNames.ts`. `lookupOidName()`'s return type gains a `description` field;
`TrieNode` and `FlatRow`'s leaf variant gain matching fields; `OidTree.vue` and `MinimapDetail.vue`
render them.

**Tech Stack:** Python 3.11+ / `pysmi` / `pysnmp` (generation only, via `uv run` PEP 723 inline
deps) · TypeScript / Vue 3 / Vitest (oidviz itself, unchanged). Full design context:
`docs/superpowers/specs/2026-07-21-oid-standard-name-map-design.md`.

## Global Constraints

- Scope is standard (IETF/RFC) MIBs only — the 14 modules named in Task 1. No vendor/enterprise
  MIBs, no user-uploaded MIBs, no runtime MIB compilation (that non-goal, from `docs/oidviz.md`,
  is unaffected by this work — generation happens ahead of time, once, by a maintainer).
- `oidviz/src/lib/oidNames.ts` is deleted; `oidviz/src/lib/oidNames.gen.ts` (generated, committed to
  git, never hand-edited — same treatment as `types.gen.ts` and `traceValidator.gen.js`) is its
  sole replacement.
- `lookupOidName(oid: OidString)` returns `{ name: string; description: string | null } | null`
  (previously `string | null`) — same longest-prefix-match algorithm as today, unchanged.
- The generator script has no `pyproject.toml` and is not added to the root `uv.workspace.members`
  — it's a self-contained PEP 723 script (`# /// script` inline metadata), matching this project's
  established preference for `uv run` one-off scripts over full packages.
- `cd oidviz && just hook` (fmt-check, lint, types, vitest) must stay green after every task's
  commit; run `just ci` (adds Playwright e2e + a11y) once all three tasks land.

## Files

- Create: `oidviz/scripts/gen_oid_names.py`, `oidviz/src/lib/oidNames.gen.ts` (generated)
- Delete: `oidviz/src/lib/oidNames.ts`
- Modify: `oidviz/src/lib/model.ts`, `oidviz/src/lib/oidTrie.ts`, `oidviz/src/components/OidTree.vue`,
  `oidviz/src/components/MinimapDetail.vue`
- Modify: `oidviz/tests/unit/oidNames.test.ts`, `oidviz/tests/unit/oidTrie.test.ts`,
  `oidviz/tests/component/helpers.ts`, `oidviz/tests/component/OidTree.test.ts`,
  `oidviz/tests/component/MinimapDetail.test.ts`
- Modify: `oidviz/Justfile`, `oidviz/biome.json`, `oidviz/.oxlintrc.json`

## Recommended models

| Task | Model | Why |
| --- | --- | --- |
| 1. Compile the standard-MIB table and swap the data source | Opus | `pysmi` is an obscure, sparsely-documented library with behavior that's easy to get subtly and silently wrong (see the facts below) — no type-checker or linter catches a Python script that runs cleanly but emits quietly-wrong data. Highest correctness risk in this plan. |
| 2. Show names and descriptions in the OID Tree | Sonnet | Well-specified template edit following an exact existing pattern already in the file (the leaf-oid span's `:title` binding). Low ambiguity, tight test contract. |
| 3. Show the resolved name in the Minimap+Detail tooltip | Sonnet | Same shape as Task 2 — one function, one existing pattern (`escHtml`/`showTooltip`) to extend, tight test contract. |

---

## Task 1: Compile the standard-MIB table and swap the data source *(model: Opus)*

**Outcome:** `oidviz/src/lib/oidNames.gen.ts` exists, generated, and exports `lookupOidName(oid:
OidString): { name: string; description: string | null } | null`. `oidviz/src/lib/oidNames.ts` is
gone. Everything that touched the old `name: string | null` shape (`TrieNode`, `FlatRow`'s leaf
variant, `oidTrie.ts`, and the test/helper files that construct them) is updated to the new shape.
`cd oidviz && just hook` is green.

**Key facts, discovered by hands-on testing against the real `mibs.pysnmp.com` repository — treat
these as ground truth, not a starting hypothesis:**

- Compile with `pysmi.compiler.MibCompiler`, using `pysmi.parser.SmiV1CompatParser`,
  `pysmi.codegen.JsonCodeGen` as the code generator, a `pysmi.writer.FileWriter` (JSON suffix), MIB
  sources from `pysmi.reader.get_readers_from_urls("https://mibs.pysnmp.com/asn1/@mib@")`, and a
  `pysmi.searcher.AnyFileSearcher` over the destination directory.
- `MibCompiler.compile(*modules, genTexts=True, ignoreErrors=True)` — **`genTexts=True` is
  required** or every symbol's `description` field is omitted entirely (not `null` — absent).
- Do **not** register a `StubSearcher`. `SNMPv2-SMI` is one of `JsonCodeGen.baseMibs` — pysmi's
  default assumption is that it's already known and doesn't need compiling, which silently skips
  emitting the structural nodes we actually want (`internet`, `mgmt`, `enterprises`, `private`,
  `security`, `directory`, `org`, `dod`). Compiling it directly (no stub searcher at all) is what
  makes those appear.
- There is no standalone `ICMP-MIB` module in this repository (compiling it reports `"missing"`).
  ICMP objects (`icmpInMsgs` etc.) live in `RFC1213-MIB` instead.
- The 14 modules to compile, verified to all succeed together via `ignoreErrors=True` (unrelated
  transitive-dependency modules like `RFC-1212`/`RFC-1215` may report `"failed"` as a side effect —
  that's expected noise, not a failure of the modules actually requested):
  `SNMPv2-SMI, SNMPv2-MIB, IF-MIB, IP-MIB, TCP-MIB, UDP-MIB, HOST-RESOURCES-MIB, BRIDGE-MIB,
  ENTITY-MIB, SNMP-FRAMEWORK-MIB, SNMP-USER-BASED-SM-MIB, SNMP-VIEW-BASED-ACM-MIB,
  SNMP-COMMUNITY-MIB, RFC1213-MIB`.
- `compile()`'s return value is a dict keyed by module name; each value is a string-like status
  object safely comparable with `== "compiled"`. Treat anything else, **for the 14 modules above
  specifically**, as a hard failure: exit non-zero and write nothing (never a partial or
  silently-wrong `oidNames.gen.ts`).
- Each compiled module's JSON is a flat dict; every entry that has an `"oid"` key (a plain dotted
  string, e.g. `"1.3.6.1.2.1.1.1"`) is a real symbol worth keeping — the only keys without one are
  the fixed `"imports"` and `"meta"` entries. `"description"` is present only for real
  `OBJECT-TYPE`/`MODULE-IDENTITY`/compliance nodes — plain `OBJECT IDENTIFIER` assignments (the
  structural nodes above) have none, so `description: null` for those is correct, not a bug.
- **Different modules define the same OID.** `RFC1213-MIB` and `SNMPv2-MIB` both define `sysDescr`
  at `1.3.6.1.2.1.1.1` (with different description text). Process the 14 modules in the order
  listed above and keep the *first* definition seen per OID — that order puts every modern module
  before `RFC1213-MIB`, which they obsolete, so `RFC1213-MIB` only fills real gaps (ICMP).
- Truncate each kept description to its first sentence (split on sentence-ending punctuation) —
  full RFC prose is multiple sentences and this is a hover-tooltip label, not documentation.
- The generated file's shape mirrors today's `oidNames.ts` almost exactly — a `[prefix, name,
  description][]` array plus the same longest-prefix-match `lookupOidName`, sorted by prefix length
  descending at module load — just wider (3-tuples instead of 2-, ~950 entries instead of ~50), and
  now self-contained/generated rather than hand-written. Give it the same generated-file banner and
  git/lint treatment as `types.gen.ts`/`traceValidator.gen.js`: a `// GENERATED FILE. DO NOT EDIT BY
  HAND.` header naming the regenerate command, committed to git, and added to the existing
  `types.gen.ts`/`traceValidator.gen.js` exemption lists in `oidviz/Justfile`'s `lint` recipe,
  `oidviz/.oxlintrc.json`'s `ignorePatterns`, and `oidviz/biome.json`'s override `include`.
- Wire it up as `just gen-oid-names` (a new Justfile target, invoking `uv run
  scripts/gen_oid_names.py`) — a manually-run, rarely-needed step, same as `gen-types` and
  `gen-validator` are today (neither is part of `hook`/`ci`).

**Test contract — `oidviz/tests/unit/oidNames.test.ts`** (rewrite for the new return shape; every
value below is real, verified against the actual compiled output):

| Input OID | Expected result |
| --- | --- |
| `1.3.6.1.2.1.1.1.0` | `{ name: "sysDescr", description: "A textual description of the entity." }` |
| `9.9.9.9` | `null` (genuinely unrecognized — outside every compiled module) |
| `1.3.6.1.2.1.2.2.1.2.1` | `{ name: "ifDescr", description: "A textual string containing information about the interface." }` — proves longest-prefix match picks the column entry over its parent table-row entry |
| `1.3.6.1.20` | `{ name: "internet", description: null }`, **not** a false match against `1.3.6.1.2` ("mgmt") — proves the arc-boundary check still holds, not just a raw string-prefix check |
| `1.3.6.1.2.1.1` | `{ name: "system", description: null }` — exact-OID-equals-prefix match |
| `1.3.6.1.4.1` | `{ name: "enterprises", description: null }` — a structural node with no DESCRIPTION clause |
| `1.3.6.1.4.1.9.1.1` | `{ name: "enterprises", description: null }` — a dropped vendor OID (Cisco) resolves through the generic ancestor, **not** `null`; distinguish this from the truly-unrecognized case above |

**Test contract — `oidviz/tests/unit/oidTrie.test.ts`** (add to the existing `buildTrie` and
`flatten` describe blocks — these prove the *real* wiring works, since the component tests in Tasks
2–3 only prove Vue renders synthetic props correctly): building a trie from an exchange whose
response OID is `1.3.6.1.2.1.1.1.0` must produce a leaf row with `name: "sysDescr"` and `description:
"A textual description of the entity."`, and its ancestor node at `1.3.6.1.2.1.1` must have `name:
"system"`, `description: null`.

- [ ] **Step 1:** Write both test files above against the not-yet-existing `oidNames.gen.ts` /
      not-yet-updated `TrieNode`/`FlatRow` shape. Run them; confirm they fail (module not found /
      type errors) — this is the TDD baseline this task fills in.
- [ ] **Step 2:** Write `gen_oid_names.py` per the facts above, run it, and confirm the generated
      file's entry count is in the same order of magnitude as verified (roughly 900–1000 entries —
      investigate if wildly different).
- [ ] **Step 3:** Delete `oidNames.ts`. Propagate the new `TrieNode.description` and `FlatRow`
      leaf `name`/`description` fields through `model.ts`, `oidTrie.ts` (import path, `makeNode`,
      both leaf-push sites in `flatten`), and the two mechanical call sites that break as a result
      — `helpers.ts`'s `makeTrieNode` factory default, and the one hand-written `FlatRow` leaf
      literal in `OidTree.test.ts`'s `"renders oid, rtt, violation-count badge, and shared badge"`
      test (both just need `name: null, description: null` added; neither is testing names).
- [ ] **Step 4:** Wire up `just gen-oid-names` and the three lint/format exemptions.
- [ ] **Step 5:** Run both test files from Step 1 again; confirm they pass. Run `cd oidviz && just
      hook`; confirm fully green.
- [ ] **Step 6:** Commit.

---

## Task 2: Show names and descriptions in the OID Tree *(model: Sonnet)*

**Outcome:** In `OidTree.vue`, a node row's description (when present) shows as its native hover
tooltip on the existing name label. A leaf row gains a name label next to the OID, and its tooltip
switches from repeating the already-visible OID to showing the description instead (the OID text
is redundant as a tooltip once a description exists). Absent name/description behaves exactly like
today's absent-name case — no label, no tooltip, nothing shown as literal `"null"`.

**Test contract — add to `oidviz/tests/component/OidTree.test.ts`**, following this file's
existing per-test-comment convention:

| Test | Synthetic setup | Assertion |
| --- | --- | --- |
| node row shows description as a tooltip | a node with `name: "sysDescr"`, `description` set | the `.trie-name` element's `title` attribute equals the description |
| leaf row shows a name label and description tooltip | a leaf row with `name`/`description` set | a new `.trie-leaf-name` element's text equals the name; `.trie-leaf-oid`'s `title` equals the description (not the OID) |
| leaf row omits the name label when unresolved | a leaf row with `name: null, description: null` | no `.trie-leaf-name` element exists; `.trie-leaf-oid` has no `title` attribute at all |

- [ ] **Step 1:** Write the three tests above. Run them; confirm they fail (the assertions about
      `title`/`.trie-leaf-name` don't hold against today's template).
- [ ] **Step 2:** Update `OidTree.vue`'s template: bind the node-name span's `title` to its
      description, add a `.trie-leaf-name` label span next to the leaf-oid span (styled like the
      existing `.trie-name` class), and switch the leaf-oid span's `title` from the OID to the
      description.
- [ ] **Step 3:** Run the tests again; confirm they pass, along with the rest of the file. Run `cd
      oidviz && just hook`; confirm green.
- [ ] **Step 4:** Commit.

---

## Task 3: Show the resolved name in the Minimap+Detail tooltip *(model: Sonnet)*

**Outcome:** Hovering a Detail-canvas row whose OID resolves to a known name shows that name as an
extra line in the existing floating tooltip, between the OID and the RTT line, HTML-escaped the
same way the OID already is. An unresolved OID's tooltip is unchanged from today (OID, RTT, status
only — no empty gap where a name would go).

**Test contract — add to `oidviz/tests/component/MinimapDetail.test.ts`**'s `"detail interaction"`
block, following this file's existing per-test-comment convention. Both exercise a single exchange
at `sentAtMs: 0`, hovered at `detailRowY(0)` — the same setup the existing detail-hover tests
already use:

| Test | requestOid | Expected tooltip `innerHTML` |
| --- | --- | --- |
| recognized OID shows its name | `1.3.6.1.2.1.1.1.0` (`sysDescr`) | `<strong>1.3.6.1.2.1.1.1.0</strong><br>sysDescr<br>RTT: 100.0ms<br>Status: Normal` |
| unrecognized OID shows no name line | `9.9.9.9` | `<strong>9.9.9.9</strong><br>RTT: 100.0ms<br>Status: Normal` |

- [ ] **Step 1:** Write both tests above. Run them; confirm they fail (today's tooltip has no name
      line, so neither `innerHTML` matches).
- [ ] **Step 2:** In `MinimapDetail.vue`'s `onDetailHover`, resolve the exchange's `requestOid` via
      `lookupOidName` (new import from `oidNames.gen.ts`) and, when resolved, insert an extra
      `<br>`-separated line for the name — escaped through the existing `escHtml` helper, same as
      the OID already is — between the OID line and the RTT line.
- [ ] **Step 3:** Run the tests again; confirm they pass, along with the rest of the file. Two
      pre-existing tests already hover `sysDescr.0`/a vendor OID and use loose `toContain`
      assertions — confirm they still pass unchanged (they don't assert the *absence* of a name
      line, so the new text is additive, not breaking). Run `cd oidviz && just hook`; confirm
      green.
- [ ] **Step 4:** Commit.

---

## Final verification

- [ ] Once all three tasks are committed, run `cd oidviz && just ci` (adds Playwright e2e + a11y
      on top of `just hook`) and confirm it's green.
