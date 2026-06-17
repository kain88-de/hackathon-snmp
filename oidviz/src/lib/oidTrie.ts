import {
  asOid,
  type DomainExchange,
  type FlatRow,
  type OidString,
  type TrieLeaf,
  type TrieNode,
} from './model';

const WELL_KNOWN: Record<string, string> = {
  '1.3.6.1.2.1.1': 'system',
  '1.3.6.1.2.1.11': 'snmp',
  '1.3.6.1.2.1.2': 'interfaces',
  '1.3.6.1.2.1.25': 'host',
  '1.3.6.1.2.1.4': 'ip',
  '1.3.6.1.2.1.6': 'tcp',
  '1.3.6.1.4.1.9': 'cisco',
  '1.3.6.1.6.3.15': 'snmpVacm',
};

const OID_SEPARATOR = '.';
const NONE = 0;
const SINGLE = 1;
const START_DEPTH = 0;
const DEPTH_INCREMENT = 1;
const MULTI_ATTEMPT_THRESHOLD = 1;

const wellKnownName = (fullOid: OidString): string | null => {
  const found = WELL_KNOWN[fullOid];
  if (found) {
    return found;
  }
  return null;
};

const makeNode = (arc: string, fullOid: OidString): TrieNode => ({
  arc,
  children: new Map(),
  expanded: false,
  flags: { retry: false, slow: false, violation: false },
  fullOid,
  leaves: [],
  name: wellKnownName(fullOid),
  stats: { count: NONE, maxRtt: NONE, violationCount: NONE },
});

const buildFullOid = (parent: string, arc: string): string => {
  if (parent === '') {
    return arc;
  }
  return `${parent}${OID_SEPARATOR}${arc}`;
};

const getOrCreateChild = (node: TrieNode, arc: string, fullOid: string): TrieNode => {
  if (node.children.has(arc)) {
    return node.children.get(arc) as TrieNode;
  }
  const child = makeNode(arc, asOid(fullOid));
  node.children.set(arc, child);
  return child;
};

const insertLeaf = (root: TrieNode, oid: OidString, leaf: TrieLeaf): void => {
  const arcs = oid.split(OID_SEPARATOR);
  let node = root;
  let fullOid = '';
  for (const arc of arcs) {
    fullOid = buildFullOid(fullOid, arc);
    node = getOrCreateChild(node, arc, fullOid);
  }
  node.leaves.push(leaf);
};

export const buildTrie = (exchanges: readonly DomainExchange[]): TrieNode => {
  const root = makeNode('', asOid(''));
  for (const ex of exchanges) {
    const shared = ex.responseOids.length > SINGLE;
    for (const oid of ex.responseOids) {
      insertLeaf(root, oid, { exchange: ex, oid, shared });
    }
  }
  return root;
};

const rollupLeaf = (node: TrieNode, leaf: TrieLeaf, slowMs: number): void => {
  node.flags.slow ||= leaf.exchange.rtt > slowMs;
  node.flags.violation ||= leaf.exchange.violations.length > NONE;
  node.flags.retry ||= leaf.exchange.attemptCount > MULTI_ATTEMPT_THRESHOLD;
  node.stats.count += SINGLE;
  node.stats.maxRtt = Math.max(node.stats.maxRtt, leaf.exchange.rtt);
  if (leaf.exchange.violations.length > NONE) {
    node.stats.violationCount += SINGLE;
  }
};

const mergeChild = (node: TrieNode, child: TrieNode): void => {
  node.flags.slow ||= child.flags.slow;
  node.flags.violation ||= child.flags.violation;
  node.flags.retry ||= child.flags.retry;
  node.stats.count += child.stats.count;
  node.stats.maxRtt = Math.max(node.stats.maxRtt, child.stats.maxRtt);
  node.stats.violationCount += child.stats.violationCount;
};

export const rollup = (node: TrieNode, slowMs: number): void => {
  for (const child of node.children.values()) {
    rollup(child, slowMs);
    mergeChild(node, child);
  }
  for (const leaf of node.leaves) {
    rollupLeaf(node, leaf, slowMs);
  }
};

const flattenNode = (node: TrieNode, depth: number, out: FlatRow[]): void => {
  out.push({ depth, kind: 'node', node });
  const nextDepth = depth + DEPTH_INCREMENT;
  for (const child of node.children.values()) {
    flattenNode(child, nextDepth, out);
  }
  for (const leaf of node.leaves) {
    out.push({ depth, exchange: leaf.exchange, kind: 'leaf', oid: leaf.oid, shared: leaf.shared });
  }
};

export const flatten = (root: TrieNode): FlatRow[] => {
  const out: FlatRow[] = [];
  for (const child of root.children.values()) {
    flattenNode(child, START_DEPTH, out);
  }
  return out;
};

export const autoExpand = (node: TrieNode): boolean => {
  const { flags } = node;
  let anyDescendant = false;
  for (const child of node.children.values()) {
    if (autoExpand(child)) {
      anyDescendant = true;
    }
  }
  const shouldExpand = flags.slow || flags.violation || flags.retry || anyDescendant;
  if (shouldExpand) {
    node.expanded = true;
  }
  return shouldExpand;
};
