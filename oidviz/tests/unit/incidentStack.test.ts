import { describe, expect, it } from 'bun:test';
import { buildIncidents } from '../../src/lib/incidentStack';
import { asOid } from '../../src/lib/model';
import type { DomainExchange } from '../../src/lib/model';

const SLOW_MS = 1000;

const makeEx = (
  seq: number,
  rtt: number,
  requestOid = '1.3.6.1.2.1',
  violations: string[] = [],
  attemptCount = 1,
  isTimeout = false,
): DomainExchange => ({
  seq,
  rtt,
  isTimeout,
  violations,
  attemptCount,
  requestOid: asOid(requestOid),
  responseOids: [],
  sentAtMs: seq * 1000,
  receivedAtMs: seq * 1000 + rtt,
});

describe('buildIncidents', () => {
  it('empty input returns empty array', () => {
    expect(buildIncidents([], SLOW_MS)).toEqual([]);
  });

  it('non-anomalous exchanges produce no incidents', () => {
    const normal = makeEx(1, 500);
    const alsoNormal = makeEx(2, 800);
    expect(buildIncidents([normal, alsoNormal], SLOW_MS)).toEqual([]);
  });

  it('single anomaly creates one incident with one member', () => {
    const slowEx = makeEx(1, 2000);
    const incidents = buildIncidents([slowEx], SLOW_MS);
    expect(incidents).toHaveLength(1);
    const first = incidents.at(0);
    expect(first?.members).toEqual([0]);
    expect(first?.peakRtt).toBe(2000);
  });

  it('gap boundary: gap of exactly 8 merges into the same cluster', () => {
    // seq diff = 10 → gap = 10 - 1 - 1 = 8 → merges (≤ 8)
    const exFirst = makeEx(1, 2000);
    const exSecond = makeEx(10, 2000);
    const incidents = buildIncidents([exFirst, exSecond], SLOW_MS);
    expect(incidents).toHaveLength(1);
    expect(incidents.at(0)?.members).toHaveLength(2);
  });

  it('gap boundary: gap of 9 with different region creates a new cluster', () => {
    // seq diff = 11 → gap = 11 - 1 - 1 = 9 → splits (> 8), different region confirms split
    const exFirst = makeEx(1, 2000, '1.3.6.1.2.1');
    const exSecond = makeEx(11, 2000, '1.3.6.1.4.1');
    const incidents = buildIncidents([exFirst, exSecond], SLOW_MS);
    expect(incidents).toHaveLength(2);
  });

  it('region-based merge: same region merges even with gap > 8', () => {
    const exFirst = makeEx(1, 2000, '1.3.6.1.2.1');
    const exSecond = makeEx(17, 2000, '1.3.6.1.2.1');
    const incidents = buildIncidents([exFirst, exSecond], SLOW_MS);
    expect(incidents).toHaveLength(1);
    expect(incidents.at(0)?.members).toHaveLength(2);
  });

  it('region-based merge: different regions with gap > 8 split into separate clusters', () => {
    const exFirst = makeEx(1, 2000, '1.3.6.1.2.1');
    const exSecond = makeEx(20, 2000, '1.3.6.1.4.1');
    const incidents = buildIncidents([exFirst, exSecond], SLOW_MS);
    expect(incidents).toHaveLength(2);
  });

  it('retryCount is sum of (attemptCount - 1), not count of exchanges with retries', () => {
    const exRetry2 = makeEx(1, 2000, '1.3.6.1.2.1', [], 3);
    const exRetry1 = makeEx(2, 2000, '1.3.6.1.2.1', [], 2);
    const incidents = buildIncidents([exRetry2, exRetry1], SLOW_MS);
    expect(incidents).toHaveLength(1);
    expect(incidents.at(0)?.retryCount).toBe(3);
  });

  it('score calculation matches formula with known inputs', () => {
    const exTimeout = makeEx(1, 0, '1.3.6.1.2.1', ['typeErr'], 1, true);
    const exSlow = makeEx(2, 10000, '1.3.6.1.2.1', ['typeErr', 'mismatch'], 3, false);
    const incidents = buildIncidents([exTimeout, exSlow], SLOW_MS);
    expect(incidents).toHaveLength(1);

    const inc = incidents.at(0);
    expect(inc?.timeoutCount).toBe(1);
    expect(inc?.violationTypes.size).toBe(2);
    expect(inc?.retryCount).toBe(2);
    expect(inc?.peakRtt).toBe(10000);
    expect(inc?.members).toHaveLength(2);

    const expectedScore =
      100 * 1 +
      50 * 2 +
      10 * 2 +
      5 * Math.log10(Math.max(10000, 1)) +
      0.1 * 2;
    expect(inc?.score).toBeCloseTo(expectedScore, 10);
  });

  it('violationTypes deduplicates across members', () => {
    const exAlpha = makeEx(1, 2000, '1.3.6.1.2.1', ['typeErr', 'mismatch']);
    const exBeta = makeEx(2, 2000, '1.3.6.1.2.1', ['typeErr']);
    const incidents = buildIncidents([exAlpha, exBeta], SLOW_MS);
    expect(incidents.at(0)?.violationTypes).toEqual(new Set(['typeErr', 'mismatch']));
  });

  it('startSeq and endSeq reflect the actual seq values of first and last members', () => {
    const exFirst = makeEx(5, 2000);
    const exSecond = makeEx(8, 2000);
    const incidents = buildIncidents([exFirst, exSecond], SLOW_MS);
    const first = incidents.at(0);
    expect(first?.startSeq).toBe(5);
    expect(first?.endSeq).toBe(8);
  });

  it('anomaly detection: isTimeout marks exchange as anomalous', () => {
    const timedOut = makeEx(1, 0, '1.3.6.1.2.1', [], 1, true);
    const incidents = buildIncidents([timedOut], SLOW_MS);
    expect(incidents).toHaveLength(1);
    expect(incidents.at(0)?.timeoutCount).toBe(1);
  });

  it('anomaly detection: violations marks exchange as anomalous', () => {
    const withViolation = makeEx(1, 100, '1.3.6.1.2.1', ['mismatch']);
    const incidents = buildIncidents([withViolation], SLOW_MS);
    expect(incidents).toHaveLength(1);
  });

  it('anomaly detection: attemptCount > 1 marks exchange as anomalous', () => {
    const withRetry = makeEx(1, 100, '1.3.6.1.2.1', [], 2);
    const incidents = buildIncidents([withRetry], SLOW_MS);
    expect(incidents).toHaveLength(1);
  });

  it('non-anomalous exchanges are excluded from all clusters', () => {
    const normal = makeEx(2, 500);
    const anomalous = makeEx(1, 2000);
    const alsoAnomalous = makeEx(3, 2000);
    const incidents = buildIncidents([anomalous, normal, alsoAnomalous], SLOW_MS);
    expect(incidents).toHaveLength(1);
    expect(incidents.at(0)?.members).toEqual([0, 2]);
  });
});
