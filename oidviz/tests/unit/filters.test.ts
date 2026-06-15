import { describe, expect, it } from 'bun:test'
import { matchesFilters, clusterMatchesFilters } from '../../src/lib/filters'
import { asOid } from '../../src/lib/model'
import type { DomainExchange, FilterState, Incident } from '../../src/lib/model'

function makeExchange(overrides: Partial<DomainExchange>): DomainExchange {
  return {
    seq: 1,
    rtt: 100,
    isTimeout: false,
    violations: [],
    attemptCount: 1,
    requestOid: asOid('1.3.6.1'),
    responseOids: [],
    sentAtMs: 0,
    receivedAtMs: 100,
    ...overrides,
  }
}

function makeIncident(overrides: Partial<Incident>): Incident {
  return {
    startIdx: 0,
    endIdx: 0,
    startSeq: 1,
    endSeq: 1,
    members: [0],
    peakRtt: 100,
    retryCount: 0,
    timeoutCount: 0,
    violationTypes: new Set(),
    region: 'system',
    score: 1,
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

describe('matchesFilters', () => {
  it('all flags false → always returns true', () => {
    const ex = makeExchange({ rtt: 5000, violations: ['err'], attemptCount: 5, isTimeout: true })
    expect(matchesFilters(ex, makeState())).toBe(true)
  })

  describe('slow flag', () => {
    it('rtt > slowMs → true', () => {
      const ex = makeExchange({ rtt: 1001 })
      expect(matchesFilters(ex, makeState({ slow: true, slowMs: 1000 }))).toBe(true)
    })

    it('rtt === slowMs → false', () => {
      const ex = makeExchange({ rtt: 1000 })
      expect(matchesFilters(ex, makeState({ slow: true, slowMs: 1000 }))).toBe(false)
    })

    it('rtt < slowMs → false', () => {
      const ex = makeExchange({ rtt: 999 })
      expect(matchesFilters(ex, makeState({ slow: true, slowMs: 1000 }))).toBe(false)
    })
  })

  describe('violations flag', () => {
    it('non-empty violations → true', () => {
      const ex = makeExchange({ violations: ['oid-mismatch'] })
      expect(matchesFilters(ex, makeState({ violations: true }))).toBe(true)
    })

    it('empty violations → false', () => {
      const ex = makeExchange({ violations: [] })
      expect(matchesFilters(ex, makeState({ violations: true }))).toBe(false)
    })
  })

  describe('retries flag', () => {
    it('attemptCount > 1 → true', () => {
      const ex = makeExchange({ attemptCount: 2 })
      expect(matchesFilters(ex, makeState({ retries: true }))).toBe(true)
    })

    it('attemptCount === 1 → false', () => {
      const ex = makeExchange({ attemptCount: 1 })
      expect(matchesFilters(ex, makeState({ retries: true }))).toBe(false)
    })
  })

  describe('timeouts flag', () => {
    it('isTimeout true → true', () => {
      const ex = makeExchange({ isTimeout: true })
      expect(matchesFilters(ex, makeState({ timeouts: true }))).toBe(true)
    })

    it('isTimeout false → false', () => {
      const ex = makeExchange({ isTimeout: false })
      expect(matchesFilters(ex, makeState({ timeouts: true }))).toBe(false)
    })
  })

  describe('OR composition', () => {
    it('matches one of multiple active flags → true', () => {
      // slow and retries active, exchange is only slow
      const ex = makeExchange({ rtt: 2000, attemptCount: 1 })
      expect(matchesFilters(ex, makeState({ slow: true, retries: true, slowMs: 1000 }))).toBe(true)
    })

    it('matches none of multiple active flags → false', () => {
      const ex = makeExchange({ rtt: 100, attemptCount: 1 })
      expect(matchesFilters(ex, makeState({ slow: true, retries: true, slowMs: 1000 }))).toBe(false)
    })

    it('all four flags active, exchange matches violations only → true', () => {
      const ex = makeExchange({ violations: ['err'] })
      expect(matchesFilters(ex, makeState({ slow: true, violations: true, retries: true, timeouts: true }))).toBe(true)
    })

    it('all four flags active, exchange matches none → false', () => {
      const ex = makeExchange({ rtt: 100, violations: [], attemptCount: 1, isTimeout: false })
      expect(matchesFilters(ex, makeState({ slow: true, violations: true, retries: true, timeouts: true, slowMs: 1000 }))).toBe(false)
    })
  })
})

describe('clusterMatchesFilters', () => {
  it('all flags false → always returns true', () => {
    const inc = makeIncident({ peakRtt: 9999, violationTypes: new Set(['x']), retryCount: 5, timeoutCount: 3 })
    expect(clusterMatchesFilters(inc, makeState())).toBe(true)
  })

  describe('slow flag', () => {
    it('peakRtt > slowMs → true', () => {
      const inc = makeIncident({ peakRtt: 1500 })
      expect(clusterMatchesFilters(inc, makeState({ slow: true, slowMs: 1000 }))).toBe(true)
    })

    it('peakRtt === slowMs → false', () => {
      const inc = makeIncident({ peakRtt: 1000 })
      expect(clusterMatchesFilters(inc, makeState({ slow: true, slowMs: 1000 }))).toBe(false)
    })

    it('peakRtt < slowMs → false', () => {
      const inc = makeIncident({ peakRtt: 500 })
      expect(clusterMatchesFilters(inc, makeState({ slow: true, slowMs: 1000 }))).toBe(false)
    })
  })

  describe('violations flag', () => {
    it('violationTypes non-empty → true', () => {
      const inc = makeIncident({ violationTypes: new Set(['oid-mismatch']) })
      expect(clusterMatchesFilters(inc, makeState({ violations: true }))).toBe(true)
    })

    it('violationTypes empty → false', () => {
      const inc = makeIncident({ violationTypes: new Set<string>() })
      expect(clusterMatchesFilters(inc, makeState({ violations: true }))).toBe(false)
    })
  })

  describe('retries flag', () => {
    it('retryCount > 0 → true', () => {
      const inc = makeIncident({ retryCount: 3 })
      expect(clusterMatchesFilters(inc, makeState({ retries: true }))).toBe(true)
    })

    it('retryCount === 0 → false', () => {
      const inc = makeIncident({ retryCount: 0 })
      expect(clusterMatchesFilters(inc, makeState({ retries: true }))).toBe(false)
    })
  })

  describe('timeouts flag', () => {
    it('timeoutCount > 0 → true', () => {
      const inc = makeIncident({ timeoutCount: 1 })
      expect(clusterMatchesFilters(inc, makeState({ timeouts: true }))).toBe(true)
    })

    it('timeoutCount === 0 → false', () => {
      const inc = makeIncident({ timeoutCount: 0 })
      expect(clusterMatchesFilters(inc, makeState({ timeouts: true }))).toBe(false)
    })
  })

  describe('OR composition', () => {
    it('matches one of multiple active flags → true', () => {
      // slow and timeouts active, only timeouts matches
      const inc = makeIncident({ peakRtt: 100, timeoutCount: 2 })
      expect(clusterMatchesFilters(inc, makeState({ slow: true, timeouts: true, slowMs: 1000 }))).toBe(true)
    })

    it('matches none of multiple active flags → false', () => {
      const inc = makeIncident({ peakRtt: 100, retryCount: 0 })
      expect(clusterMatchesFilters(inc, makeState({ slow: true, retries: true, slowMs: 1000 }))).toBe(false)
    })

    it('all four flags active, incident matches retries only → true', () => {
      const inc = makeIncident({ peakRtt: 100, retryCount: 2, timeoutCount: 0, violationTypes: new Set() })
      expect(clusterMatchesFilters(inc, makeState({ slow: true, violations: true, retries: true, timeouts: true, slowMs: 1000 }))).toBe(true)
    })

    it('all four flags active, incident matches none → false', () => {
      const inc = makeIncident({ peakRtt: 100, retryCount: 0, timeoutCount: 0, violationTypes: new Set() })
      expect(clusterMatchesFilters(inc, makeState({ slow: true, violations: true, retries: true, timeouts: true, slowMs: 1000 }))).toBe(false)
    })
  })
})
