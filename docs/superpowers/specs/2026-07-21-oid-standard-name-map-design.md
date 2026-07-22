# OID Standard Name Map Design

Date: 2026-07-21
Status: **approved — ready for implementation planning**

A customer wants to know what the OIDs in a walk actually mean, not just which OID
subtree they fall under. Today `oidviz/src/lib/oidNames.ts` is a hand-written table of
~50 prefixes mapping to coarse MIB-group labels (e.g. `1.3.6.1.2.1.2` → "Interfaces
MIB") — it answers "which MIB" but not "which object" or "what does it hold".

## Scope

Standard (IETF/RFC) MIBs only, compiled down to leaf-object granularity: SNMPv2-SMI /
SNMPv2-TC (the meta-modules that define the structural tree names — `internet`,
`mgmt`, `mib-2`, `enterprises`, ...), SNMPv2-MIB, IF-MIB, IP-MIB, ICMP-MIB, TCP-MIB,
UDP-MIB, HOST-RESOURCES-MIB, BRIDGE-MIB, ENTITY-MIB, and the other modules already
represented at group level in today's table.

Vendor/enterprise OIDs (Cisco, Juniper, HP/Aruba, ...) are dropped, not replaced —
explicit tradeoff, decided over an uncertain hand-picked list rather than kept for
false confidence. In practice they resolve to the generic `enterprises` structural
node (`1.3.6.1.4.1`, inherited from SNMPv2-SMI, no description) via longest-prefix
match, not `null` — genuinely unrecognized OIDs (outside the compiled modules
entirely) are the ones that resolve to `null`.

MIB compilation, MIB browser UI, or user-supplied MIB files remain non-goals per
`docs/oidviz.md` — this generates a static table from a fixed, curated MIB set
**ahead of time**; nothing is compiled at runtime and users still cannot upload MIBs.


## Generation

`oidviz/scripts/gen_oid_names.py`: a self-contained `uv run` script (PEP 723 inline
metadata declaring `pysmi`/`pysnmp` as its only deps — no `pyproject.toml`, no uv
workspace membership). It compiles the standard MIB modules via `pysmi`, walks each
module's OBJECT-TYPE/OBJECT-IDENTIFIER nodes, and writes out
`oidviz/src/lib/oidNames.gen.ts`. Wired as `just gen-oid-names` in `oidviz/Justfile`,
run by hand when needed — standard MIBs are stable RFCs, so this should be rare.

`oidNames.gen.ts` fully replaces today's hand-written `oidNames.ts` (deleted). Like
`types.gen.ts` and `traceValidator.gen.js`, it's committed to git, not gitignored, and
never hand-edited. It's self-contained: both the `[oid, name, description][]` data and
the `lookupOidName()` longest-prefix-match function (unchanged algorithm from today,
just more and more-specific entries) live in this one file. `description` is `string |
null` per entry — truncated to the DESCRIPTION clause's first sentence, since plain
`OBJECT IDENTIFIER` structural nodes (`internet`, `mgmt`, ...) have no DESCRIPTION
clause at all, only real
`OBJECT-TYPE`/`MODULE-IDENTITY` nodes do.

If `pysmi` fails to compile a module, the script exits non-zero and writes nothing —
never a partial or silently-wrong `oidNames.gen.ts`.

## Consumers

`lookupOidName`'s return type changes from `string | null` to `{ name: string;
description: string | null } | null`. Three call sites:

- **`oidTrie.ts`** (`model.ts`'s `TrieNode`): gains a `description: string | null`
  field alongside the existing `name`, populated in `makeNode()`.
- **`oidTrie.ts`** (`model.ts`'s `FlatRow` leaf variant): currently carries no name at
  all for leaf rows — gains both `name` and `description`, populated in `flatten()`
  via `lookupOidName(leaf.oid)`. No new matching logic needed: longest-prefix-match
  already resolves table-row/instance suffixes through their parent object today.
- **`OidTree.vue`**: node rows already render `name` — add `description` as the
  span's `title` (native hover tooltip). Leaf rows currently show only the raw OID
  with the OID itself as `title` — add a `name` label next to the OID, and repurpose
  `title` to the description (echoing the already-visible OID back in a tooltip is
  redundant).
- **`MinimapDetail.vue`**'s `onDetailHover`: appends the resolved **name only** (not
  description) to the existing tooltip HTML, escaped via the same `escHtml` already
  used for the OID. This tooltip is for fast scrubbing across the timeline — the name
  alone ("sysDescr") is the "where am I in the spec" signal; the fuller description is
  OidTree's job, where inspection is more deliberate.

Unrecognized OID → `null` → UI silently omits the label/tooltip line, same pattern as
today, now applied uniformly to leaf rows and the Detail tooltip too.

## Testing

- `oidNames.test.ts` moves to `oidNames.gen.ts`'s new `{name, description} | null`
  shape: pins a handful of real, well-known resolutions (`sysDescr`, `ifDescr`,
  `hrSystemUptime`, ...), keeps a null-for-unrecognized-OID case, and adds an explicit
  test that a formerly-labeled vendor OID (e.g. `1.3.6.1.4.1.9.1.1`, "Cisco" today) now
  resolves to `null` — documents the accepted tradeoff instead of leaving it implicit.
- `oidTrie`/`OidTree`/`MinimapDetail` tests each get one fixture OID asserting the name
  (and, for OidTree, description) actually renders.
- No dedicated test suite for `gen_oid_names.py` — it's a one-off dev tool, not shipped
  code; its correctness is verified indirectly by the pinned TS-side tests against its
  committed output.
