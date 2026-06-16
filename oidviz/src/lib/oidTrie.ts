import { matchesFilters } from './filters';
import type {
  DomainExchange,
  FilterState,
  FlatRow,
  TrieLeaf,
  TrieNode,
} from './model';
import { Severity, asOid } from './model';

const WELL_KNOWN: ReadonlyMap<string, string> = new Map([
  ['1.3.6.1.2.1.1', 'system'],
  ['1.3.6.1.2.1.2', 'interfaces'],
  ['1.3.6.1.2.1.4', 'ip'],
  ['1.3.6.1.2.1.6', 'tcp'],
  ['1.3.6.1.2.1.11', 'snmp'],
  ['1.3.6.1.2.1.25', 'host'],
  ['1.3.6.1.4.1.9', 'cisco'],
  ['1.3.6.1.6.3.16', 'snmpVacm'],
]);

function makeNode(arc: string, path: string): TrieNode {
  return {
    arc,
    fullOid: asOid(path),
    name: WELL_KNOWN.get(path) ?? null,
    children: new Map(),
    leaves: [],
    expanded: false,
    stats: { count: 0, maxRtt: 0, violationCount: 0 },
    severity: Severity.Ok,
  };
}

function insertOid(root: TrieNode, oid: string, leaf: TrieLeaf): void {
  let node = root;
  let path = '';
  for (const arc of oid.split('.')) {
    path = path === '' ? arc : `${path}.${arc}`;
    let child = node.children.get(arc);
    if (child === undefined) {
      child = makeNode(arc, path);
      node.children.set(arc, child);
    }
    node = child;
  }
  node.leaves.push(leaf);
}

export function buildTrie(
  exchanges: readonly DomainExchange[],
  state: Readonly<FilterState>,
): TrieNode {
  const root = makeNode('', '');

  for (const ex of exchanges) {
    if (!matchesFilters(ex, state)) {
      continue;
    }
    const shared = ex.responseOids.length > 1;
    const leaf: TrieLeaf = { exchange: ex, shared };
    for (const oid of ex.responseOids) {
      insertOid(root, oid, leaf);
    }
  }

  return root;
}

export function rollup(node: TrieNode, slowMs: number): void {
  for (const child of node.children.values()) {
    rollup(child, slowMs);
    node.stats.count += child.stats.count;
    node.stats.maxRtt = Math.max(node.stats.maxRtt, child.stats.maxRtt);
    node.stats.violationCount += child.stats.violationCount;
    node.severity = Math.max(node.severity, child.severity) as Severity;
  }

  for (const leaf of node.leaves) {
    let leafSeverity: Severity;
    if (leaf.exchange.violations.length > 0) {
      leafSeverity = Severity.Violation;
    } else if (leaf.exchange.rtt > slowMs) {
      leafSeverity = Severity.Slow;
    } else {
      leafSeverity = Severity.Ok;
    }
    node.stats.count += 1;
    node.stats.maxRtt = Math.max(node.stats.maxRtt, leaf.exchange.rtt);
    node.stats.violationCount += leaf.exchange.violations.length > 0 ? 1 : 0;
    node.severity = Math.max(node.severity, leafSeverity) as Severity;
  }
}

function visitNode(node: TrieNode, depth: number, rows: FlatRow[]): void {
  rows.push({ kind: 'node', depth, node });
  if (node.expanded) {
    for (const child of node.children.values()) {
      visitNode(child, depth + 1, rows);
    }
    for (const leaf of node.leaves) {
      rows.push({
        kind: 'leaf',
        depth: depth + 1,
        exchange: leaf.exchange,
        shared: leaf.shared,
      });
    }
  }
}

export function flatten(root: TrieNode): FlatRow[] {
  const rows: FlatRow[] = [];
  for (const child of root.children.values()) {
    visitNode(child, 0, rows);
  }
  return rows;
}

export function autoExpand(node: TrieNode): boolean {
  let anyAnomalous = false;
  for (const child of node.children.values()) {
    if (autoExpand(child)) {
      anyAnomalous = true;
    }
  }
  if (node.severity > Severity.Ok) {
    anyAnomalous = true;
  }
  if (anyAnomalous) {
    node.expanded = true;
  }
  return anyAnomalous;
}
