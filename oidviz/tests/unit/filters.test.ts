import { describe, expect, test } from "bun:test";
import { asOid } from "../../src/lib/model.ts";
import type { DomainExchange, FacetState } from "../../src/lib/model.ts";
import { matchesFacets } from "../../src/lib/filters.ts";

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

const defaultFacets: FacetState = {
	perf: "any",
	corr: "any",
	retryOnly: false,
	slowMs: 1000,
};

function facets(overrides: Partial<FacetState>): FacetState {
	return { ...defaultFacets, ...overrides };
}

describe("matchesFacets", () => {
	test("all-any facets always passes", () => {
		expect(matchesFacets(makeExchange(), defaultFacets)).toBe(true);
	});

	test("perf:fast rejects slow exchange", () => {
		const ex = makeExchange({ rtt: 2000 });
		expect(matchesFacets(ex, facets({ perf: "fast" }))).toBe(false);
	});

	test("perf:fast passes fast exchange", () => {
		const ex = makeExchange({ rtt: 500 });
		expect(matchesFacets(ex, facets({ perf: "fast" }))).toBe(true);
	});

	test("perf:slow passes slow exchange", () => {
		const ex = makeExchange({ rtt: 2000 });
		expect(matchesFacets(ex, facets({ perf: "slow" }))).toBe(true);
	});

	test("perf:slow rejects fast exchange", () => {
		const ex = makeExchange({ rtt: 500 });
		expect(matchesFacets(ex, facets({ perf: "slow" }))).toBe(false);
	});

	test("perf:timeout passes timeout exchange", () => {
		const ex = makeExchange({ isTimeout: true });
		expect(matchesFacets(ex, facets({ perf: "timeout" }))).toBe(true);
	});

	test("perf:timeout rejects non-timeout exchange", () => {
		expect(matchesFacets(makeExchange(), facets({ perf: "timeout" }))).toBe(
			false,
		);
	});

	test("perf:fast rejects timeout exchange", () => {
		const ex = makeExchange({ isTimeout: true, rtt: 100 });
		expect(matchesFacets(ex, facets({ perf: "fast" }))).toBe(false);
	});

	test("perf:slow rejects timeout exchange", () => {
		const ex = makeExchange({ isTimeout: true, rtt: 5000 });
		expect(matchesFacets(ex, facets({ perf: "slow" }))).toBe(false);
	});

	test("corr:violations rejects exchange with no violations", () => {
		expect(
			matchesFacets(makeExchange(), facets({ corr: "violations" })),
		).toBe(false);
	});

	test("corr:violations passes exchange with violations", () => {
		const ex = makeExchange({ violations: ["wrong-type"] });
		expect(matchesFacets(ex, facets({ corr: "violations" }))).toBe(true);
	});

	test("retryOnly:false always passes", () => {
		const ex = makeExchange({ attemptCount: 1 });
		expect(matchesFacets(ex, facets({ retryOnly: false }))).toBe(true);
	});

	test("retryOnly:true rejects attemptCount:1", () => {
		const ex = makeExchange({ attemptCount: 1 });
		expect(matchesFacets(ex, facets({ retryOnly: true }))).toBe(false);
	});

	test("retryOnly:true passes attemptCount:2", () => {
		const ex = makeExchange({ attemptCount: 2 });
		expect(matchesFacets(ex, facets({ retryOnly: true }))).toBe(true);
	});

	test("AND logic: all axes must pass", () => {
		// fast exchange with violations but only 1 attempt
		const ex = makeExchange({
			rtt: 100,
			violations: ["wrong-type"],
			attemptCount: 1,
		});
		// retryOnly:true fails even though perf and corr pass
		expect(
			matchesFacets(ex, facets({ perf: "fast", corr: "violations", retryOnly: true })),
		).toBe(false);
	});
});
