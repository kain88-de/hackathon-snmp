import { describe, expect, test } from "vitest";
import {
	isValidExchange,
	isValidHeader,
	isValidSummary,
	isValidSystemInfo,
	parseTrace,
} from "../../src/lib/parser.worker.ts";

function validHeader(): Record<string, unknown> {
	return {
		format_version: 1,
		session: { id: "s1", run: 1, runs_total: 1 },
		settings: { bulk_size: 0, retries: 3, start_oid: "1.3.6.1", timeout_s: 1 },
		snmp: { version: "2c" },
		started_at: "2026-07-20T00:00:00Z",
		tool: "oidtrace",
		type: "header",
	};
}

function validExchange(): Record<string, unknown> {
	return {
		attempts: [{ received_at: 0.1, sent_at: 0 }],
		request: { oids: ["1.3.6.1"], pdu: "getnext", request_id: 1 },
		seq: 1,
		type: "exchange",
	};
}

describe("isValidHeader", () => {
	test("accepts a well-formed header record", () => {
		expect(isValidHeader(validHeader())).toBe(true);
	});

	test("rejects a header missing settings.start_oid", () => {
		const record = validHeader();
		record.settings = { bulk_size: 0, retries: 3, timeout_s: 1 };
		expect(isValidHeader(record)).toBe(false);
	});

	test("rejects a header whose snmp is not an object", () => {
		const record = validHeader();
		record.snmp = "2c";
		expect(isValidHeader(record)).toBe(false);
	});
});

describe("isValidSystemInfo", () => {
	test("accepts a well-formed system_info record", () => {
		expect(
			isValidSystemInfo({ at: 0, point: "start", type: "system_info", values: {} }),
		).toBe(true);
	});

	test("rejects an unknown point value", () => {
		expect(
			isValidSystemInfo({ at: 0, point: "middle", type: "system_info", values: {} }),
		).toBe(false);
	});
});

describe("isValidExchange", () => {
	test("accepts a well-formed exchange record", () => {
		expect(isValidExchange(validExchange())).toBe(true);
	});

	test("rejects an exchange with an empty attempts array", () => {
		const record = validExchange();
		record.attempts = [];
		expect(isValidExchange(record)).toBe(false);
	});

	test("rejects an exchange whose request is missing oids", () => {
		const record = validExchange();
		record.request = { pdu: "getnext", request_id: 1 };
		expect(isValidExchange(record)).toBe(false);
	});

	test("rejects an exchange whose response varbind has a non-string oid", () => {
		const record = validExchange();
		record.response = {
			error_index: 0,
			error_status: 0,
			request_id: 1,
			varbinds: [{ oid: 123, vlen: 0, vtype: "Integer" }],
		};
		expect(isValidExchange(record)).toBe(false);
	});
});

describe("isValidSummary", () => {
	test("accepts a well-formed summary record", () => {
		expect(
			isValidSummary({
				at: 1,
				end_reason: "completed",
				exchanges: 1,
				oids_seen: 1,
				type: "summary",
				violation_counts: {},
			}),
		).toBe(true);
	});

	test("rejects a summary with a non-numeric exchanges count", () => {
		expect(
			isValidSummary({
				at: 1,
				end_reason: "completed",
				exchanges: "1",
				oids_seen: 1,
				type: "summary",
				violation_counts: {},
			}),
		).toBe(false);
	});
});

async function gzipLines(lines: string[]): Promise<ArrayBuffer> {
	const cs = new CompressionStream("gzip");
	const writer = cs.writable.getWriter();
	writer.write(new TextEncoder().encode(`${lines.join("\n")}\n`));
	writer.close();
	const chunks: Uint8Array[] = [];
	const reader = cs.readable.getReader();
	for (;;) {
		const { done, value } = await reader.read();
		if (done) {
			break;
		}
		chunks.push(value);
	}
	const total = chunks.reduce((sum, chunk): number => sum + chunk.length, 0);
	const buffer = new Uint8Array(total);
	let offset = 0;
	for (const chunk of chunks) {
		buffer.set(chunk, offset);
		offset += chunk.length;
	}
	return buffer.buffer;
}

describe("parseTrace", () => {
	test("a malformed exchange mid-file truncates instead of throwing", async () => {
		const goodExchange = JSON.stringify(validExchange());
		const badExchange = JSON.stringify({ ...validExchange(), attempts: [] });
		const buffer = await gzipLines([
			JSON.stringify(validHeader()),
			goodExchange,
			badExchange,
			goodExchange,
		]);

		const result = await parseTrace(buffer);

		expect(result.truncated).toBe(true);
		expect(result.exchanges).toHaveLength(1);
	});

	test("a malformed header surfaces as the existing missing-header error, not a downstream crash", async () => {
		const badHeader = JSON.stringify({ ...validHeader(), settings: undefined });
		const buffer = await gzipLines([badHeader]);

		await expect(parseTrace(buffer)).rejects.toThrow("Trace file missing header record");
	});
});
