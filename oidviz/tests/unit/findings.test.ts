import { describe, expect, test } from "bun:test";
import { asOid } from "../../src/lib/model.ts";
import type { DomainExchange } from "../../src/lib/model.ts";
import { categorise } from "../../src/lib/findings.ts";

function makeExchange(overrides: Partial<DomainExchange> = {}): DomainExchange {
	return {
		seq: 1,
		rtt: 100,
		isTimeout: false,
		violations: [],
		attemptCount: 1,
		requestOid: asOid("1.3.6.1.2.1.1.1.0"),
		responseOids: [],
		sentAtMs: 0,
		receivedAtMs: 100,
		...overrides,
	};
}

describe("categorise", () => {
	test("empty exchanges → empty Findings", () => {
		const result = categorise([], 1000);
		expect(result.slow).toHaveLength(0);
		expect(result.timeout).toHaveLength(0);
		expect(result.fast).toHaveLength(0);
	});

	test("slow exchange (rtt > slowMs, !isTimeout) → in slow section", () => {
		const ex = makeExchange({ rtt: 2000 });
		const result = categorise([ex], 1000);
		expect(result.slow).toContain(ex);
		expect(result.timeout).toHaveLength(0);
		expect(result.fast).toHaveLength(0);
	});

	test("timeout exchange (isTimeout) → in timeout section", () => {
		const ex = makeExchange({ isTimeout: true });
		const result = categorise([ex], 1000);
		expect(result.timeout).toContain(ex);
		expect(result.slow).toHaveLength(0);
		expect(result.fast).toHaveLength(0);
	});

	test("fast exchange (rtt <= slowMs, !isTimeout) → in fast section", () => {
		const ex = makeExchange({ rtt: 500 });
		const result = categorise([ex], 1000);
		expect(result.fast).toContain(ex);
		expect(result.slow).toHaveLength(0);
		expect(result.timeout).toHaveLength(0);
	});

	test("exchange at exactly slowMs → in fast section", () => {
		const ex = makeExchange({ rtt: 1000 });
		const result = categorise([ex], 1000);
		expect(result.fast).toContain(ex);
		expect(result.slow).toHaveLength(0);
	});

	test("slow section sorted RTT desc", () => {
		const a = makeExchange({ seq: 1, rtt: 1500 });
		const b = makeExchange({ seq: 2, rtt: 3000 });
		const c = makeExchange({ seq: 3, rtt: 2000 });
		const result = categorise([a, b, c], 1000);
		expect(result.slow.map((e) => e.rtt)).toEqual([3000, 2000, 1500]);
	});

	test("timeout section sorted seq asc", () => {
		const a = makeExchange({ seq: 5, isTimeout: true });
		const b = makeExchange({ seq: 1, isTimeout: true });
		const c = makeExchange({ seq: 3, isTimeout: true });
		const result = categorise([a, b, c], 1000);
		expect(result.timeout.map((e) => e.seq)).toEqual([1, 3, 5]);
	});

	test("fast section sorted violation count desc then RTT desc", () => {
		const a = makeExchange({ seq: 1, rtt: 800, violations: ["v1"] });
		const b = makeExchange({ seq: 2, rtt: 900, violations: ["v1", "v2"] });
		const c = makeExchange({ seq: 3, rtt: 700, violations: ["v1"] });
		const result = categorise([a, b, c], 1000);
		// b has 2 violations (first), then a (rtt 800) before c (rtt 700)
		expect(result.fast[0]).toBe(b);
		expect(result.fast[1]).toBe(a);
		expect(result.fast[2]).toBe(c);
	});

	test("exchange with isTimeout:true does NOT appear in slow section", () => {
		const ex = makeExchange({ isTimeout: true, rtt: 5000 });
		const result = categorise([ex], 1000);
		expect(result.slow).toHaveLength(0);
		expect(result.timeout).toContain(ex);
	});
});
