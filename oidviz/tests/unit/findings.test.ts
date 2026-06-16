import { describe, expect, it } from 'bun:test';
import { categorise } from '../../src/lib/findings';
import { asOid } from '../../src/lib/model';
import type { DomainExchange } from '../../src/lib/model';

const makeEx = (
  seq: number,
  rtt: number,
  isTimeout = false,
  violations: string[] = [],
): DomainExchange => ({
  seq,
  rtt,
  isTimeout,
  violations,
  attemptCount: 1,
  requestOid: asOid('1.3.6.1'),
  responseOids: [],
  sentAtMs: 0,
  receivedAtMs: rtt,
});

const SLOW_MS = 1000;

describe('categorise', () => {
  it('empty input returns three empty arrays', () => {
    const result = categorise([], SLOW_MS);
    expect(result.slow).toEqual([]);
    expect(result.timeout).toEqual([]);
    expect(result.fast).toEqual([]);
  });

  it('slow partition: includes !isTimeout && rtt > slowMs, sorted RTT desc', () => {
    const exA = makeEx(1, 1500);
    const exB = makeEx(2, 3000);
    const exC = makeEx(3, 500);
    const result = categorise([exA, exB, exC], SLOW_MS);
    expect(result.slow).toEqual([exB, exA]);
    expect(result.timeout).toEqual([]);
    expect(result.fast).toEqual([exC]);
  });

  it('timeout partition: includes isTimeout exchanges, sorted seq asc', () => {
    const exA = makeEx(5, 0, true);
    const exB = makeEx(2, 0, true);
    const exC = makeEx(8, 0, true);
    const result = categorise([exA, exB, exC], SLOW_MS);
    expect(result.timeout).toEqual([exB, exA, exC]);
    expect(result.slow).toEqual([]);
    expect(result.fast).toEqual([]);
  });

  it('fast partition: includes !isTimeout && rtt <= slowMs, sorted violation count desc then RTT asc', () => {
    const exA = makeEx(1, 200, false, ['a', 'b']);
    const exB = makeEx(2, 100, false, ['a', 'b', 'c']);
    const exC = makeEx(3, 300, false, ['a']);
    const exD = makeEx(4, 50, false, []);
    const result = categorise([exA, exB, exC, exD], SLOW_MS);
    expect(result.fast).toEqual([exB, exA, exC, exD]);
    expect(result.slow).toEqual([]);
    expect(result.timeout).toEqual([]);
  });

  it('mutual exclusion: each exchange appears in exactly one partition', () => {
    const exSlow = makeEx(1, 2000);
    const exTimeout = makeEx(2, 0, true);
    const exFast = makeEx(3, 500);
    const result = categorise([exSlow, exTimeout, exFast], SLOW_MS);
    const all = [...result.slow, ...result.timeout, ...result.fast];
    expect(all).toHaveLength(3);
    expect(result.slow).toContain(exSlow);
    expect(result.timeout).toContain(exTimeout);
    expect(result.fast).toContain(exFast);
  });

  it('boundary case: rtt === slowMs goes to fast, not slow', () => {
    const exExact = makeEx(1, SLOW_MS);
    const result = categorise([exExact], SLOW_MS);
    expect(result.fast).toContain(exExact);
    expect(result.slow).toEqual([]);
    expect(result.timeout).toEqual([]);
  });

  it('fast sort: higher violation count before lower; same violation count, lower RTT first', () => {
    const exHighViolLowRtt = makeEx(1, 100, false, ['a', 'b']);
    const exHighViolHighRtt = makeEx(2, 900, false, ['a', 'b']);
    const exLowViolLowRtt = makeEx(3, 50, false, ['a']);
    const exLowViolHighRtt = makeEx(4, 800, false, ['a']);
    const exNoViol = makeEx(5, 200, false, []);

    const result = categorise(
      [exNoViol, exLowViolHighRtt, exHighViolHighRtt, exLowViolLowRtt, exHighViolLowRtt],
      SLOW_MS,
    );

    expect(result.fast).toEqual([
      exHighViolLowRtt,
      exHighViolHighRtt,
      exLowViolLowRtt,
      exLowViolHighRtt,
      exNoViol,
    ]);
  });
});
