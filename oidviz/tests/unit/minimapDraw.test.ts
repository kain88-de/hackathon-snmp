import { describe, expect, test } from "vitest";
import { asOid } from "../../src/lib/model.ts";
import type { DomainExchange } from "../../src/lib/model.ts";
import {
	bucketScore,
	exchangeStatus,
	getColumnBuckets,
	getTimeRange,
	getWindowExchanges,
	worstBucketStatus,
} from "../../src/lib/minimapDraw.ts";

function makeExchange(overrides: Partial<DomainExchange> = {}): DomainExchange {
	return {
		seq: 1,
		rtt: 100,
		isTimeout: false,
		violations: [],
		attemptCount: 1,
		requestOid: asOid("1.3.6.1"),
		responseOids: [],
		sentAtMs: 0,
		receivedAtMs: 100,
		...overrides,
	};
}

const SLOW_MS = 1000;

describe("bucketScore", () => {
	test("empty bucket → 0", () => {
		expect(bucketScore([])).toBe(0);
	});

	test("normal exchange → score based on rtt and count", () => {
		const ex = makeExchange({ rtt: 500 });
		const score = bucketScore([ex]);
		// no violation bonus, so score = 500 * 1000 + 1
		expect(score).toBe(500 * 1000 + 1);
	});

	test("violation adds large bonus", () => {
		const normal = makeExchange({ rtt: 500 });
		const withViolation = makeExchange({ rtt: 100, violations: ["v1"] });
		expect(bucketScore([withViolation])).toBeGreaterThan(bucketScore([normal]));
	});

	test("higher rtt → higher score (no violations)", () => {
		const low = [makeExchange({ rtt: 100 })];
		const high = [makeExchange({ rtt: 900 })];
		expect(bucketScore(high)).toBeGreaterThan(bucketScore(low));
	});

	test("more exchanges in bucket → higher score (same rtt)", () => {
		const one = [makeExchange({ rtt: 100 })];
		const two = [makeExchange({ rtt: 100 }), makeExchange({ rtt: 100 })];
		expect(bucketScore(two)).toBeGreaterThan(bucketScore(one));
	});
});

describe("worstBucketStatus", () => {
	test("empty bucket → Normal", () => {
		expect(worstBucketStatus([], SLOW_MS)).toBe("Normal");
	});

	test("timeout → Timeout", () => {
		const ex = makeExchange({ isTimeout: true });
		expect(worstBucketStatus([ex], SLOW_MS)).toBe("Timeout");
	});

	test("violation → Violation", () => {
		const ex = makeExchange({ violations: ["v1"] });
		expect(worstBucketStatus([ex], SLOW_MS)).toBe("Violation");
	});

	test("slow → Slow", () => {
		const ex = makeExchange({ rtt: 2000 });
		expect(worstBucketStatus([ex], SLOW_MS)).toBe("Slow");
	});

	test("retry → Retry", () => {
		const ex = makeExchange({ attemptCount: 2 });
		expect(worstBucketStatus([ex], SLOW_MS)).toBe("Retry");
	});

	test("timeout wins over violation", () => {
		const timeout = makeExchange({ isTimeout: true });
		const violation = makeExchange({ violations: ["v"] });
		expect(worstBucketStatus([violation, timeout], SLOW_MS)).toBe("Timeout");
	});

	test("violation wins over slow", () => {
		const violation = makeExchange({ violations: ["v"] });
		const slow = makeExchange({ rtt: 2000 });
		expect(worstBucketStatus([slow, violation], SLOW_MS)).toBe("Violation");
	});
});

describe("exchangeStatus", () => {
	test("timeout → Timeout", () => {
		expect(exchangeStatus(makeExchange({ isTimeout: true }), SLOW_MS)).toBe("Timeout");
	});

	test("violation → Violation", () => {
		expect(exchangeStatus(makeExchange({ violations: ["v"] }), SLOW_MS)).toBe("Violation");
	});

	test("slow → Slow", () => {
		expect(exchangeStatus(makeExchange({ rtt: 2000 }), SLOW_MS)).toBe("Slow");
	});

	test("retry → Retry", () => {
		expect(exchangeStatus(makeExchange({ attemptCount: 3 }), SLOW_MS)).toBe("Retry");
	});

	test("normal → Normal", () => {
		expect(exchangeStatus(makeExchange({ rtt: 100 }), SLOW_MS)).toBe("Normal");
	});

	test("timeout takes priority over violation", () => {
		const ex = makeExchange({ isTimeout: true, violations: ["v"] });
		expect(exchangeStatus(ex, SLOW_MS)).toBe("Timeout");
	});
});

describe("getWindowExchanges", () => {
	test("totalCols 0 → returns all exchanges", () => {
		const exchanges = [makeExchange({ sentAtMs: 0 }), makeExchange({ sentAtMs: 100 })];
		expect(getWindowExchanges(exchanges, 0, 0, 10, 100)).toBe(exchanges);
	});

	test("colEnd <= colStart → returns all exchanges", () => {
		const exchanges = [makeExchange({ sentAtMs: 0 })];
		expect(getWindowExchanges(exchanges, 100, 50, 50, 100)).toBe(exchanges);
	});

	test("window covering full range → all exchanges returned", () => {
		const exchanges = [
			makeExchange({ seq: 1, sentAtMs: 0 }),
			makeExchange({ seq: 2, sentAtMs: 500 }),
			makeExchange({ seq: 3, sentAtMs: 1000 }),
		];
		const result = getWindowExchanges(exchanges, 100, 0, 100, 100);
		expect(result).toHaveLength(3);
	});

	test("narrow window filters to matching exchanges", () => {
		const early = makeExchange({ seq: 1, sentAtMs: 0 });
		const late = makeExchange({ seq: 2, sentAtMs: 1000 });
		// timeRange = 1000ms mapped to 100 cols; col 50 ≈ ms 500
		// window colStart=0, colEnd=10 → only early exchange fits
		const result = getWindowExchanges([early, late], 100, 0, 10, 100);
		expect(result).toContain(early);
		expect(result).not.toContain(late);
	});

	test("a selected window covering a genuine gap returns no exchanges, not the full trace", () => {
		const exchanges = [
			makeExchange({ seq: 1, sentAtMs: 0 }),
			makeExchange({ seq: 2, sentAtMs: 1000 }),
		];
		// timeRange=1000ms over 100 cols; colStart=20, colEnd=80 → tStart=200, tEnd=800
		// sentAtMs=0 < 200 and sentAtMs=1000 > 800, so neither exchange matches
		const result = getWindowExchanges(exchanges, 100, 20, 80, 100);
		expect(result).toEqual([]);
	});
});

	// Hover and drag were rescanning the full exchange list on every
	// pointer-move event. getTimeRange/getColumnBuckets cache their derived
	// structures per exchanges-array identity so repeated calls during one
	// interaction (same array reference) reuse the cached result instead of
	// rescanning. These tests double as a perf regression guard: they fail if
	// a future edit removes the memoization.
	describe("getTimeRange", () => {
		test("computes min, max, and the span between them", () => {
			const exchanges = [
				makeExchange({ sentAtMs: 100 }),
				makeExchange({ sentAtMs: 400 }),
			];
			expect(getTimeRange(exchanges)).toEqual({ minT: 100, maxT: 400, timeRange: 300 });
		});

		test("a single distinct timestamp falls back to timeRange 1 to avoid divide-by-zero", () => {
			const exchanges = [makeExchange({ sentAtMs: 50 }), makeExchange({ sentAtMs: 50 })];
			expect(getTimeRange(exchanges).timeRange).toBe(1);
		});

		test("repeated calls with the same array reference return the cached object, not a rescan", () => {
			const exchanges = [makeExchange({ sentAtMs: 0 }), makeExchange({ sentAtMs: 500 })];
			const first = getTimeRange(exchanges);
			const second = getTimeRange(exchanges);
			expect(second).toBe(first);
		});

		test("a different array reference is computed independently of a cached one", () => {
			const a = [makeExchange({ sentAtMs: 0 })];
			const b = [makeExchange({ sentAtMs: 900 })];
			expect(getTimeRange(a)).not.toBe(getTimeRange(b));
			expect(getTimeRange(b).minT).toBe(900);
		});
	});

	describe("getColumnBuckets", () => {
		test("assigns each exchange to the column matching its time offset", () => {
			const early = makeExchange({ seq: 1, sentAtMs: 0 });
			const late = makeExchange({ seq: 2, sentAtMs: 1000 });
			const buckets = getColumnBuckets([early, late], 10);
			expect(buckets[0]).toContain(early);
			expect(buckets[9]).toContain(late);
		});

		test("repeated calls with the same array reference and column count return the cached buckets, not a rescan", () => {
			const exchanges = [makeExchange({ sentAtMs: 0 }), makeExchange({ sentAtMs: 500 })];
			const first = getColumnBuckets(exchanges, 50);
			const second = getColumnBuckets(exchanges, 50);
			expect(second).toBe(first);
		});

		test("a column-count change (e.g. canvas resize) invalidates the cached buckets", () => {
			const exchanges = [makeExchange({ sentAtMs: 0 }), makeExchange({ sentAtMs: 500 })];
			const wide = getColumnBuckets(exchanges, 100);
			const narrow = getColumnBuckets(exchanges, 10);
			expect(narrow).not.toBe(wide);
			expect(narrow).toHaveLength(10);
		});
	});
