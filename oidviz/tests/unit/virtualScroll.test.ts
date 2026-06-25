import { describe, expect, test } from "bun:test";
import {
	computeOffsets,
	sumHeights,
	varHeightEndIdx,
	varHeightStartIdx,
} from "../../src/lib/virtualScroll.ts";

const fixedH = (_: unknown): number => 32;

describe("computeOffsets", () => {
	test("empty list → empty offsets", () => {
		expect(computeOffsets([], fixedH)).toEqual([]);
	});

	test("uniform height → cumulative multiples", () => {
		const items = ["a", "b", "c"];
		expect(computeOffsets(items, fixedH)).toEqual([0, 32, 64]);
	});

	test("variable heights → correct cumulative positions", () => {
		const items = [10, 20, 30];
		const getH = (n: number): number => n;
		expect(computeOffsets(items, getH)).toEqual([0, 10, 30]);
	});
});

describe("sumHeights", () => {
	test("empty list → 0", () => {
		expect(sumHeights([], fixedH)).toBe(0);
	});

	test("uniform heights → count × height", () => {
		expect(sumHeights(["a", "b", "c", "d"], fixedH)).toBe(128);
	});

	test("variable heights → sum of all", () => {
		const items = [10, 20, 30];
		expect(sumHeights(items, (n) => n)).toBe(60);
	});
});

describe("varHeightStartIdx", () => {
	// Items: [32, 32, 32] → offsets [0, 32, 64], total 96
	const items = ["a", "b", "c"];
	const offsets = [0, 32, 64];

	test("scrollY 0 → startIdx 0", () => {
		expect(varHeightStartIdx(items, offsets, fixedH, 0)).toBe(0);
	});

	test("scrollY past first item → startIdx 1", () => {
		// item 0 ends at offset 32; scrollY 32 means item 0 is fully above viewport
		expect(varHeightStartIdx(items, offsets, fixedH, 32)).toBe(1);
	});

	test("scrollY midway into first item → startIdx 0", () => {
		expect(varHeightStartIdx(items, offsets, fixedH, 16)).toBe(0);
	});

	test("scrollY past all items → startIdx = length", () => {
		expect(varHeightStartIdx(items, offsets, fixedH, 200)).toBe(3);
	});

	test("empty items → 0", () => {
		expect(varHeightStartIdx([], [], fixedH, 50)).toBe(0);
	});
});

describe("varHeightEndIdx", () => {
	// offsets [0, 32, 64], totalCount 3, each item 32px tall
	const offsets = [0, 32, 64];
	const totalCount = 3;

	test("viewEnd covers all → totalCount", () => {
		expect(varHeightEndIdx(offsets, 0, totalCount, 200)).toBe(3);
	});

	test("viewEnd stops before last item starts → returns that index", () => {
		// offset[2] = 64; viewEnd 64 means stop before index 2
		expect(varHeightEndIdx(offsets, 0, totalCount, 64)).toBe(2);
	});

	test("startIdx skips leading items", () => {
		// starting from index 1, viewEnd 64 → stop at index 2
		expect(varHeightEndIdx(offsets, 1, totalCount, 64)).toBe(2);
	});

	test("viewEnd 0 with startIdx 0 → 0", () => {
		// offset[0] = 0 >= 0 → return 0 immediately
		expect(varHeightEndIdx(offsets, 0, totalCount, 0)).toBe(0);
	});
});
