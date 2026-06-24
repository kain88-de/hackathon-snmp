import { describe, expect, test } from "bun:test";
import { asOid } from "../../src/lib/model.ts";
import type { DomainExchange, FacetState, Incident } from "../../src/lib/model.ts";
import { clusterMatchesFacets, matchesFacets } from "../../src/lib/filters.ts";

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

function makeIncident(overrides: Partial<Incident> = {}): Incident {
	return {
		startIdx: 0,
		endIdx: 0,
		startSeq: 1,
		endSeq: 1,
		members: [0],
		peakRtt: 200,
		retryCount: 0,
		timeoutCount: 0,
		violationTypes: new Set(),
		region: "test",
		score: 1,
		...overrides,
	};
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

describe("clusterMatchesFacets", () => {
	test("all-any facets always passes", () => {
		expect(clusterMatchesFacets(makeIncident(), defaultFacets)).toBe(true);
	});

	test("perf:timeout passes incident with timeouts", () => {
		const inc = makeIncident({ timeoutCount: 2 });
		expect(clusterMatchesFacets(inc, facets({ perf: "timeout" }))).toBe(true);
	});

	test("perf:timeout rejects incident without timeouts", () => {
		expect(
			clusterMatchesFacets(makeIncident(), facets({ perf: "timeout" })),
		).toBe(false);
	});

	test("perf:slow passes incident with high peakRtt", () => {
		const inc = makeIncident({ peakRtt: 2000 });
		expect(clusterMatchesFacets(inc, facets({ perf: "slow" }))).toBe(true);
	});

	test("perf:slow rejects incident with low peakRtt", () => {
		const inc = makeIncident({ peakRtt: 200 });
		expect(clusterMatchesFacets(inc, facets({ perf: "slow" }))).toBe(false);
	});

	test("perf:fast passes incident with low peakRtt and no timeouts", () => {
		const inc = makeIncident({ peakRtt: 200, timeoutCount: 0 });
		expect(clusterMatchesFacets(inc, facets({ perf: "fast" }))).toBe(true);
	});

	test("perf:fast rejects incident with timeouts", () => {
		const inc = makeIncident({ peakRtt: 200, timeoutCount: 1 });
		expect(clusterMatchesFacets(inc, facets({ perf: "fast" }))).toBe(false);
	});

	test("corr:violations passes incident with violation types", () => {
		const inc = makeIncident({ violationTypes: new Set(["wrong-type"]) });
		expect(clusterMatchesFacets(inc, facets({ corr: "violations" }))).toBe(
			true,
		);
	});

	test("corr:violations rejects incident without violations", () => {
		expect(
			clusterMatchesFacets(makeIncident(), facets({ corr: "violations" })),
		).toBe(false);
	});

	test("retryOnly:true passes incident with retries", () => {
		const inc = makeIncident({ retryCount: 3 });
		expect(clusterMatchesFacets(inc, facets({ retryOnly: true }))).toBe(true);
	});

	test("retryOnly:true rejects incident without retries", () => {
		expect(
			clusterMatchesFacets(makeIncident(), facets({ retryOnly: true })),
		).toBe(false);
	});
});
