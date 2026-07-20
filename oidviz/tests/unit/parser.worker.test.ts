import { describe, expect, test } from "vitest";
import { parseTrace } from "../../src/lib/parser.worker.ts";

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

function validExchange(seq: number): Record<string, unknown> {
	return {
		attempts: [{ received_at: 0.1, sent_at: 0 }],
		request: { oids: ["1.3.6.1"], pdu: "getnext", request_id: seq },
		seq,
		type: "exchange",
	};
}

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
		const goodExchange = JSON.stringify(validExchange(1));
		const badExchange = JSON.stringify({ ...validExchange(99), attempts: [] });
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

	// The trace format spec requires readers to ignore record types they don't
	// recognize (forward compatibility for future record kinds), so this must
	// stay a no-op rather than a validation failure — even though the schema's
	// top-level shape is a discriminated oneOf that would otherwise reject any
	// record whose type doesn't match one of its five known branches.
	test("an unrecognized record type is skipped, not treated as invalid", async () => {
		const buffer = await gzipLines([
			JSON.stringify(validHeader()),
			JSON.stringify(validExchange(1)),
			JSON.stringify({ note: "reserved for a future feature", type: "future_feature" }),
			JSON.stringify(validExchange(2)),
		]);

		const result = await parseTrace(buffer);

		expect(result.truncated).toBe(false);
		expect(result.exchanges).toHaveLength(2);
	});

	// A getbulk request must carry non_repeaters/max_repetitions per the
	// schema's if/then invariant — a check the previous hand-written validator
	// didn't enforce (out of its scope) but the generated one gets for free
	// straight from trace-format.schema.json.
	test("a getbulk request missing non_repeaters/max_repetitions is rejected", async () => {
		const badGetbulk = JSON.stringify({
			...validExchange(1),
			request: { oids: ["1.3.6.1"], pdu: "getbulk", request_id: 1 },
		});
		const buffer = await gzipLines([JSON.stringify(validHeader()), badGetbulk]);

		const result = await parseTrace(buffer);

		expect(result.truncated).toBe(true);
		expect(result.exchanges).toHaveLength(0);
	});
});
