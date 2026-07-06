import { describe, expect, test } from "vitest";
import { asOid } from "../../src/lib/model.ts";
import type { DomainExchange } from "../../src/lib/model.ts";
import { minMaxValues, rttCssClass, rttCssClassFromRtt } from "../../src/lib/utils.ts";

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

describe("minMaxValues", () => {
	test("single element returns same value for min and max", () => {
		expect(minMaxValues([42])).toEqual([42, 42]);
	});

	test("ascending sequence", () => {
		expect(minMaxValues([1, 2, 3, 4, 5])).toEqual([1, 5]);
	});

	test("descending sequence", () => {
		expect(minMaxValues([5, 4, 3, 2, 1])).toEqual([1, 5]);
	});

	test("all equal values", () => {
		expect(minMaxValues([7, 7, 7])).toEqual([7, 7]);
	});

	test("negative values", () => {
		expect(minMaxValues([-3, -1, -5, 0])).toEqual([-5, 0]);
	});
});

describe("rttCssClass", () => {
	test("timeout → dim-timeout regardless of rtt", () => {
		const ex = makeExchange({ isTimeout: true, rtt: 0 });
		expect(rttCssClass(ex, 1000)).toBe("dim-timeout");
	});

	test("rtt above slowMs → dim-slow", () => {
		const ex = makeExchange({ rtt: 1500 });
		expect(rttCssClass(ex, 1000)).toBe("dim-slow");
	});

	test("rtt exactly at slowMs → dim-fast (not strictly greater)", () => {
		const ex = makeExchange({ rtt: 1000 });
		expect(rttCssClass(ex, 1000)).toBe("dim-fast");
	});

	test("rtt below slowMs → dim-fast", () => {
		const ex = makeExchange({ rtt: 200 });
		expect(rttCssClass(ex, 1000)).toBe("dim-fast");
	});

	test("timeout takes priority over rtt > slowMs", () => {
		const ex = makeExchange({ isTimeout: true, rtt: 5000 });
		expect(rttCssClass(ex, 1000)).toBe("dim-timeout");
	});
});

describe("rttCssClassFromRtt", () => {
	test("rtt above slowMs → dim-slow", () => {
		expect(rttCssClassFromRtt(1500, 1000)).toBe("dim-slow");
	});

	test("rtt at slowMs → dim-fast", () => {
		expect(rttCssClassFromRtt(1000, 1000)).toBe("dim-fast");
	});

	test("rtt below slowMs → dim-fast", () => {
		expect(rttCssClassFromRtt(200, 1000)).toBe("dim-fast");
	});
});
