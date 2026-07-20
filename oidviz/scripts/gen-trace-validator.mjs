// Compiles traceformat/trace-format.schema.json into a standalone runtime
// validator per record type, so oidviz validates untrusted trace records
// against the same authoritative schema that gen-types derives its
// compile-time types from. Regenerate with `just gen-validator` whenever the
// schema changes.
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import Ajv2020 from "ajv/dist/2020.js";
import standaloneCode from "ajv/dist/standalone/index.js";

const scriptDir = fileURLToPath(new URL(".", import.meta.url));
const schemaPath = `${scriptDir}../../traceformat/trace-format.schema.json`;
const outPath = `${scriptDir}../src/lib/traceValidator.gen.js`;

const schema = JSON.parse(readFileSync(schemaPath, "utf8"));

const ajv = new Ajv2020({
	allErrors: true,
	code: { esm: true, lines: true, source: true },
	strict: false,
	// date-time format checking would need the ajv-formats runtime helper;
	// skipped to keep the generated validator dependency-free, matching the
	// scope of what oidviz actually needs at this boundary.
	validateFormats: false,
});
ajv.addSchema(schema, "trace");

// Only the record types oidviz's parser dispatches on. "event" records exist
// in the format but are never read by the app, so — like any other unknown
// record type — they're intentionally left unvalidated and skipped.
const exports = {
	validateExchange: "trace#/$defs/exchange",
	validateHeader: "trace#/$defs/header",
	validateSummary: "trace#/$defs/summary",
	validateSystemInfo: "trace#/$defs/system_info",
};
for (const ref of Object.values(exports)) {
	ajv.compile({ $ref: ref });
}

const banner = `// GENERATED FILE. DO NOT EDIT BY HAND.
// Regenerate with: just gen-validator
// Compiled from traceformat/trace-format.schema.json — see
// scripts/gen-trace-validator.mjs and the hand-written sidecar
// traceValidator.gen.d.ts.
`;

writeFileSync(outPath, banner + standaloneCode(ajv, exports));
console.log(`wrote ${outPath}`);
