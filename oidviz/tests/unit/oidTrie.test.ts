import { describe, expect, test } from "bun:test";
import { asOid } from "../../src/lib/model.ts";
import type { DomainExchange } from "../../src/lib/model.ts";
import {
	autoExpand,
	buildTrie,
	flatten,
	rollup,
} from "../../src/lib/oidTrie.ts";

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

const SLOW_MS = 1000;

// Test 1: buildTrie with empty exchanges → root with no children
describe("buildTrie", () => {
	test("empty exchanges → root node with no children and no leaves", () => {
		const root = buildTrie([]);
		expect(root.children.size).toBe(0);
		expect(root.leaves).toHaveLength(0);
	});

	// Test 2: buildTrie with one exchange with one responseOid → leaf under correct path
	test("one exchange with one responseOid → leaf under correct path", () => {
		const ex = makeExchange({
			responseOids: [asOid("1.3.6.1.2.1.1.1.0")],
		});
		const root = buildTrie([ex]);

		// Path: 1 → 3 → 6 → 1 → 2 → 1 → 1 → 1 → 0
		const node1 = root.children.get("1");
		expect(node1).toBeDefined();
		expect(node1!.fullOid).toBe(asOid("1"));

		// Navigate to leaf node at "0"
		let cur = node1!;
		for (const arc of ["3", "6", "1", "2", "1", "1", "1", "0"]) {
			const child = cur.children.get(arc);
			expect(child).toBeDefined();
			cur = child!;
		}
		expect(cur.leaves).toHaveLength(1);
		expect(cur.leaves[0]!.exchange).toBe(ex);
		expect(cur.leaves[0]!.oid).toBe(asOid("1.3.6.1.2.1.1.1.0"));
	});

	// Test 3: buildTrie with exchange with no responseOids → leaf under root
	test("exchange with no responseOids → leaf under root", () => {
		const ex = makeExchange({
			requestOid: asOid("1.3.6.1.2.1.1.1.0"),
			responseOids: [],
		});
		const root = buildTrie([ex]);
		expect(root.leaves).toHaveLength(1);
		expect(root.leaves[0]!.exchange).toBe(ex);
		expect(root.leaves[0]!.oid).toBe(asOid("1.3.6.1.2.1.1.1.0"));
	});

	// Test 10: shared: true when exchange appears under multiple responseOids
	test("shared: true when exchange appears under multiple responseOids", () => {
		const ex = makeExchange({
			responseOids: [
				asOid("1.3.6.1.2.1.1.1.0"),
				asOid("1.3.6.1.2.1.1.2.0"),
			],
		});
		const root = buildTrie([ex]);

		// Collect all leaves
		function collectLeaves(node: ReturnType<typeof buildTrie>): import("../../src/lib/model.ts").TrieLeaf[] {
			const result: import("../../src/lib/model.ts").TrieLeaf[] = [...node.leaves];
			for (const child of node.children.values()) {
				result.push(...collectLeaves(child));
			}
			return result;
		}

		const leaves = collectLeaves(root);
		// Both placements should have shared: true
		for (const leaf of leaves) {
			expect(leaf.shared).toBe(true);
		}
		expect(leaves).toHaveLength(2);
	});
});

// Test 4: rollup computes stats.count correctly
describe("rollup", () => {
	test("stats.count = total leaves in subtree", () => {
		const ex1 = makeExchange({ seq: 1, responseOids: [asOid("1.3")] });
		const ex2 = makeExchange({ seq: 2, responseOids: [asOid("1.3.6")] });
		const ex3 = makeExchange({ seq: 3, responseOids: [asOid("1.3.6")] });
		const root = buildTrie([ex1, ex2, ex3]);
		rollup(root, SLOW_MS);

		const node1 = root.children.get("1")!;
		// node "1" has child "3" which has 1 leaf (ex1)
		// node "3" has child "6" which has 2 leaves (ex2, ex3)
		// total under "1" = 3
		expect(node1.stats.count).toBe(3);

		const node3 = node1.children.get("3")!;
		expect(node3.stats.count).toBe(3); // 1 own + 2 in child "6"

		const node6 = node3.children.get("6")!;
		expect(node6.stats.count).toBe(2);
	});

	// Test 5: rollup computes flags.slow correctly
	test("flags.slow = true when any leaf has rtt > slowMs", () => {
		const fast = makeExchange({
			seq: 1,
			rtt: 500,
			responseOids: [asOid("1.3")],
		});
		const slow = makeExchange({
			seq: 2,
			rtt: 2000,
			responseOids: [asOid("1.4")],
		});

		const root = buildTrie([fast, slow]);
		rollup(root, SLOW_MS);

		const node1 = root.children.get("1")!;
		// fast under "3", slow under "4" — node "1" should be flagged slow
		expect(node1.flags.slow).toBe(true);

		const node3 = node1.children.get("3")!;
		expect(node3.flags.slow).toBe(false);

		const node4 = node1.children.get("4")!;
		expect(node4.flags.slow).toBe(true);
	});

	// Test 6: rollup visits children before own leaves (post-order)
	test("post-order: children stats are set before parent reads them", () => {
		const ex = makeExchange({
			seq: 1,
			rtt: 2500,
			responseOids: [asOid("1.3.6")],
		});
		const root = buildTrie([ex]);
		rollup(root, SLOW_MS);

		// The deepest node "6" should have slow flag set from its own leaf
		const node6 = root.children.get("1")!.children.get("3")!.children.get("6")!;
		expect(node6.flags.slow).toBe(true);

		// The parent "3" should have inherited slow from child "6"
		const node3 = root.children.get("1")!.children.get("3")!;
		expect(node3.flags.slow).toBe(true);
	});
});

// Test 7: flatten skips synthetic root
describe("flatten", () => {
	test("skips the synthetic root node", () => {
		const ex = makeExchange({
			responseOids: [asOid("1.3")],
		});
		const root = buildTrie([ex]);
		autoExpand(root);
		const rows = flatten(root);

		// None of the rows should have the synthetic root (arc === "" and fullOid === "")
		for (const row of rows) {
			if (row.kind === "node") {
				expect(row.node.arc).not.toBe("");
			}
		}
		// First row should be arc "1" at depth 0
		expect(rows[0]).toBeDefined();
		expect(rows[0]!.kind).toBe("node");
		if (rows[0]!.kind === "node") {
			expect(rows[0]!.depth).toBe(0);
			expect(rows[0]!.node.arc).toBe("1");
		}
	});

	// Test 8: flatten only emits children/leaves of expanded nodes
	test("collapsed nodes hide their children/leaves", () => {
		const ex1 = makeExchange({ seq: 1, responseOids: [asOid("1.3.6")] });
		const ex2 = makeExchange({ seq: 2, responseOids: [asOid("1.4.5")] });
		const root = buildTrie([ex1, ex2]);

		// Expand root children but not their children
		const node1 = root.children.get("1")!;
		node1.expanded = true;
		// node3 and node4 are collapsed (default)

		const rows = flatten(root);

		// Should see node "1" (depth 0) and its direct children "3" and "4" (depth 1)
		// but NOT "6" or "5" (children of collapsed nodes)
		const arcs = rows
			.filter((r) => r.kind === "node")
			.map((r) => (r.kind === "node" ? r.node.arc : ""));

		expect(arcs).toContain("1");
		expect(arcs).toContain("3");
		expect(arcs).toContain("4");
		expect(arcs).not.toContain("6");
		expect(arcs).not.toContain("5");
	});

	// Test 9: leaf rows display row.oid (response OID), not exchange.requestOid
	test("leaf rows display row.oid (response OID), not requestOid", () => {
		const requestOid = asOid("1.2.3.4.5");
		const responseOid = asOid("1.3.6.1.2.1.1.1.0");
		const ex = makeExchange({
			requestOid,
			responseOids: [responseOid],
		});
		const root = buildTrie([ex]);
		autoExpand(root);
		const rows = flatten(root);

		const leafRows = rows.filter((r) => r.kind === "leaf");
		expect(leafRows).toHaveLength(1);
		const leaf = leafRows[0]!;
		if (leaf.kind === "leaf") {
			expect(leaf.oid).toBe(responseOid);
			expect(leaf.oid).not.toBe(requestOid);
		}
	});
});
