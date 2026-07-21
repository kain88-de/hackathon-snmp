import type {
	DomainExchange,
	FlatRow,
	OidString,
	TrieLeaf,
	TrieNode,
	TrieNodeFlags,
} from "./model.ts";
import { asOid } from "./model.ts";
import { lookupOidName } from "./oidNames.gen.ts";

const AUTO_EXPAND_MAX_CHILDREN = 10;

function makeNode(arc: string, fullOid: OidString): TrieNode {
	const info = lookupOidName(fullOid);
	return {
		arc,
		children: new Map(),
		description: info?.description ?? null,
		expanded: false,
		flags: { retry: false, slow: false, violation: false },
		fullOid,
		leaves: [],
		name: info?.name ?? null,
		stats: { count: 0, maxRtt: 0, violationCount: 0 },
	};
}

interface InsertArgs {
	exchange: DomainExchange;
	responseOid: OidString;
	root: TrieNode;
	shared: boolean;
}

function insertResponseOid(args: InsertArgs): void {
	const { exchange, responseOid, root, shared } = args;
	const arcs = responseOid.split(".");
	let current = root;

	for (let i = 0; i < arcs.length; i += 1) {
		const arc = arcs[i] ?? "";
		const fullOid = asOid(arcs.slice(0, i + 1).join("."));

		let child = current.children.get(arc);
		if (child === undefined) {
			child = makeNode(arc, fullOid);
			current.children.set(arc, child);
		}
		current = child;
	}

	const info = lookupOidName(responseOid);
	current.leaves.push({
		description: info?.description ?? null,
		exchange,
		name: info?.name ?? null,
		oid: responseOid,
		shared,
	});
}

export function buildTrie(exchanges: readonly DomainExchange[]): TrieNode {
	const root = makeNode("", asOid(""));
	root.expanded = true;

	for (const exchange of exchanges) {
		if (exchange.responseOids.length === 0) {
			const info = lookupOidName(exchange.requestOid);
			root.leaves.push({
				description: info?.description ?? null,
				exchange,
				name: info?.name ?? null,
				oid: exchange.requestOid,
				shared: false,
			});
		} else {
			const shared = exchange.responseOids.length > 1;
			for (const responseOid of exchange.responseOids) {
				insertResponseOid({ exchange, responseOid, root, shared });
			}
		}
	}

	return root;
}

function aggregateChildFlags(
	children: Map<string, TrieNode>,
	flags: TrieNodeFlags,
): { count: number; maxRtt: number; violationCount: number } {
	let count = 0;
	let maxRtt = 0;
	let violationCount = 0;

	for (const child of children.values()) {
		count += child.stats.count;
		if (child.stats.maxRtt > maxRtt) {
			maxRtt = child.stats.maxRtt;
		}
		violationCount += child.stats.violationCount;
		if (child.flags.slow) {
			flags.slow = true;
		}
		if (child.flags.violation) {
			flags.violation = true;
		}
		if (child.flags.retry) {
			flags.retry = true;
		}
	}

	return { count, maxRtt, violationCount };
}

function aggregateLeafFlags(
	leaves: readonly TrieLeaf[],
	slowMs: number,
	flags: TrieNodeFlags,
): { maxRtt: number; violationCount: number } {
	let maxRtt = 0;
	let violationCount = 0;

	for (const leaf of leaves) {
		const ex = leaf.exchange;
		if (ex.rtt > maxRtt) {
			maxRtt = ex.rtt;
		}
		if (ex.rtt > slowMs) {
			flags.slow = true;
		}
		if (ex.violations.length > 0) {
			flags.violation = true;
			violationCount += 1;
		}
		if (ex.attemptCount > 1) {
			flags.retry = true;
		}
	}

	return { maxRtt, violationCount };
}

export function rollup(node: TrieNode, slowMs: number): void {
	// Post-order: children first
	for (const child of node.children.values()) {
		rollup(child, slowMs);
	}

	const flags: TrieNodeFlags = { retry: false, slow: false, violation: false };

	const fromChildren = aggregateChildFlags(node.children, flags);
	const fromLeaves = aggregateLeafFlags(node.leaves, slowMs, flags);

	node.stats = {
		count: fromChildren.count + node.leaves.length,
		maxRtt: Math.max(fromChildren.maxRtt, fromLeaves.maxRtt),
		violationCount: fromChildren.violationCount + fromLeaves.violationCount,
	};
	node.flags = flags;
}

export function flatten(root: TrieNode): FlatRow[] {
	const rows: FlatRow[] = [];

	function visit(node: TrieNode, depth: number): void {
		rows.push({ depth, kind: "node", node });
		if (!node.expanded) {
			return;
		}

		for (const child of node.children.values()) {
			visit(child, depth + 1);
		}

		for (const leaf of node.leaves) {
			rows.push({
				depth: depth + 1,
				description: leaf.description,
				exchange: leaf.exchange,
				kind: "leaf",
				name: leaf.name,
				oid: leaf.oid,
				shared: leaf.shared,
			});
		}
	}

	// Skip the synthetic root — start with its children
	for (const child of root.children.values()) {
		visit(child, 0);
	}

	// Root-level no-response leaves (responseOids === [])
	for (const leaf of root.leaves) {
		rows.push({
			depth: 0,
			description: leaf.description,
			exchange: leaf.exchange,
			kind: "leaf",
			name: leaf.name,
			oid: leaf.oid,
			shared: leaf.shared,
		});
	}

	return rows;
}

export function autoExpand(node: TrieNode): void {
	if (node.children.size <= AUTO_EXPAND_MAX_CHILDREN) {
		node.expanded = true;
	}
	for (const child of node.children.values()) {
		autoExpand(child);
	}
}

export function collapseAll(node: TrieNode): void {
	node.expanded = false;
	for (const child of node.children.values()) {
		collapseAll(child);
	}
}
