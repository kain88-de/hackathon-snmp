# /// script
# requires-python = ">=3.11"
# dependencies = ["pysmi==2.0.0"]
# ///
"""Generate src/lib/oidNames.gen.ts from standard IETF MIB source files.

Compiles a fixed set of standard MIB modules fetched from
https://mibs.pysnmp.com into a longest-prefix-match table mapping OID prefixes
to per-object names and one-sentence descriptions. Only standard MIBs are
compiled; vendor OIDs resolve through their generic IANA ancestor at lookup
time. Run via `just gen-oid-names` whenever the module set changes.
"""

import json
import re
import sys
import tempfile
from pathlib import Path

from pysmi.codegen import JsonCodeGen
from pysmi.compiler import MibCompiler
from pysmi.parser import SmiV1CompatParser
from pysmi.reader import get_readers_from_urls
from pysmi.searcher import AnyFileSearcher
from pysmi.writer import FileWriter

# Modules compiled together, in resolution priority order: every modern module
# precedes RFC1213-MIB, which they obsolete, so RFC1213-MIB only fills genuine
# gaps (notably ICMP, which has no standalone module in this repository).
# SNMPv2-SMI is compiled directly (no StubSearcher) so its structural nodes
# (internet, mgmt, enterprises, ...) are emitted rather than assumed-known.
MODULES = [
    "SNMPv2-SMI",
    "SNMPv2-MIB",
    "IF-MIB",
    "IP-MIB",
    "TCP-MIB",
    "UDP-MIB",
    "HOST-RESOURCES-MIB",
    "BRIDGE-MIB",
    "ENTITY-MIB",
    "SNMP-FRAMEWORK-MIB",
    "SNMP-USER-BASED-SM-MIB",
    "SNMP-VIEW-BASED-ACM-MIB",
    "SNMP-COMMUNITY-MIB",
    "RFC1213-MIB",
]

MIB_URL = "https://mibs.pysnmp.com/asn1/@mib@"

OUT_PATH = Path(__file__).resolve().parent.parent / "src" / "lib" / "oidNames.gen.ts"


def compile_modules(dest_dir: Path) -> None:
    """Compile MODULES to JSON in dest_dir; exit non-zero if any one fails."""
    compiler = MibCompiler(
        SmiV1CompatParser(),
        JsonCodeGen(),
        FileWriter(str(dest_dir)).set_options(suffix=".json"),
    )
    compiler.add_sources(*get_readers_from_urls(MIB_URL))
    compiler.add_searchers(AnyFileSearcher(str(dest_dir)).set_options(exts=[".json"]))

    # genTexts=True is required, or every description field is omitted entirely.
    # ignoreErrors=True lets unrelated transitive dependencies fail harmlessly.
    results = compiler.compile(*MODULES, genTexts=True, ignoreErrors=True)

    failed = [name for name in MODULES if str(results.get(name)) != "compiled"]
    if failed:
        print(
            f"error: requested modules did not compile: {failed}",
            file=sys.stderr,
        )
        sys.exit(1)


def first_sentence(text: str) -> str:
    """Collapse whitespace and truncate to the first sentence (a tooltip label)."""
    normalized = " ".join(text.split())
    match = re.search(r"[.!?]", normalized)
    return normalized[: match.end()] if match else normalized


def build_table(dest_dir: Path) -> list[tuple[str, str, str | None]]:
    """Collect (oid, name, description) tuples, keeping the first OID seen."""
    seen: dict[str, tuple[str, str, str | None]] = {}
    for module in MODULES:
        data = json.loads((dest_dir / f"{module}.json").read_text())
        for name, entry in data.items():
            # Only "imports" and "meta" lack an "oid"; everything else is a symbol.
            if not isinstance(entry, dict) or "oid" not in entry:
                continue
            oid = entry["oid"]
            if oid in seen:
                continue
            description = entry.get("description")
            seen[oid] = (
                oid,
                name,
                first_sentence(description) if description else None,
            )
    return list(seen.values())


def render_ts(rows: list[tuple[str, str, str | None]]) -> str:
    """Render the generated TypeScript module."""
    entries = ",\n".join(
        "\t" + json.dumps([oid, name, description]) for oid, name, description in rows
    )
    return f"""// GENERATED FILE. DO NOT EDIT BY HAND.
// Regenerate with `just gen-oid-names`.
import type {{ OidString }} from "./model.ts";

const RAW_PREFIXES: [string, string, string | null][] = [
{entries},
];

// Sorted descending by prefix length at module init — most-specific match wins.
const SORTED_PREFIXES: [string, string, string | null][] = [...RAW_PREFIXES].sort(
\t(a, b): number => b[0].length - a[0].length,
);

export function lookupOidName(
\toid: OidString,
): {{ name: string; description: string | null }} | null {{
\tfor (const [prefix, name, description] of SORTED_PREFIXES) {{
\t\tif (
\t\t\toid.startsWith(prefix) &&
\t\t\t(oid.length === prefix.length || oid[prefix.length] === ".")
\t\t) {{
\t\t\treturn {{ name, description }};
\t\t}}
\t}}
\treturn null;
}}
"""


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        dest_dir = Path(tmp)
        compile_modules(dest_dir)
        rows = build_table(dest_dir)
    OUT_PATH.write_text(render_ts(rows))
    print(f"wrote {len(rows)} entries to {OUT_PATH}")


if __name__ == "__main__":
    main()
