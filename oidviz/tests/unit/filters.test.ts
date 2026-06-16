import { describe, expect, it } from 'bun:test';
import { clusterMatchesFacets, matchesFacets } from '../../src/lib/filters';
import { asOid } from '../../src/lib/model';
import type { DomainExchange, FacetState, Incident } from '../../src/lib/model';

const makeEx = (overrides: Partial<DomainExchange>): DomainExchange => ({
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
});

const DEFAULT_FACET: FacetState = { perf: 'any', corr: 'any', retryOnly: false, slowMs: 1000 };

const makeIncident = (overrides: Partial<Incident> = {}): Incident => ({
  startIdx: 0,
  endIdx: 0,
  startSeq: 1,
  endSeq: 1,
  members: [0],
  peakRtt: 100,
  retryCount: 0,
  timeoutCount: 0,
  violationTypes: new Set(),
  region: 'normal',
  score: 1,
  ...overrides,
});

describe('matchesFacets', () => {
  it('perf: any passes fast, slow, and timeout exchanges', () => {
    const facet: FacetState = { ...DEFAULT_FACET, perf: 'any' };
    expect(matchesFacets(makeEx({ rtt: 100 }), facet)).toBe(true);
    expect(matchesFacets(makeEx({ rtt: 2000 }), facet)).toBe(true);
    expect(matchesFacets(makeEx({ isTimeout: true }), facet)).toBe(true);
  });

  it('perf: slow excludes timeouts and fast exchanges', () => {
    const facet: FacetState = { ...DEFAULT_FACET, perf: 'slow' };
    expect(matchesFacets(makeEx({ rtt: 2000 }), facet)).toBe(true);
    expect(matchesFacets(makeEx({ rtt: 100 }), facet)).toBe(false);
    expect(matchesFacets(makeEx({ isTimeout: true, rtt: 2000 }), facet)).toBe(false);
  });

  it('perf: timeout excludes non-timeout exchanges', () => {
    const facet: FacetState = { ...DEFAULT_FACET, perf: 'timeout' };
    expect(matchesFacets(makeEx({ isTimeout: true }), facet)).toBe(true);
    expect(matchesFacets(makeEx({ rtt: 2000 }), facet)).toBe(false);
    expect(matchesFacets(makeEx({ rtt: 100 }), facet)).toBe(false);
  });

  it('perf: fast includes fast and excludes slow and timeout', () => {
    const facet: FacetState = { ...DEFAULT_FACET, perf: 'fast' };
    expect(matchesFacets(makeEx({ rtt: 100 }), facet)).toBe(true);
    expect(matchesFacets(makeEx({ rtt: 2000 }), facet)).toBe(false);
    expect(matchesFacets(makeEx({ isTimeout: true }), facet)).toBe(false);
  });

  it('corr: violations excludes clean exchanges', () => {
    const facet: FacetState = { ...DEFAULT_FACET, corr: 'violations' };
    expect(matchesFacets(makeEx({ violations: [] }), facet)).toBe(false);
    expect(matchesFacets(makeEx({ violations: ['mismatch'] }), facet)).toBe(true);
  });

  it('retryOnly: true excludes single-attempt exchanges', () => {
    const facet: FacetState = { ...DEFAULT_FACET, retryOnly: true };
    expect(matchesFacets(makeEx({ attemptCount: 1 }), facet)).toBe(false);
    expect(matchesFacets(makeEx({ attemptCount: 2 }), facet)).toBe(true);
  });

  it('all-default facet state passes everything', () => {
    expect(matchesFacets(makeEx({ rtt: 100 }), DEFAULT_FACET)).toBe(true);
    expect(matchesFacets(makeEx({ rtt: 2000 }), DEFAULT_FACET)).toBe(true);
    expect(matchesFacets(makeEx({ isTimeout: true }), DEFAULT_FACET)).toBe(true);
    expect(matchesFacets(makeEx({ violations: ['x'], attemptCount: 3 }), DEFAULT_FACET)).toBe(true);
  });
});

describe('clusterMatchesFacets', () => {
  it('perf: any passes all incident shapes', () => {
    const facet: FacetState = { ...DEFAULT_FACET, perf: 'any' };
    expect(clusterMatchesFacets(makeIncident({ timeoutCount: 1 }), facet)).toBe(true);
    expect(clusterMatchesFacets(makeIncident({ peakRtt: 2000 }), facet)).toBe(true);
    expect(clusterMatchesFacets(makeIncident({ peakRtt: 100 }), facet)).toBe(true);
  });

  it('perf: timeout requires timeoutCount > 0', () => {
    const facet: FacetState = { ...DEFAULT_FACET, perf: 'timeout' };
    expect(clusterMatchesFacets(makeIncident({ timeoutCount: 1 }), facet)).toBe(true);
    expect(clusterMatchesFacets(makeIncident({ timeoutCount: 0, peakRtt: 2000 }), facet)).toBe(false);
  });

  it('perf: slow requires peakRtt > slowMs and no timeouts', () => {
    const facet: FacetState = { ...DEFAULT_FACET, perf: 'slow' };
    expect(clusterMatchesFacets(makeIncident({ peakRtt: 2000, timeoutCount: 0 }), facet)).toBe(true);
    expect(clusterMatchesFacets(makeIncident({ peakRtt: 100, timeoutCount: 0 }), facet)).toBe(false);
    expect(clusterMatchesFacets(makeIncident({ peakRtt: 2000, timeoutCount: 1 }), facet)).toBe(false);
  });

  it('perf: fast requires peakRtt <= slowMs and no timeouts', () => {
    const facet: FacetState = { ...DEFAULT_FACET, perf: 'fast' };
    expect(clusterMatchesFacets(makeIncident({ peakRtt: 100, timeoutCount: 0 }), facet)).toBe(true);
    expect(clusterMatchesFacets(makeIncident({ peakRtt: 2000, timeoutCount: 0 }), facet)).toBe(false);
    expect(clusterMatchesFacets(makeIncident({ peakRtt: 100, timeoutCount: 1 }), facet)).toBe(false);
  });

  it('corr: violations requires violationTypes.size > 0', () => {
    const facet: FacetState = { ...DEFAULT_FACET, corr: 'violations' };
    expect(clusterMatchesFacets(makeIncident({ violationTypes: new Set(['mismatch']) }), facet)).toBe(true);
    expect(clusterMatchesFacets(makeIncident({ violationTypes: new Set() }), facet)).toBe(false);
  });

  it('retryOnly: true requires retryCount > 0', () => {
    const facet: FacetState = { ...DEFAULT_FACET, retryOnly: true };
    expect(clusterMatchesFacets(makeIncident({ retryCount: 0 }), facet)).toBe(false);
    expect(clusterMatchesFacets(makeIncident({ retryCount: 1 }), facet)).toBe(true);
  });

  it('all-default facet state passes all incidents', () => {
    expect(clusterMatchesFacets(makeIncident(), DEFAULT_FACET)).toBe(true);
    expect(clusterMatchesFacets(makeIncident({ timeoutCount: 1 }), DEFAULT_FACET)).toBe(true);
    expect(clusterMatchesFacets(makeIncident({ peakRtt: 2000, violationTypes: new Set(['x']) }), DEFAULT_FACET)).toBe(true);
  });
});
