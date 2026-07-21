import { describe, expect, test } from "vitest";
import { mount } from "@vue/test-utils";
import { asOid } from "../../src/lib/model.ts";
import type { FacetState, FlatRow } from "../../src/lib/model.ts";
import OidTree from "../../src/components/OidTree.vue";
import { makeExchange, makeFacetState, makeTrieNode } from "./helpers.ts";

interface OidTreeProps {
	flatRows: FlatRow[];
	facetState: FacetState;
	matchingCount: number;
}

function mountOidTree(overrides: Partial<OidTreeProps> = {}) {
	const props: OidTreeProps = {
		flatRows: [],
		facetState: makeFacetState(),
		matchingCount: 0,
		...overrides,
	};
	return mount(OidTree, { props });
}

describe("OidTree", () => {
	describe("toolbar", () => {
		// matchingCount: 7 while flatRows only has 2 entries — proves the
		// toolbar count reflects the matchingCount prop rather than
		// flatRows.length (which would read "2" here).
		test("shows the matching count", () => {
			const wrapper = mountOidTree({
				flatRows: [
					{ kind: "node", depth: 0, node: makeTrieNode({ arc: "1", fullOid: asOid("1") }) },
					{ kind: "node", depth: 0, node: makeTrieNode({ arc: "2", fullOid: asOid("2") }) },
				],
				matchingCount: 7,
			});

			expect(wrapper.find(".oid-tree-count").text()).toBe("7 exchanges");
		});

		// any non-empty flatRows — clicking "Collapse all" must emit
		// collapse-all regardless of row contents, proving the toolbar
		// button is wired independently of row/node state.
		test("clicking Collapse all emits collapse-all", async () => {
			const wrapper = mountOidTree({
				flatRows: [{ kind: "node", depth: 0, node: makeTrieNode() }],
			});

			await wrapper.find(".oid-tree-collapse-btn").trigger("click");

			expect(wrapper.emitted("collapse-all")).toHaveLength(1);
		});
	});

	describe("node rows", () => {
		// one node with name "sysDescr", stats.count: 5, stats.maxRtt: 42.5
		// (> 0); a second node with stats.maxRtt: 0 — proves arc/name/count
		// render from the node's own fields, that maxRtt is formatted with
		// toFixed(1) (42.5 would read "43ms" if rounded, or "42ms" if
		// truncated — "42.5ms" proves neither), and that the maxRtt element
		// is conditionally rendered rather than always present.
		test("renders arc, name, count, and maxRtt; omits maxRtt when zero", () => {
			const nodeWithRtt = makeTrieNode({
				arc: "1",
				fullOid: asOid("1"),
				name: "sysDescr",
				stats: { count: 5, maxRtt: 42.5, violationCount: 0 },
			});
			const nodeWithoutRtt = makeTrieNode({
				arc: "2",
				fullOid: asOid("2"),
				stats: { count: 3, maxRtt: 0, violationCount: 0 },
			});
			const wrapper = mountOidTree({
				flatRows: [
					{ kind: "node", depth: 0, node: nodeWithRtt },
					{ kind: "node", depth: 0, node: nodeWithoutRtt },
				],
			});

			const rows = wrapper.findAll(".trie-node");
			expect(rows).toHaveLength(2);

			expect(rows[0]!.find(".trie-arc").text()).toBe("1");
			expect(rows[0]!.find(".trie-name").text()).toBe("sysDescr");
			expect(rows[0]!.find(".trie-count").text()).toBe("5");
			const maxRtt = rows[0]!.find(".trie-maxrtt");
			expect(maxRtt.exists()).toBe(true);
			expect(maxRtt.text()).toBe("42.5ms");
			expect(maxRtt.classes()).toContain("dim-fast");

			expect(rows[1]!.find(".trie-maxrtt").exists()).toBe(false);
		});

		// one node expanded: true, one expanded: false — the toggle glyph
		// and aria-expanded attribute must each reflect that node's own
		// expanded field, not a shared/default value.
		test("toggle glyph and aria-expanded reflect each node's expanded state", () => {
			const expandedNode = makeTrieNode({ arc: "1", fullOid: asOid("1"), expanded: true });
			const collapsedNode = makeTrieNode({ arc: "2", fullOid: asOid("2"), expanded: false });
			const wrapper = mountOidTree({
				flatRows: [
					{ kind: "node", depth: 0, node: expandedNode },
					{ kind: "node", depth: 0, node: collapsedNode },
				],
			});

			const rows = wrapper.findAll(".trie-node");
			expect(rows[0]!.find(".trie-toggle").text()).toBe("▾");
			expect(rows[0]!.attributes("aria-expanded")).toBe("true");
			expect(rows[1]!.find(".trie-toggle").text()).toBe("▸");
			expect(rows[1]!.attributes("aria-expanded")).toBe("false");
		});

		// node starting expanded: false — clicking its row must emit
		// reflatten and mutate the SAME TrieNode object's .expanded field to
		// true. OidTree.vue mutates the prop's nested TrieNode directly
		// (`// TrieNode.expanded is intentionally mutable`) rather than
		// emitting a new value, so the test holds onto the exact object
		// reference passed into flatRows and reads its field afterward.
		// Investigated empirically (see task report): @vue/test-utils'
		// mount() makes object/array props deeply reactive, so the `node`
		// the click handler receives (via the v-for row) is a reactive
		// proxy sharing the same underlying storage as our raw `node`
		// reference — the mutation is visible on our reference AND the
		// rendered aria-expanded/toggle glyph update on their own, with no
		// forced re-render needed. Both are asserted; .expanded is the
		// authoritative contract per the source comment.
		test("clicking a node row emits reflatten and flips the node's expanded field", async () => {
			const node = makeTrieNode({ expanded: false });
			const wrapper = mountOidTree({
				flatRows: [{ kind: "node", depth: 0, node }],
			});

			await wrapper.find(".trie-node").trigger("click");

			expect(wrapper.emitted("reflatten")).toHaveLength(1);
			expect(node.expanded).toBe(true);
			const row = wrapper.find(".trie-node");
			expect(row.attributes("aria-expanded")).toBe("true");
			expect(row.find(".trie-toggle").text()).toBe("▾");
		});

		// two separate nodes, both starting expanded: false — Enter on one
		// row and Space on the other must each behave like a click: emit
		// reflatten and flip that node's own .expanded field (and, per the
		// reactivity behavior described above, its rendered aria-expanded
		// too), proving both keyboard bindings delegate to the same handler
		// as the mouse click.
		test("Enter and Space on a node row toggle expansion like a click", async () => {
			const enterNode = makeTrieNode({ arc: "1", fullOid: asOid("1"), expanded: false });
			const spaceNode = makeTrieNode({ arc: "2", fullOid: asOid("2"), expanded: false });
			const wrapper = mountOidTree({
				flatRows: [
					{ kind: "node", depth: 0, node: enterNode },
					{ kind: "node", depth: 0, node: spaceNode },
				],
			});
			const rows = wrapper.findAll(".trie-node");

			await rows[0]!.trigger("keydown.enter");
			await rows[1]!.trigger("keydown.space");

			expect(wrapper.emitted("reflatten")).toHaveLength(2);
			expect(enterNode.expanded).toBe(true);
			expect(spaceNode.expanded).toBe(true);
			const rowsAfter = wrapper.findAll(".trie-node");
			expect(rowsAfter[0]!.attributes("aria-expanded")).toBe("true");
			expect(rowsAfter[1]!.attributes("aria-expanded")).toBe("true");
		});
	});

	describe("node badges", () => {
		// four nodes: one with flags.slow, one with flags.violation, one
		// with flags.retry, and one with no flags set — each badge class
		// must render exactly for the node whose own flag is set, proving
		// the badges read the row's own flags rather than any shared state.
		test("renders a badge only for the flags that are set", () => {
			const slowNode = makeTrieNode({
				arc: "1",
				fullOid: asOid("1"),
				flags: { slow: true, violation: false, retry: false },
			});
			const violationNode = makeTrieNode({
				arc: "2",
				fullOid: asOid("2"),
				flags: { slow: false, violation: true, retry: false },
			});
			const retryNode = makeTrieNode({
				arc: "3",
				fullOid: asOid("3"),
				flags: { slow: false, violation: false, retry: true },
			});
			const noneNode = makeTrieNode({
				arc: "4",
				fullOid: asOid("4"),
				flags: { slow: false, violation: false, retry: false },
			});
			const wrapper = mountOidTree({
				flatRows: [
					{ kind: "node", depth: 0, node: slowNode },
					{ kind: "node", depth: 0, node: violationNode },
					{ kind: "node", depth: 0, node: retryNode },
					{ kind: "node", depth: 0, node: noneNode },
				],
			});

			const rows = wrapper.findAll(".trie-node");
			expect(rows).toHaveLength(4);

			expect(rows[0]!.find(".badge-slow").exists()).toBe(true);
			expect(rows[0]!.find(".badge-violation").exists()).toBe(false);
			expect(rows[0]!.find(".badge-retry").exists()).toBe(false);

			expect(rows[1]!.find(".badge-violation").exists()).toBe(true);
			expect(rows[1]!.find(".badge-slow").exists()).toBe(false);
			expect(rows[1]!.find(".badge-retry").exists()).toBe(false);

			expect(rows[2]!.find(".badge-retry").exists()).toBe(true);
			expect(rows[2]!.find(".badge-slow").exists()).toBe(false);
			expect(rows[2]!.find(".badge-violation").exists()).toBe(false);

			expect(rows[3]!.find(".badge-slow").exists()).toBe(false);
			expect(rows[3]!.find(".badge-violation").exists()).toBe(false);
			expect(rows[3]!.find(".badge-retry").exists()).toBe(false);
		});
	});

	describe("leaf rows", () => {
		// a leaf exchange with requestOid "1.3.6.1.2.1.1.5.0", rtt: 1500 (>
		// the default facetState.slowMs of 1000, so dim-slow), 2 violations,
		// and row.shared: true — every leaf field must render from the
		// exchange/row data. Using 2 violations (not 1) proves the badge
		// sums the violations array length rather than just checking
		// presence, which would coincidentally also read "1 viol".
		test("renders oid, rtt, violation-count badge, and shared badge", () => {
			const exchange = makeExchange({
				requestOid: asOid("1.3.6.1.2.1.1.5.0"),
				rtt: 1500,
				violations: ["oid-not-increasing", "duplicate-response"],
			});
			const wrapper = mountOidTree({
				flatRows: [
					{
						kind: "leaf",
						depth: 0,
						exchange,
						oid: asOid("1.3.6.1.2.1.1.5.0"),
						shared: true,
						name: null,
						description: null,
					},
				],
			});

			const row = wrapper.find(".trie-leaf");
			expect(row.find(".trie-leaf-oid").text()).toBe("1.3.6.1.2.1.1.5.0");
			const rtt = row.find(".trie-leaf-rtt");
			expect(rtt.text()).toBe("1500.0ms");
			expect(rtt.classes()).toContain("dim-slow");
			expect(row.find(".badge-violation").text()).toBe("2 viol");
			expect(row.find(".badge-shared").exists()).toBe(true);
		});
	});
});
