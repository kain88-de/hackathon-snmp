// Generates the 5 e2e test-data fixtures consumed by the Playwright suite.
// Run via `just gen-test-data` (or `bun tests/e2e/test-data/generate.mjs`).
//
// Record shapes follow docs/trace-format.md §4; the consumer that reads these
// files is oidviz/src/lib/parser.worker.ts. Keep the two in sync.
//
// NOTE: response OIDs are truncated to their first 7 arcs before dedup in the
// parser (truncateOid). OIDs here were chosen so that counts come out right.

import { gzipSync } from "node:zlib";
import { writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const OUT_DIR = dirname(fileURLToPath(import.meta.url));

/** Join records into gzip-compressed JSON Lines with a trailing newline. */
function toGzipJsonl(records) {
	const text = records.map((r) => JSON.stringify(r)).join("\n") + "\n";
	return gzipSync(text);
}

function write(name, buffer) {
	writeFileSync(join(OUT_DIR, name), buffer);
}

const SESSION_ID = "5e1f3a9c-6a86-4a0b-9b6e-2f6d6a9c1d42";

/** Header shared by all valid fixtures, matching the brief's settings. */
function header() {
	return {
		type: "header",
		format_version: 1,
		tool: "oidtrace 0.1.0",
		started_at: "2026-06-11T14:03:07Z",
		label: "test-walk",
		session: { id: SESSION_ID, run: 1, runs_total: 1 },
		snmp: { version: "2c" },
		settings: {
			bulk_size: 10,
			timeout_s: 2,
			retries: 1,
			start_oid: "1.3.6.1",
			time_budget_s: 30,
			resume_from: "1.3.6.1.2.1.4.20",
		},
	};
}

/** A single-attempt exchange that got a response. */
function exchangeOk({ seq, requestOid, responseOid, sentAt, rttS, violations }) {
	const rec = {
		type: "exchange",
		seq,
		request: { pdu: "getnext", request_id: 1000 + seq, oids: [requestOid] },
		attempts: [{ sent_at: sentAt, received_at: sentAt + rttS }],
		response: {
			request_id: 1000 + seq,
			error_status: 0,
			error_index: 0,
			varbinds: [{ oid: responseOid, vtype: "Counter32", vlen: 4 }],
		},
	};
	if (violations !== undefined) {
		rec.violations = violations;
	}
	return rec;
}

/** A single-attempt exchange that timed out (no response, no OID). */
function exchangeTimeout({ seq, requestOid, sentAt }) {
	return {
		type: "exchange",
		seq,
		request: { pdu: "getnext", request_id: 1000 + seq, oids: [requestOid] },
		attempts: [{ sent_at: sentAt, received_at: null }],
	};
}

/** A two-attempt exchange: first attempt timed out, retry got a response. */
function exchangeRetry({ seq, requestOid, responseOid, sentAt, retrySentAt, rttS }) {
	return {
		type: "exchange",
		seq,
		request: { pdu: "getnext", request_id: 1000 + seq, oids: [requestOid] },
		attempts: [
			{ sent_at: sentAt, received_at: null },
			{ sent_at: retrySentAt, received_at: retrySentAt + rttS },
		],
		response: {
			request_id: 1000 + seq,
			error_status: 0,
			error_index: 0,
			varbinds: [{ oid: responseOid, vtype: "OctetString", vlen: 12 }],
		},
	};
}

// --- canonical: one exchange per performance/correctness category ---------
const canonical = [
	header(),
	{
		type: "system_info",
		at: 0.05,
		point: "start",
		values: {
			"1.3.6.1.2.1.1.1.0": "Test Device R1\nBuild 42",
			"1.3.6.1.2.1.1.2.0": "1.3.6.1.4.1.9999.1",
			"1.3.6.1.2.1.1.3.0": 12345,
		},
	},
	// seq 1: fast, 50ms
	exchangeOk({
		seq: 1,
		requestOid: "1.3.6.1.2.1.2.2.1.10",
		responseOid: "1.3.6.1.2.1.2.2.1.10.1",
		sentAt: 1.0,
		rttS: 0.05,
	}),
	// seq 2: slow, 1500ms
	exchangeOk({
		seq: 2,
		requestOid: "1.3.6.1.2.1.2.2.1.16",
		responseOid: "1.3.6.1.2.1.2.2.1.16.1",
		sentAt: 2.0,
		rttS: 1.5,
	}),
	// seq 3: timeout
	exchangeTimeout({
		seq: 3,
		requestOid: "1.3.6.1.2.1.2.2.1.20",
		sentAt: 4.0,
	}),
	// seq 4: fast + violation, 20ms
	exchangeOk({
		seq: 4,
		requestOid: "1.3.6.1.4.1.9999.23.1.1",
		responseOid: "1.3.6.1.4.1.9999.23.1.2",
		sentAt: 7.0,
		rttS: 0.02,
		violations: ["oid-not-increasing"],
	}),
	// seq 5: fast + retry, 50ms on the retry attempt
	exchangeRetry({
		seq: 5,
		requestOid: "1.3.6.1.2.1.1.5",
		responseOid: "1.3.6.1.2.1.1.5.0",
		sentAt: 8.0,
		retrySentAt: 10.0,
		rttS: 0.05,
	}),
	{
		type: "summary",
		at: 11.0,
		exchanges: 5,
		oids_seen: 4,
		end_reason: "completed",
		violation_counts: { "oid-not-increasing": 1 },
	},
];
write("canonical.oidtrace.jsonl.gz", toGzipJsonl(canonical));

// --- no-summary: 2 clean exchanges, no summary record ---------------------
const noSummary = [
	header(),
	exchangeOk({
		seq: 1,
		requestOid: "1.3.6.1.2.1.2.2.1.3",
		responseOid: "1.3.6.1.2.1.2.2.1.3.1",
		sentAt: 1.0,
		rttS: 0.05,
		violations: ["oid-not-increasing"],
	}),
	exchangeOk({
		seq: 2,
		requestOid: "1.3.6.1.4.1.9.9",
		responseOid: "1.3.6.1.4.1.9.9.1",
		sentAt: 2.0,
		rttS: 0.05,
	}),
];
write("no-summary.oidtrace.jsonl.gz", toGzipJsonl(noSummary));

// --- unknown-record-type: an unknown record between two exchanges ---------
const unknownRecord = [
	header(),
	exchangeOk({
		seq: 1,
		requestOid: "1.3.6.1.2.1.1.1",
		responseOid: "1.3.6.1.2.1.1.1.0",
		sentAt: 1.0,
		rttS: 0.05,
	}),
	{ type: "future_feature", note: "readers must ignore unknown record types" },
	exchangeOk({
		seq: 2,
		requestOid: "1.3.6.1.4.1.9.9",
		responseOid: "1.3.6.1.4.1.9.9.1",
		sentAt: 2.0,
		rttS: 0.05,
	}),
	{
		type: "summary",
		at: 3.0,
		exchanges: 2,
		oids_seen: 2,
		end_reason: "completed",
		violation_counts: {},
	},
];
write("unknown-record-type.oidtrace.jsonl.gz", toGzipJsonl(unknownRecord));

// --- truncated: valid header + one exchange + a cut-off line ---------------
// Simulates a crash mid-write: the last line is incomplete with no newline.
{
	const completeLines =
		[header(), exchangeOk({
			seq: 1,
			requestOid: "1.3.6.1.2.1.2.2.1.3",
			responseOid: "1.3.6.1.2.1.2.2.1.3.1",
			sentAt: 1.0,
			rttS: 0.05,
		})]
			.map((r) => JSON.stringify(r))
			.join("\n") + "\n";
	const cutOff = '{"type":"exchange","seq":2,"request":{"pdu":"get"';
	write("truncated.oidtrace.jsonl.gz", gzipSync(completeLines + cutOff));
}

// --- not-gzip: plain text saved with a .gz extension ----------------------
// Decompression must fail. NOT gzip-compressed.
write("not-gzip.oidtrace.jsonl.gz", Buffer.from("this is not a gzip file\n"));

console.log("Wrote 5 fixtures to", OUT_DIR);
