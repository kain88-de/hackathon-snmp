import { describe, expect, test } from "bun:test";
import { asOid } from "../../src/lib/model.ts";
import type { DomainExchange } from "../../src/lib/model.ts";
import {
	autoExpand,
	buildTrie,
	collapseAll,
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

describe("buildTrie", () => {
	test("empty exchanges → root node with no children and no leaves", () => {
		const root = buildTrie([]);
		expect(root.children.size).toBe(0);
		expect(root.leaves).toHaveLength(0);
	});

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

	test("exchange with multiple responseOids → shared: true on both placements", () => {
		const ex = makeExchange({
			responseOids: [
				asOid("1.3.6.1.2.1.1.1.0"),
				asOid("1.3.6.1.2.1.1.2.0"),
			],
		});
		const root = buildTrie([ex]);

		// Navigate to the two known leaf nodes and check directly
		function nav(node: ReturnType<typeof buildTrie>, ...arcs: string[]): ReturnType<typeof buildTrie> {
			let cur = node;
			for (const arc of arcs) {
				cur = cur.children.get(arc)!;
			}
			return cur;
		}

		const leaf1 = nav(root, "1", "3", "6", "1", "2", "1", "1", "1", "0").leaves[0]!;
		const leaf2 = nav(root, "1", "3", "6", "1", "2", "1", "1", "2", "0").leaves[0]!;
		expect(leaf1.shared).toBe(true);
		expect(leaf2.shared).toBe(true);
	});
});

describe("rollup", () => {
	test("stats.count = total leaves in subtree", () => {
		const ex1 = makeExchange({ seq: 1, responseOids: [asOid("1.3")] });
		const ex2 = makeExchange({ seq: 2, responseOids: [asOid("1.3.6")] });
		const ex3 = makeExchange({ seq: 3, responseOids: [asOid("1.3.6")] });
		const root = buildTrie([ex1, ex2, ex3]);
		rollup(root, SLOW_MS);

		const node1 = root.children.get("1")!;
		const node3 = node1.children.get("3")!;
		const node6 = node3.children.get("6")!;
		expect(node1.stats.count).toBe(3);
		expect(node3.stats.count).toBe(3); // 1 own + 2 in child "6"
		expect(node6.stats.count).toBe(2);
	});

	test("slow flag set on node when any leaf has rtt > slowMs", () => {
		const fast = makeExchange({ seq: 1, rtt: 500, responseOids: [asOid("1.3")] });
		const slow = makeExchange({ seq: 2, rtt: 2000, responseOids: [asOid("1.4")] });
		const root = buildTrie([fast, slow]);
		rollup(root, SLOW_MS);

		const node1 = root.children.get("1")!;
		expect(node1.flags.slow).toBe(true);
		expect(node1.children.get("3")!.flags.slow).toBe(false);
		expect(node1.children.get("4")!.flags.slow).toBe(true);
	});

	test("slow flag on a deep leaf surfaces on its ancestor after rollup", () => {
		const ex = makeExchange({ seq: 1, rtt: 2500, responseOids: [asOid("1.3.6")] });
		const root = buildTrie([ex]);
		rollup(root, SLOW_MS);

		const node3 = root.children.get("1")!.children.get("3")!;
		const node6 = node3.children.get("6")!;
		expect(node6.flags.slow).toBe(true);
		expect(node3.flags.slow).toBe(true);
	});

	test("violation flag set on node when any leaf has violations", () => {
		const ex = makeExchange({ responseOids: [asOid("1.3")], violations: ["snmp-v1-only"] });
		const root = buildTrie([ex]);
		rollup(root, SLOW_MS);
		expect(root.children.get("1")!.flags.violation).toBe(true);
	});

	test("retry flag set on node when any leaf has attemptCount > 1", () => {
		const ex = makeExchange({ responseOids: [asOid("1.3")], attemptCount: 2 });
		const root = buildTrie([ex]);
		rollup(root, SLOW_MS);
		expect(root.children.get("1")!.flags.retry).toBe(true);
	});

	test("violation flag on a deep leaf surfaces on its ancestor after rollup", () => {
		const ex = makeExchange({ responseOids: [asOid("1.3.6")], violations: ["snmp-v1-only"] });
		const root = buildTrie([ex]);
		rollup(root, SLOW_MS);
		expect(root.children.get("1")!.flags.violation).toBe(true);
	});

	test("retry flag on a deep leaf surfaces on its ancestor after rollup", () => {
		const ex = makeExchange({ responseOids: [asOid("1.3.6")], attemptCount: 3 });
		const root = buildTrie([ex]);
		rollup(root, SLOW_MS);
		expect(root.children.get("1")!.flags.retry).toBe(true);
	});

	test("violationCount aggregated correctly across siblings", () => {
		const v1 = makeExchange({ seq: 1, responseOids: [asOid("1.3")], violations: ["v"] });
		const v2 = makeExchange({ seq: 2, responseOids: [asOid("1.4")], violations: ["v"] });
		const ok = makeExchange({ seq: 3, responseOids: [asOid("1.5")] });
		const root = buildTrie([v1, v2, ok]);
		rollup(root, SLOW_MS);
		expect(root.children.get("1")!.stats.violationCount).toBe(2);
	});
});

describe("flatten", () => {
	test("skips the synthetic root node", () => {
		const ex = makeExchange({ responseOids: [asOid("1.3")] });
		const root = buildTrie([ex]);
		autoExpand(root);
		const rows = flatten(root);

		for (const row of rows) {
			if (row.kind === "node") {
				expect(row.node.arc).not.toBe("");
			}
		}
		expect(rows[0]!.kind).toBe("node");
		if (rows[0]!.kind === "node") {
			expect(rows[0]!.depth).toBe(0);
			expect(rows[0]!.node.arc).toBe("1");
		}
	});

	test("collapsed nodes hide their children and leaves", () => {
		const ex1 = makeExchange({ seq: 1, responseOids: [asOid("1.3.6")] });
		const ex2 = makeExchange({ seq: 2, responseOids: [asOid("1.4.5")] });
		const root = buildTrie([ex1, ex2]);

		root.children.get("1")!.expanded = true;
		// node3 and node4 remain collapsed (default)

		const arcs = flatten(root)
			.filter((r) => r.kind === "node")
			.map((r) => (r.kind === "node" ? r.node.arc : ""));

		expect(arcs).toContain("1");
		expect(arcs).toContain("3");
		expect(arcs).toContain("4");
		expect(arcs).not.toContain("6");
		expect(arcs).not.toContain("5");
	});

	test("leaf row oid is the response OID, not the request OID", () => {
		const requestOid = asOid("1.2.3.4.5");
		const responseOid = asOid("1.3.6.1.2.1.1.1.0");
		const ex = makeExchange({ requestOid, responseOids: [responseOid] });
		const root = buildTrie([ex]);
		autoExpand(root);
		const rows = flatten(root);

		const leafRows = rows.filter((r) => r.kind === "leaf");
		expect(leafRows).toHaveLength(1);
		if (leafRows[0]!.kind === "leaf") {
			expect(leafRows[0]!.oid).toBe(responseOid);
			expect(leafRows[0]!.oid).not.toBe(requestOid);
		}
	});

	test("exchange with no responseOids appears as depth-0 leaf row", () => {
		const ex = makeExchange({ requestOid: asOid("1.3.6.1.2.1.1.1.0"), responseOids: [] });
		const root = buildTrie([ex]);
		autoExpand(root);
		const rows = flatten(root);

		const leafRows = rows.filter((r) => r.kind === "leaf");
		expect(leafRows).toHaveLength(1);
		expect(leafRows[0]!.depth).toBe(0);
		if (leafRows[0]!.kind === "leaf") {
			expect(leafRows[0]!.oid).toBe(asOid("1.3.6.1.2.1.1.1.0"));
		}
	});
});

describe("collapseAll", () => {
	test("sets expanded = false on root and all descendants", () => {
		const ex1 = makeExchange({ seq: 1, responseOids: [asOid("1.3.6")] });
		const ex2 = makeExchange({ seq: 2, responseOids: [asOid("1.4.5")] });
		const root = buildTrie([ex1, ex2]);
		autoExpand(root);

		expect(root.children.get("1")!.expanded).toBe(true);

		collapseAll(root);

		expect(root.expanded).toBe(false);
		const node1 = root.children.get("1")!;
		expect(node1.expanded).toBe(false);
		for (const child of node1.children.values()) {
			expect(child.expanded).toBe(false);
		}
	});

	test("flatten after collapseAll returns only top-level nodes", () => {
		const ex = makeExchange({ responseOids: [asOid("1.3.6")] });
		const root = buildTrie([ex]);
		autoExpand(root);
		collapseAll(root);

		const arcs = flatten(root)
			.filter((r) => r.kind === "node")
			.map((r) => (r.kind === "node" ? r.node.arc : ""));
		expect(arcs).toContain("1");
		expect(arcs).not.toContain("3");
		expect(arcs).not.toContain("6");
	});
});
