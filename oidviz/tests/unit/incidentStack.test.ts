import { describe, expect, test } from "bun:test";
import { asOid } from "../../src/lib/model.ts";
import type { DomainExchange } from "../../src/lib/model.ts";
import { buildIncidents } from "../../src/lib/incidentStack.ts";

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

function makeExchanges(count: number, overrides: Partial<DomainExchange> = {}): DomainExchange[] {
	return Array.from({ length: count }, (_, i) =>
		makeExchange({ seq: i + 1, ...overrides }),
	);
}

const SLOW_MS = 1000;

describe("buildIncidents", () => {
	test("empty exchanges returns empty array", () => {
		expect(buildIncidents([], SLOW_MS)).toEqual([]);
	});

	test("no anomalous exchanges returns empty array", () => {
		const exchanges = makeExchanges(10, { rtt: 100 });
		expect(buildIncidents(exchanges, SLOW_MS)).toEqual([]);
	});

	test("single anomalous exchange produces one incident", () => {
		const exchanges = [makeExchange({ rtt: 2000, seq: 1 })];
		const incidents = buildIncidents(exchanges, SLOW_MS);
		expect(incidents).toHaveLength(1);
		expect(incidents[0]?.members).toEqual([0]);
		expect(incidents[0]?.peakRtt).toBe(2000);
	});

	test("gap of exactly 8 non-anomalous exchanges merges into one incident", () => {
		// anomalous at index 0, 8 normal (idx 1-8), anomalous at index 9
		// gap = 9 - 0 - 1 = 8 → merge
		const exchanges: DomainExchange[] = [
			makeExchange({ seq: 1, rtt: 2000 }),          // idx 0: anomalous
			...makeExchanges(8).map((ex, i) => ({         // idx 1-8: normal
				...ex,
				seq: i + 2,
				rtt: 100,
			})),
			makeExchange({ seq: 10, rtt: 2000 }),         // idx 9: anomalous
		];
		const incidents = buildIncidents(exchanges, SLOW_MS);
		expect(incidents).toHaveLength(1);
		expect(incidents[0]?.members).toEqual([0, 9]);
	});

	test("gap of exactly 9 non-anomalous exchanges splits into two incidents", () => {
		// anomalous at index 0, 9 normal (idx 1-9), anomalous at index 10
		// gap = 10 - 0 - 1 = 9 → split
		const exchanges: DomainExchange[] = [
			makeExchange({ seq: 1, rtt: 2000 }),           // idx 0: anomalous
			...makeExchanges(9).map((ex, i) => ({          // idx 1-9: normal
				...ex,
				seq: i + 2,
				rtt: 100,
			})),
			makeExchange({ seq: 11, rtt: 2000 }),          // idx 10: anomalous
		];
		const incidents = buildIncidents(exchanges, SLOW_MS);
		expect(incidents).toHaveLength(2);
	});

	test("retryCount is sum of (attemptCount - 1), not count of retrying exchanges", () => {
		// 2 anomalous exchanges: one with attemptCount=3 (+2), one with attemptCount=2 (+1) → sum=3
		const exchanges = [
			makeExchange({ seq: 1, rtt: 2000, attemptCount: 3 }),
			makeExchange({ seq: 2, rtt: 2000, attemptCount: 2 }),
		];
		const incidents = buildIncidents(exchanges, SLOW_MS);
		expect(incidents).toHaveLength(1);
		expect(incidents[0]?.retryCount).toBe(3); // (3-1) + (2-1) = 3
	});

	test("retryCount is NOT count of exchanges with retries", () => {
		// 2 exchanges both with attemptCount=2 → retryCount=2, not 2 exchanges but sum=(2-1)+(2-1)=2
		// verify this is 2, not "2 exchanges"
		// More distinctive: 1 exchange with attemptCount=5 → retryCount=4
		const exchanges = [
			makeExchange({ seq: 1, rtt: 2000, attemptCount: 5 }),
		];
		const incidents = buildIncidents(exchanges, SLOW_MS);
		expect(incidents[0]?.retryCount).toBe(4); // 5-1=4, not 1 (count)
	});

	test("region label uses lookupOidName for known OID prefix", () => {
		const exchanges = [
			makeExchange({ seq: 1, rtt: 2000, requestOid: asOid("1.3.6.1.2.1.1.1.0") }),
		];
		const incidents = buildIncidents(exchanges, SLOW_MS);
		// "1.3.6.1.2.1.1" → "System MIB"
		expect(incidents[0]?.region).toBe("System MIB");
	});

	test("region label uses 3-arc prefix for unknown OID", () => {
		const exchanges = [
			makeExchange({ seq: 1, rtt: 2000, requestOid: asOid("9.9.9.1.2.3.4") }),
		];
		const incidents = buildIncidents(exchanges, SLOW_MS);
		expect(incidents[0]?.region).toBe("9.9.9");
	});

	test("score is computed correctly", () => {
		// violations: 1 type (+1000), peakRtt=2000, retryCount=2 (+200), timeoutCount=0
		const exchanges = [
			makeExchange({
				seq: 1,
				rtt: 2000,
				violations: ["wrong-type"],
				attemptCount: 3, // retryCount += 2
			}),
		];
		const incidents = buildIncidents(exchanges, SLOW_MS);
		expect(incidents[0]?.score).toBe(1000 + 2000 + 2 * 100 + 0 * 500);
	});

	test("incidents are sorted by score descending", () => {
		// Two separate incident groups:
		// group A: high rtt (score=3000)
		// group B: timeout (score=500+200=700)
		// gap >= 9 between groups ensures split
		const exchanges: DomainExchange[] = [
			// idx 0: group B (lower score): timeout + rtt=200
			makeExchange({ seq: 1, rtt: 200, isTimeout: true }),
			// idx 1-9: normal gap (9 exchanges → split)
			...Array.from({ length: 9 }, (_, i) => makeExchange({ seq: i + 2, rtt: 100 })),
			// idx 10: group A (higher score): rtt=3000
			makeExchange({ seq: 11, rtt: 3000 }),
		];
		const incidents = buildIncidents(exchanges, SLOW_MS);
		expect(incidents).toHaveLength(2);
		// group A has score = 3000 (rtt only)
		// group B has score = 200 (rtt) + 500 (timeout) = 700
		expect(incidents[0]?.peakRtt).toBe(3000); // highest score first
		expect(incidents[1]?.timeoutCount).toBe(1);
	});

	test("timeout exchange is anomalous", () => {
		const exchanges = [
			makeExchange({ seq: 1, rtt: 50, isTimeout: true }),
		];
		const incidents = buildIncidents(exchanges, SLOW_MS);
		expect(incidents).toHaveLength(1);
		expect(incidents[0]?.timeoutCount).toBe(1);
	});

	test("violation exchange is anomalous", () => {
		const exchanges = [
			makeExchange({ seq: 1, rtt: 50, violations: ["oid-mismatch"] }),
		];
		const incidents = buildIncidents(exchanges, SLOW_MS);
		expect(incidents).toHaveLength(1);
		expect(incidents[0]?.violationTypes).toEqual(new Set(["oid-mismatch"]));
	});

	test("violationTypes collects all distinct violations across members", () => {
		const exchanges = [
			makeExchange({ seq: 1, rtt: 2000, violations: ["wrong-type", "oid-mismatch"] }),
			makeExchange({ seq: 2, rtt: 2000, violations: ["wrong-type"] }),
		];
		const incidents = buildIncidents(exchanges, SLOW_MS);
		expect(incidents).toHaveLength(1);
		expect(incidents[0]?.violationTypes).toEqual(new Set(["wrong-type", "oid-mismatch"]));
	});

	test("startIdx and endIdx span the whole window including gap", () => {
		// anomalous at 0, gap 3, anomalous at 4 → startIdx=0, endIdx=4
		const exchanges: DomainExchange[] = [
			makeExchange({ seq: 1, rtt: 2000 }),
			makeExchange({ seq: 2, rtt: 100 }),
			makeExchange({ seq: 3, rtt: 100 }),
			makeExchange({ seq: 4, rtt: 100 }),
			makeExchange({ seq: 5, rtt: 2000 }),
		];
		const incidents = buildIncidents(exchanges, SLOW_MS);
		expect(incidents).toHaveLength(1);
		expect(incidents[0]?.startIdx).toBe(0);
		expect(incidents[0]?.endIdx).toBe(4);
	});
});
