import { describe, expect, it } from 'bun:test'
import { autoExpand, buildTrie, flatten, rollup } from '../../src/lib/oidTrie'
import { asOid } from '../../src/lib/model'
import type { DomainExchange, FilterState } from '../../src/lib/model'

function makeExchange(responseOids: string[], overrides: Partial<DomainExchange> = {}): DomainExchange {
  return {
    seq: 1,
    rtt: 50,
    isTimeout: false,
    violations: [],
    attemptCount: 1,
    requestOid: asOid('1.3.6.1'),
    responseOids: responseOids.map(o => asOid(o)),
    sentAtMs: 0,
    receivedAtMs: 50,
    ...overrides,
  }
}

function makeState(overrides: Partial<FilterState> = {}): FilterState {
  return {
    slow: false,
    violations: false,
    retries: false,
    timeouts: false,
    slowMs: 1000,
    ...overrides,
  }
}

describe('buildTrie', () => {
  it('empty input returns root with no children', () => {
    const root = buildTrie([], makeState())
    expect(root.children.size).toBe(0)
    expect(root.leaves).toHaveLength(0)
    expect(root.arc).toBe('')
  })

  it('single-OID exchange creates one path of nodes with leaf at deepest node', () => {
    const ex = makeExchange(['1.3.6.1.2.1'])
    const root = buildTrie([ex], makeState())

    // Walk the path: 1 → 3 → 6 → 1 → 2 → 1
    expect(root.children.size).toBe(1)
    const n1 = root.children.get('1')
    expect(n1).toBeDefined()
    expect(n1!.arc).toBe('1')

    const node = n1!.children.get('3')!.children.get('6')!
      .children.get('1')!.children.get('2')!.children.get('1')!

    expect(node.leaves).toHaveLength(1)
    const leaf = node.leaves[0]
    expect(leaf?.exchange).toBe(ex)
    expect(leaf?.shared).toBe(false)
    expect(node.children.size).toBe(0)
  })

  it('multi-OID exchange: leaf appears under two nodes, both with shared=true', () => {
    const ex = makeExchange(['1.3.6.1.2.1', '1.3.6.1.2.2'])
    const root = buildTrie([ex], makeState())
    const base = root.children.get('1')!.children.get('3')!.children.get('6')!
      .children.get('1')!.children.get('2')!

    // Navigate to 1.3.6.1.2.1
    const n1 = base.children.get('1')!
    expect(n1.leaves).toHaveLength(1)
    expect(n1.leaves[0]?.shared).toBe(true)

    // Navigate to 1.3.6.1.2.2
    const n2 = base.children.get('2')!
    expect(n2.leaves).toHaveLength(1)
    expect(n2.leaves[0]?.shared).toBe(true)
    expect(n2.leaves[0]?.exchange).toBe(ex)
  })

  it('filtered exchange is excluded when filter excludes it', () => {
    // violations filter active, exchange has no violations → excluded
    const ex = makeExchange(['1.3.6.1'], { violations: [] })
    const root = buildTrie([ex], makeState({ violations: true }))
    expect(root.children.size).toBe(0)
  })

  it('well-known OID prefix gets a name', () => {
    const ex = makeExchange(['1.3.6.1.2.1.1.1'])
    const root = buildTrie([ex], makeState())
    // 1.3.6.1.2.1.1 node should have name 'system'
    const systemNode = root.children.get('1')!.children.get('3')!.children.get('6')!
      .children.get('1')!.children.get('2')!.children.get('1')!.children.get('1')!
    expect(systemNode.name).toBe('system')
    expect(systemNode.fullOid).toBe(asOid('1.3.6.1.2.1.1'))
  })
})

describe('rollup', () => {
  it('aggregates count and maxRtt from leaves', () => {
    const ex = makeExchange(['1.3.6.1'], { rtt: 500 })
    const root = buildTrie([ex], makeState())
    rollup(root, 1000)

    // The leaf node is at depth 4: 1 → 3 → 6 → 1
    const deepNode = root.children.get('1')!.children.get('3')!
      .children.get('6')!.children.get('1')!
    expect(deepNode.stats.count).toBe(1)
    expect(deepNode.stats.maxRtt).toBe(500)

    // Root should also aggregate up
    expect(root.stats.count).toBe(1)
    expect(root.stats.maxRtt).toBe(500)
  })

  it('severity 2 propagates to root when violation exists', () => {
    const ex = makeExchange(['1.3.6.1.2'], { violations: ['oid-mismatch'] })
    const root = buildTrie([ex], makeState())
    rollup(root, 1000)
    expect(root.severity).toBe(2)
  })

  it('severity 1 for slow exchange (no violations)', () => {
    const ex = makeExchange(['1.3.6.1'], { rtt: 1500 })
    const root = buildTrie([ex], makeState())
    rollup(root, 1000)
    expect(root.severity).toBe(1)
  })

  it('severity 0 for normal exchange', () => {
    const ex = makeExchange(['1.3.6.1'], { rtt: 50 })
    const root = buildTrie([ex], makeState())
    rollup(root, 1000)
    expect(root.severity).toBe(0)
  })

  it('violationCount is incremented for violation exchanges', () => {
    const ex = makeExchange(['1.3.6.1'], { violations: ['err1', 'err2'] })
    const root = buildTrie([ex], makeState())
    rollup(root, 1000)
    expect(root.stats.violationCount).toBe(1)
  })

  it('maxRtt takes the maximum across multiple leaves', () => {
    const ex1 = makeExchange(['1.3.6.1'], { seq: 1, rtt: 200 })
    const ex2 = makeExchange(['1.3.6.2'], { seq: 2, rtt: 800 })
    const root = buildTrie([ex1, ex2], makeState())
    rollup(root, 1000)
    expect(root.stats.maxRtt).toBe(800)
    expect(root.stats.count).toBe(2)
  })
})

describe('flatten', () => {
  it('virtual root itself is not in output', () => {
    const ex = makeExchange(['1.3.6.1'])
    const root = buildTrie([ex], makeState())
    root.children.get('1')!.expanded = true
    const rows = flatten(root)
    for (const row of rows) {
      if (row.kind === 'node') {
        expect(row.node.arc).not.toBe('')
      }
    }
  })

  it('returns empty array when root has no children', () => {
    const root = buildTrie([], makeState())
    expect(flatten(root)).toHaveLength(0)
  })

  it('collapsed nodes do not show children in output', () => {
    const ex = makeExchange(['1.3.6.1.2.1'])
    const root = buildTrie([ex], makeState())
    // No nodes are expanded — only top-level nodes appear
    const rows = flatten(root)
    // Only the arc='1' node at depth 0
    expect(rows).toHaveLength(1)
    const [row0] = rows
    expect(row0?.kind).toBe('node')
    if (row0?.kind === 'node') {
      expect(row0.depth).toBe(0)
      expect(row0.node.arc).toBe('1')
    }
  })

  it('expanded nodes show children and leaves', () => {
    const ex = makeExchange(['1.3.6.1'])
    const root = buildTrie([ex], makeState())
    // Expand the first-level node '1'
    const n1 = root.children.get('1')!
    n1.expanded = true
    const rows = flatten(root)
    // Should have: depth-0 node '1', then its children at depth 1
    expect(rows.length).toBeGreaterThan(1)
    const [r0, r1] = rows
    expect(r0?.depth).toBe(0)
    expect(r1?.depth).toBe(1)
  })

  it('leaf rows appear after node rows when expanded', () => {
    const ex = makeExchange(['1'])
    const root = buildTrie([ex], makeState())
    const n1 = root.children.get('1')!
    n1.expanded = true
    const rows = flatten(root)
    // n1 has a leaf directly (OID '1' has arc ['1'])
    expect(rows).toHaveLength(2)
    const [r0, r1] = rows
    expect(r0?.kind).toBe('node')
    expect(r1?.kind).toBe('leaf')
    if (r1?.kind === 'leaf') {
      expect(r1.depth).toBe(1)
      expect(r1.exchange).toBe(ex)
    }
  })
})

describe('autoExpand', () => {
  it('nodes with anomalous descendants are expanded after rollup + autoExpand', () => {
    const exBad = makeExchange(['1.3.6.1.2'], { violations: ['err'] })
    const exOk = makeExchange(['2.1.1'], { rtt: 10 })
    const root = buildTrie([exBad, exOk], makeState())
    rollup(root, 1000)
    autoExpand(root)

    // The '1' subtree should be expanded (has violation)
    expect(root.children.get('1')!.expanded).toBe(true)
    // The '2' subtree should NOT be expanded (ok exchange)
    expect(root.children.get('2')!.expanded).toBe(false)
  })

  it('nodes with only ok leaves are not expanded', () => {
    const ex = makeExchange(['1.3.6.1'], { rtt: 50 })
    const root = buildTrie([ex], makeState())
    rollup(root, 1000)
    autoExpand(root)
    expect(root.children.get('1')!.expanded).toBe(false)
  })

  it('returns true when any descendant has severity > 0', () => {
    const ex = makeExchange(['1.3.6.1'], { violations: ['err'] })
    const root = buildTrie([ex], makeState())
    rollup(root, 1000)
    const result = autoExpand(root)
    expect(result).toBe(true)
  })

  it('returns false when no descendant has severity > 0', () => {
    const ex = makeExchange(['1.3.6.1'], { rtt: 50 })
    const root = buildTrie([ex], makeState())
    rollup(root, 1000)
    const result = autoExpand(root)
    expect(result).toBe(false)
  })

  it('slow exchange (severity 1) also triggers autoExpand', () => {
    const ex = makeExchange(['1.3.6.1'], { rtt: 2000 })
    const root = buildTrie([ex], makeState())
    rollup(root, 1000)
    autoExpand(root)
    expect(root.children.get('1')!.expanded).toBe(true)
  })
})
