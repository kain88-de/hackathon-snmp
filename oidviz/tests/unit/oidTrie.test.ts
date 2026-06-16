import { describe, expect, it } from 'bun:test';
import type { DomainExchange } from '../../src/lib/model';
import { asOid } from '../../src/lib/model';
import { autoExpand, buildTrie, flatten, rollup } from '../../src/lib/oidTrie';

const makeExchange = (overrides: Partial<DomainExchange> = {}): DomainExchange => ({
  seq: 1,
  rtt: 10,
  isTimeout: false,
  violations: [],
  attemptCount: 1,
  requestOid: asOid('1.3.6.1.2.1.1'),
  responseOids: [asOid('1.3.6.1.2.1.1')],
  sentAtMs: 0,
  receivedAtMs: 10,
  ...overrides,
});

describe('buildTrie', () => {
  it('creates a leaf in the correct trie node for a single responseOid', () => {
    const ex = makeExchange({ responseOids: [asOid('1.3.6.1.2.1.1')] });
    const root = buildTrie([ex]);

    // Navigate to node '1' -> '3' -> '6' -> '1' -> '2' -> '1' -> '1'
    const node1 = root.children.get('1');
    expect(node1).toBeDefined();
    const node3 = node1?.children.get('3');
    expect(node3).toBeDefined();

    // The leaf should exist somewhere under the tree with the correct oid
    const rows = flatten(root);
    const leafRow = rows.find((r) => r.kind === 'leaf');
    expect(leafRow).toBeDefined();
    if (leafRow?.kind === 'leaf') {
      expect(leafRow.oid).toBe(asOid('1.3.6.1.2.1.1'));
      expect(leafRow.exchange).toBe(ex);
    }
  });

  it('sets shared=false when exchange has exactly one responseOid', () => {
    const ex = makeExchange({ responseOids: [asOid('1.3.6.1.2.1.1')] });
    const root = buildTrie([ex]);
    const rows = flatten(root);
    const leafRow = rows.find((r) => r.kind === 'leaf');
    expect(leafRow?.kind === 'leaf' && leafRow.shared).toBe(false);
  });

  it('sets shared=true on each leaf when exchange has 2+ responseOids', () => {
    const ex = makeExchange({
      responseOids: [asOid('1.3.6.1.2.1.1'), asOid('1.3.6.1.2.1.2')],
    });
    const root = buildTrie([ex]);
    const rows = flatten(root);
    const leafRows = rows.filter((r) => r.kind === 'leaf');
    expect(leafRows).toHaveLength(2);
    for (const row of leafRows) {
      expect(row.kind === 'leaf' && row.shared).toBe(true);
    }
  });

  it('assigns leaf.oid to the specific responseOid, not requestOid', () => {
    const ex = makeExchange({
      requestOid: asOid('1.3.6.1.2.1.1'),
      responseOids: [asOid('1.3.6.1.2.1.2')],
    });
    const root = buildTrie([ex]);
    const rows = flatten(root);
    const leafRow = rows.find((r) => r.kind === 'leaf');
    expect(leafRow?.kind === 'leaf' && leafRow.oid).toBe(asOid('1.3.6.1.2.1.2'));
  });
});

describe('rollup', () => {
  it('sets flags.slow=true on parent node when leaf rtt > slowMs', () => {
    const slowMs = 100;
    const ex = makeExchange({ rtt: 200, responseOids: [asOid('1.3.6.1')] });
    const root = buildTrie([ex]);
    rollup(root, slowMs);

    const node1 = root.children.get('1');
    expect(node1?.flags.slow).toBe(true);
  });

  it('sets flags.slow=false when leaf rtt <= slowMs', () => {
    const slowMs = 100;
    const ex = makeExchange({ rtt: 50, responseOids: [asOid('1.3.6.1')] });
    const root = buildTrie([ex]);
    rollup(root, slowMs);

    const node1 = root.children.get('1');
    expect(node1?.flags.slow).toBe(false);
  });

  it('sets flags.violation=true when a leaf has violations', () => {
    const ex = makeExchange({
      violations: ['some-violation'],
      responseOids: [asOid('1.3.6.1')],
    });
    const root = buildTrie([ex]);
    rollup(root, 100);

    const node1 = root.children.get('1');
    expect(node1?.flags.violation).toBe(true);
  });

  it('sets flags.retry=true when a leaf has attemptCount > 1', () => {
    const ex = makeExchange({ attemptCount: 2, responseOids: [asOid('1.3.6.1')] });
    const root = buildTrie([ex]);
    rollup(root, 100);

    const node1 = root.children.get('1');
    expect(node1?.flags.retry).toBe(true);
  });

  it('processes children before own leaves (bottom-up)', () => {
    // Node '1.3.6.1' has a deep leaf at '1.3.6.1.2.1.1' with slow rtt
    // After rollup, the ancestor '1' should also be flagged slow
    const ex = makeExchange({ rtt: 200, responseOids: [asOid('1.3.6.1.2.1.1')] });
    const root = buildTrie([ex]);
    rollup(root, 100);

    // All ancestors of the leaf should have flags.slow=true
    const node1 = root.children.get('1');
    const node3 = node1?.children.get('3');
    const node6 = node3?.children.get('6');
    const node1b = node6?.children.get('1');
    expect(node1b?.flags.slow).toBe(true);
    expect(node3?.flags.slow).toBe(true);
    expect(node1?.flags.slow).toBe(true);
  });

  it('updates stats.count and stats.maxRtt after rollup', () => {
    const ex1 = makeExchange({ rtt: 50, responseOids: [asOid('1.3.6.1.2')] });
    const ex2 = makeExchange({ rtt: 80, responseOids: [asOid('1.3.6.1.4')] });
    const root = buildTrie([ex1, ex2]);
    rollup(root, 100);

    const node1 = root.children.get('1');
    const node3 = node1?.children.get('3');
    const node6 = node3?.children.get('6');
    const node1b = node6?.children.get('1');
    // Both leaves are under 1.3.6.1
    expect(node1b?.stats.count).toBe(2);
    expect(node1b?.stats.maxRtt).toBe(80);
  });

  it('updates stats.violationCount after rollup', () => {
    const ex = makeExchange({
      violations: ['v1', 'v2'],
      responseOids: [asOid('1.3.6.1')],
    });
    const root = buildTrie([ex]);
    rollup(root, 100);

    const node1 = root.children.get('1');
    expect(node1?.stats.violationCount).toBe(1);
  });
});

describe('flatten', () => {
  it('skips the synthetic root node (arc="")', () => {
    const ex = makeExchange({ responseOids: [asOid('1.3.6.1')] });
    const root = buildTrie([ex]);
    const rows = flatten(root);

    // No row should be the root itself
    const rootRow = rows.find((r) => r.kind === 'node' && r.node.arc === '');
    expect(rootRow).toBeUndefined();
  });

  it('produces node rows followed by their children in DFS order', () => {
    const ex = makeExchange({ responseOids: [asOid('1.3.6.1')] });
    const root = buildTrie([ex]);
    const rows = flatten(root);

    // All rows should appear — check that node for '1' appears before node for '3'
    const idx1 = rows.findIndex((r) => r.kind === 'node' && r.node.arc === '1');
    const idx3 = rows.findIndex((r) => r.kind === 'node' && r.node.arc === '3');
    expect(idx1).toBeGreaterThanOrEqual(0);
    expect(idx3).toBeGreaterThan(idx1);
  });

  it('puts leaves after all children of the same node', () => {
    // Put a leaf directly on an intermediate node and a child node
    // We do this by having two oids: '1.3' and '1.3.6'
    const ex1 = makeExchange({ seq: 1, responseOids: [asOid('1.3')] });
    const ex2 = makeExchange({ seq: 2, responseOids: [asOid('1.3.6')] });
    const root = buildTrie([ex1, ex2]);
    const rows = flatten(root);

    // Node '3' should appear, then its child node '6', then the leaf on '3'
    const idx3Node = rows.findIndex((r) => r.kind === 'node' && r.node.arc === '3');
    const idx6Node = rows.findIndex((r) => r.kind === 'node' && r.node.arc === '6');
    const idx3Leaf = rows.findIndex(
      (r) => r.kind === 'leaf' && r.oid === asOid('1.3'),
    );
    expect(idx3Node).toBeGreaterThanOrEqual(0);
    expect(idx6Node).toBeGreaterThan(idx3Node);
    expect(idx3Leaf).toBeGreaterThan(idx6Node);
  });

  it('assigns correct depth values', () => {
    const ex = makeExchange({ responseOids: [asOid('1.3.6')] });
    const root = buildTrie([ex]);
    const rows = flatten(root);

    const node1 = rows.find((r) => r.kind === 'node' && r.node.arc === '1');
    const node3 = rows.find((r) => r.kind === 'node' && r.node.arc === '3');
    const node6 = rows.find((r) => r.kind === 'node' && r.node.arc === '6');
    expect(node1?.depth).toBe(0);
    expect(node3?.depth).toBe(1);
    expect(node6?.depth).toBe(2);
  });
});

describe('autoExpand', () => {
  it('expands a node when it has flags.slow set', () => {
    const ex = makeExchange({ rtt: 200, responseOids: [asOid('1.3.6.1')] });
    const root = buildTrie([ex]);
    rollup(root, 100);
    autoExpand(root);

    const node1 = root.children.get('1');
    expect(node1?.expanded).toBe(true);
  });

  it('does not expand a node when no flags are set', () => {
    const ex = makeExchange({ rtt: 10, responseOids: [asOid('1.3.6.1')] });
    const root = buildTrie([ex]);
    rollup(root, 100);
    autoExpand(root);

    const node1 = root.children.get('1');
    expect(node1?.expanded).toBe(false);
  });

  it('expands ancestor nodes when a deep descendant has a flag', () => {
    const ex = makeExchange({ rtt: 200, responseOids: [asOid('1.3.6.1.2.1.1')] });
    const root = buildTrie([ex]);
    rollup(root, 100);
    autoExpand(root);

    // All ancestors of the slow leaf should be expanded
    const node1 = root.children.get('1');
    const node3 = node1?.children.get('3');
    const node6 = node3?.children.get('6');
    expect(node1?.expanded).toBe(true);
    expect(node3?.expanded).toBe(true);
    expect(node6?.expanded).toBe(true);
  });

  it('returns true when the node was expanded, false otherwise', () => {
    const exSlow = makeExchange({ rtt: 200, responseOids: [asOid('1.3.6.1')] });
    const rootSlow = buildTrie([exSlow]);
    rollup(rootSlow, 100);
    const result = autoExpand(rootSlow);
    // Root itself doesn't get expanded (only children do), but returns true
    // because it found a descendant that needed expansion
    expect(result).toBe(true);

    const exFast = makeExchange({ rtt: 10, responseOids: [asOid('1.3.6.1')] });
    const rootFast = buildTrie([exFast]);
    rollup(rootFast, 100);
    const resultFast = autoExpand(rootFast);
    expect(resultFast).toBe(false);
  });
});

describe('well-known OID names', () => {
  it('assigns name="system" to node at fullOid 1.3.6.1.2.1.1', () => {
    const ex = makeExchange({ responseOids: [asOid('1.3.6.1.2.1.1.5.0')] });
    const root = buildTrie([ex]);
    const rows = flatten(root);

    const systemNode = rows.find(
      (r) => r.kind === 'node' && r.node.fullOid === '1.3.6.1.2.1.1',
    );
    expect(systemNode).toBeDefined();
    if (systemNode?.kind === 'node') {
      expect(systemNode.node.name).toBe('system');
    }
  });

  it('assigns name="interfaces" to node at fullOid 1.3.6.1.2.1.2', () => {
    const ex = makeExchange({ responseOids: [asOid('1.3.6.1.2.1.2.2.1.1')] });
    const root = buildTrie([ex]);
    const rows = flatten(root);

    const ifNode = rows.find(
      (r) => r.kind === 'node' && r.node.fullOid === '1.3.6.1.2.1.2',
    );
    expect(ifNode).toBeDefined();
    if (ifNode?.kind === 'node') {
      expect(ifNode.node.name).toBe('interfaces');
    }
  });

  it('assigns null name to nodes not in the well-known list', () => {
    const ex = makeExchange({ responseOids: [asOid('1.3.6.1.2.1.1')] });
    const root = buildTrie([ex]);
    const rows = flatten(root);

    // Node '1' should not have a well-known name
    const node1 = rows.find((r) => r.kind === 'node' && r.node.arc === '1');
    if (node1?.kind === 'node') {
      expect(node1.node.name).toBeNull();
    }
  });
});
