import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { mount } from "@vue/test-utils";
import { nextTick } from "vue";
import { asOid } from "../../src/lib/model.ts";
import type { FlatRow } from "../../src/lib/model.ts";
import OidTree from "../../src/components/OidTree.vue";
import { makeExchange } from "./helpers.ts";

// useVirtualScroll is shared by OidTree.vue and FindingsByCategory.vue; either
// consumer exercises the same composable. OidTree.vue is used here because
// its flatRows prop is trivial to synthesize at the row counts needed to
// prove virtualization actually kicks in (happy-dom's default container
// fallback is 600px / 32px rows ≈ 21 visible rows).
class MockResizeObserver {
	static instances: MockResizeObserver[] = [];
	callback: ResizeObserverCallback;
	observedElements: Element[] = [];
	disconnected = false;

	constructor(callback: ResizeObserverCallback) {
		this.callback = callback;
		MockResizeObserver.instances.push(this);
	}

	observe(el: Element): void {
		this.observedElements.push(el);
	}

	unobserve(): void {}

	disconnect(): void {
		this.disconnected = true;
	}
}

function makeFlatRows(count: number): FlatRow[] {
	return Array.from({ length: count }, (_, i) => ({
		depth: 0,
		exchange: makeExchange({ seq: i }),
		kind: "leaf",
		oid: asOid(String(i)),
		shared: false,
	}));
}

describe("useVirtualScroll resize handling", () => {
	beforeEach(() => {
		MockResizeObserver.instances = [];
		vi.stubGlobal("ResizeObserver", MockResizeObserver);
	});

	afterEach(() => {
		vi.unstubAllGlobals();
	});

	// happy-dom has no layout engine: clientHeight is 0 on mount, so
	// containerHeight falls back to the 600px default (≈21 rows at 32px each)
	// regardless of this fix — the only way to prove a *later* resize is
	// picked up is to fake clientHeight and fire the observer's callback by
	// hand, since happy-dom's own ResizeObserver never calls back for real.
	test("re-measures and renders more rows when the container grows after mount", async () => {
		const wrapper = mount(OidTree, {
			props: {
				facetState: { corr: "any", perf: "any", retryOnly: false, slowMs: 1000 },
				flatRows: makeFlatRows(50),
				matchingCount: 50,
			},
		});

		const initialRowCount = wrapper.findAll("[data-trie-row]").length;
		expect(initialRowCount).toBeLessThan(50);

		expect(MockResizeObserver.instances).toHaveLength(1);
		const observer = MockResizeObserver.instances[0]!;
		const containerEl = wrapper.find(".oid-tree-list").element;
		expect(observer.observedElements).toContain(containerEl);

		Object.defineProperty(containerEl, "clientHeight", {
			configurable: true,
			value: 50 * 32,
		});
		observer.callback([], observer as unknown as ResizeObserver);
		await nextTick();

		expect(wrapper.findAll("[data-trie-row]")).toHaveLength(50);
	});

	// A single flat row is enough here — this test isn't about virtualization
	// math, only that unmounting cleans up the observer instead of leaking it.
	test("disconnects the ResizeObserver on unmount", () => {
		const wrapper = mount(OidTree, {
			props: {
				facetState: { corr: "any", perf: "any", retryOnly: false, slowMs: 1000 },
				flatRows: makeFlatRows(1),
				matchingCount: 1,
			},
		});

		const observer = MockResizeObserver.instances[0]!;
		wrapper.unmount();

		expect(observer.disconnected).toBe(true);
	});
});
