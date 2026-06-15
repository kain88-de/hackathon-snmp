import { describe, expect, it } from 'bun:test'
import { buildIncidents } from '../../src/lib/incidentStack'
import { asOid } from '../../src/lib/model'
import type { DomainExchange } from '../../src/lib/model'

function makeExchange(seq: number, overrides: Partial<DomainExchange> = {}): DomainExchange {
  return {
    seq,
    rtt: 50,
    isTimeout: false,
    violations: [],
    attemptCount: 1,
    requestOid: asOid('1.3.6.1.2.1.1.1'),
    responseOids: [],
    sentAtMs: seq * 100,
    receivedAtMs: seq * 100 + 50,
    ...overrides,
  }
}

describe('buildIncidents', () => {
  it('empty input returns []', () => {
    expect(buildIncidents([], 1000)).toEqual([])
  })

  it('no anomalous exchanges returns []', () => {
    const exchanges = [
      makeExchange(1),
      makeExchange(2),
      makeExchange(3),
    ]
    expect(buildIncidents(exchanges, 1000)).toEqual([])
  })

  it('single anomalous exchange produces one incident with one member', () => {
    const exchanges = [
      makeExchange(1),
      makeExchange(2, { rtt: 2000 }),
      makeExchange(3),
    ]
    const incidents = buildIncidents(exchanges, 1000)
    expect(incidents).toHaveLength(1)
    const inc = incidents[0]!
    expect(inc.members).toEqual([1])
    expect(inc.startIdx).toBe(1)
    expect(inc.endIdx).toBe(1)
  })

  it('gap of exactly 8 merges into one incident', () => {
    // index 0: anomalous, indices 1-8: normal (8 exchanges), index 9: anomalous
    // gap = 9 - 0 - 1 = 8 → should merge
    const exchanges = [
      makeExchange(0, { rtt: 2000 }),   // index 0, anomalous
      makeExchange(1),
      makeExchange(2),
      makeExchange(3),
      makeExchange(4),
      makeExchange(5),
      makeExchange(6),
      makeExchange(7),
      makeExchange(8),                   // index 8, 8 normal exchanges (gap = 8)
      makeExchange(9, { rtt: 2000 }),    // index 9, anomalous
    ]
    const incidents = buildIncidents(exchanges, 1000)
    expect(incidents).toHaveLength(1)
    expect(incidents[0]!.members).toEqual([0, 9])
  })

  it('gap of 9 does not merge — produces two incidents', () => {
    // index 0: anomalous (system region), indices 1-9: normal (9 exchanges), index 10: anomalous (ip region)
    // gap = 10 - 0 - 1 = 9 → should NOT merge (gap too large, different regions)
    const systemOid = asOid('1.3.6.1.2.1.1.1')   // system
    const ipOid = asOid('1.3.6.1.2.1.4.1')       // ip
    const exchanges = [
      makeExchange(0, { rtt: 2000, requestOid: systemOid }),   // index 0, anomalous
      makeExchange(1),
      makeExchange(2),
      makeExchange(3),
      makeExchange(4),
      makeExchange(5),
      makeExchange(6),
      makeExchange(7),
      makeExchange(8),
      makeExchange(9),                                          // index 9, 9 normal exchanges (gap = 9)
      makeExchange(10, { rtt: 2000, requestOid: ipOid }),      // index 10, anomalous, different region
    ]
    const incidents = buildIncidents(exchanges, 1000)
    expect(incidents).toHaveLength(2)
  })

  it('region-based merge ignores gap — two anomalous in same region merge even 20 apart', () => {
    // Both use 1.3.6.1.2.1.11.x → 'snmp' region; 20 normal exchanges between them
    const sameRegionOid = asOid('1.3.6.1.2.1.11.1')
    const exchanges: DomainExchange[] = [
      makeExchange(0, { rtt: 2000, requestOid: sameRegionOid }),
      // 20 normal exchanges
      ...Array.from({ length: 20 }, (_, k) =>
        makeExchange(k + 1, { requestOid: sameRegionOid })
      ),
      makeExchange(21, { rtt: 2000, requestOid: sameRegionOid }),
    ]
    const incidents = buildIncidents(exchanges, 1000)
    expect(incidents).toHaveLength(1)
    expect(incidents[0]!.members).toEqual([0, 21])
  })

  it('non-anomalous exchanges are not members', () => {
    const exchanges = [
      makeExchange(0, { rtt: 2000 }),   // index 0, anomalous
      makeExchange(1),                   // index 1, normal
      makeExchange(2),                   // index 2, normal
      makeExchange(3, { rtt: 2000 }),   // index 3, anomalous
    ]
    const incidents = buildIncidents(exchanges, 1000)
    expect(incidents).toHaveLength(1)
    const inc = incidents[0]!
    expect(inc.members).toEqual([0, 3])
    // Normal indices 1 and 2 must NOT be in members
    expect(inc.members).not.toContain(1)
    expect(inc.members).not.toContain(2)
  })

  it('retryCount is sum of (attemptCount - 1)', () => {
    // One exchange with attemptCount=3 contributes 2, not 1
    const exchanges = [
      makeExchange(0, { attemptCount: 3 }),
    ]
    const incidents = buildIncidents(exchanges, 1000)
    expect(incidents).toHaveLength(1)
    expect(incidents[0]!.retryCount).toBe(2)
  })

  it('returned array is sorted by score descending', () => {
    // Create three separate incident clusters (gap > 8, different regions to avoid region merge)
    // Cluster A: timeout (score ~100)
    // Cluster B: violation (score ~50)
    // Cluster C: slow only (score ~log10(2000)*5 ≈ 16.5)
    const regionA = asOid('1.3.6.1.2.1.1.1')   // system
    const regionB = asOid('1.3.6.1.2.1.4.1')   // ip
    const regionC = asOid('1.3.6.1.2.1.6.1')   // tcp

    const exchanges: DomainExchange[] = [
      // Cluster A: timeout at index 0
      makeExchange(0,  { isTimeout: true, requestOid: regionA }),
      // 9 normal gaps with varying regions to avoid region-based merges
      makeExchange(1, { requestOid: regionB }),
      makeExchange(2, { requestOid: regionC }),
      makeExchange(3, { requestOid: regionB }),
      makeExchange(4, { requestOid: regionC }),
      makeExchange(5, { requestOid: regionB }),
      makeExchange(6, { requestOid: regionC }),
      makeExchange(7, { requestOid: regionB }),
      makeExchange(8, { requestOid: regionC }),
      makeExchange(9, { requestOid: regionB }),
      // Cluster B: violation at index 10
      makeExchange(10, { violations: ['oid-mismatch'], requestOid: regionC }),
      makeExchange(11, { requestOid: regionA }),
      makeExchange(12, { requestOid: regionB }),
      makeExchange(13, { requestOid: regionA }),
      makeExchange(14, { requestOid: regionB }),
      makeExchange(15, { requestOid: regionA }),
      makeExchange(16, { requestOid: regionB }),
      makeExchange(17, { requestOid: regionA }),
      makeExchange(18, { requestOid: regionB }),
      makeExchange(19, { requestOid: regionA }),
      // Cluster C: slow at index 20
      makeExchange(20, { rtt: 2000, requestOid: regionB }),
    ]
    const incidents = buildIncidents(exchanges, 1000)
    // Should have 3 separate incidents
    expect(incidents).toHaveLength(3)
    // Verify descending score order
    for (let i = 0; i < incidents.length - 1; i++) {
      expect(incidents[i]!.score).toBeGreaterThanOrEqual(incidents[i + 1]!.score)
    }
    // Timeout incident should have the highest score
    expect(incidents[0]!.timeoutCount).toBe(1)
  })

  describe('anomaly detection', () => {
    it('rtt > slowMs triggers anomaly', () => {
      const exchanges = [makeExchange(0, { rtt: 1001 })]
      expect(buildIncidents(exchanges, 1000)).toHaveLength(1)
    })

    it('rtt === slowMs does not trigger anomaly', () => {
      const exchanges = [makeExchange(0, { rtt: 1000 })]
      expect(buildIncidents(exchanges, 1000)).toHaveLength(0)
    })

    it('violations.length > 0 triggers anomaly', () => {
      const exchanges = [makeExchange(0, { violations: ['err'] })]
      expect(buildIncidents(exchanges, 1000)).toHaveLength(1)
    })

    it('attemptCount > 1 triggers anomaly', () => {
      const exchanges = [makeExchange(0, { attemptCount: 2 })]
      expect(buildIncidents(exchanges, 1000)).toHaveLength(1)
    })

    it('isTimeout triggers anomaly', () => {
      const exchanges = [makeExchange(0, { isTimeout: true })]
      expect(buildIncidents(exchanges, 1000)).toHaveLength(1)
    })
  })

  describe('region detection', () => {
    it('longest prefix wins — 1.3.6.1.2.1.2.2.1 maps to ifTable not interfaces', () => {
      const exchanges = [makeExchange(0, { rtt: 2000, requestOid: asOid('1.3.6.1.2.1.2.2.1.1') })]
      const incidents = buildIncidents(exchanges, 1000)
      expect(incidents[0]!.region).toBe('ifTable')
    })

    it('unknown OID falls back to first 8 arcs', () => {
      const exchanges = [makeExchange(0, { rtt: 2000, requestOid: asOid('9.9.9.9.9.9.9.9.9.9') })]
      const incidents = buildIncidents(exchanges, 1000)
      expect(incidents[0]!.region).toBe('9.9.9.9.9.9.9.9')
    })
  })
})
