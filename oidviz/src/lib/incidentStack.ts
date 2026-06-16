import type { DomainExchange, Incident } from './model.ts';

const GAP_WINDOW = 8;
const TIMEOUT_WEIGHT = 100;
const VIOL_TYPE_WEIGHT = 50;
const RETRY_WEIGHT = 10;
const LOG_RTT_WEIGHT = 5;
const MEMBER_WEIGHT = 0.1;
const SINGLE_REGION_DEPTH = 5;
const LOG_RTT_MIN = 1;
const NO_ATTEMPTS = 1;
const EMPTY_LENGTH = 0;
const INITIAL_MATCH = 0;
const STEP = 1;
const TIMEOUT_INCREMENT = 1;

const isAnomalous = (exchange: DomainExchange, slowMs: number): boolean =>
  exchange.rtt > slowMs ||
  exchange.violations.length > EMPTY_LENGTH ||
  exchange.attemptCount > NO_ATTEMPTS ||
  exchange.isTimeout;

const computeCommonLength = (firstArcs: string[], otherArcs: string[], maxLen: number): number => {
  let matchLen = INITIAL_MATCH;
  while (
    matchLen < maxLen &&
    matchLen < otherArcs.length &&
    otherArcs[matchLen] === firstArcs[matchLen]
  ) {
    matchLen += STEP;
  }
  return matchLen;
};

const dominantRegion = (oids: string[]): string => {
  if (oids.length === EMPTY_LENGTH) {
    return '';
  }
  const arcArrays = oids.map((oid) => oid.split('.'));
  const firstArcs = arcArrays[EMPTY_LENGTH];
  if (!firstArcs) {
    return '';
  }
  let commonLength = firstArcs.length;
  for (const arcs of arcArrays.slice(STEP)) {
    commonLength = computeCommonLength(firstArcs, arcs, commonLength);
  }
  return firstArcs.slice(EMPTY_LENGTH, commonLength).join('.');
};

const getRegionSingle = (oid: string): string =>
  oid.split('.').slice(EMPTY_LENGTH, SINGLE_REGION_DEPTH).join('.');

const getRegion = (oids: string[]): string => {
  if (oids.length === STEP) {
    const firstOid = oids[EMPTY_LENGTH];
    if (!firstOid) {
      return '';
    }
    return getRegionSingle(firstOid);
  }
  return dominantRegion(oids);
};

interface ClusterAccumulator {
  memberIndices: number[];
  memberOids: string[];
  memberSeqs: number[];
  peakRtt: number;
  retryCount: number;
  timeoutCount: number;
  violationTypes: Set<string>;
}

interface ScoreInputs {
  memberCount: number;
  peakRtt: number;
  retryCount: number;
  timeoutCount: number;
  violationTypes: Set<string>;
}

const computeScore = (inputs: ScoreInputs): number =>
  TIMEOUT_WEIGHT * inputs.timeoutCount +
  VIOL_TYPE_WEIGHT * inputs.violationTypes.size +
  RETRY_WEIGHT * inputs.retryCount +
  LOG_RTT_WEIGHT * Math.log10(Math.max(inputs.peakRtt, LOG_RTT_MIN)) +
  MEMBER_WEIGHT * inputs.memberCount;

const getSeq = (exchanges: readonly DomainExchange[], idx: number): number => {
  const ex = exchanges[idx];
  if (!ex) {
    return EMPTY_LENGTH;
  }
  return ex.seq;
};

interface ClusterBounds {
  startIdx: number;
  endIdx: number;
  startSeq: number;
  endSeq: number;
}

const getClusterBounds = (
  acc: ClusterAccumulator,
  exchanges: readonly DomainExchange[],
): ClusterBounds => {
  const startIdx = acc.memberIndices[EMPTY_LENGTH] ?? EMPTY_LENGTH;
  const endIdx = acc.memberIndices[acc.memberIndices.length - STEP] ?? EMPTY_LENGTH;
  return {
    endIdx,
    endSeq: getSeq(exchanges, endIdx),
    startIdx,
    startSeq: getSeq(exchanges, startIdx),
  };
};

const buildCluster = (acc: ClusterAccumulator, exchanges: readonly DomainExchange[]): Incident => {
  const region = getRegion(acc.memberOids);
  const score = computeScore({
    memberCount: acc.memberIndices.length,
    peakRtt: acc.peakRtt,
    retryCount: acc.retryCount,
    timeoutCount: acc.timeoutCount,
    violationTypes: acc.violationTypes,
  });
  const { endIdx, endSeq, startIdx, startSeq } = getClusterBounds(acc, exchanges);
  return {
    endIdx,
    endSeq,
    members: [...acc.memberIndices],
    peakRtt: acc.peakRtt,
    region,
    retryCount: acc.retryCount,
    score,
    startIdx,
    startSeq,
    timeoutCount: acc.timeoutCount,
    violationTypes: new Set(acc.violationTypes),
  };
};

const initialTimeoutCount = (isTimeout: boolean): number => {
  if (isTimeout) {
    return TIMEOUT_INCREMENT;
  }
  return EMPTY_LENGTH;
};

const makeAccumulator = (exchange: DomainExchange, index: number): ClusterAccumulator => ({
  memberIndices: [index],
  memberOids: [exchange.requestOid],
  memberSeqs: [exchange.seq],
  peakRtt: exchange.rtt,
  retryCount: exchange.attemptCount - NO_ATTEMPTS,
  timeoutCount: initialTimeoutCount(exchange.isTimeout),
  violationTypes: new Set(exchange.violations),
});

const updatePeakRtt = (acc: ClusterAccumulator, rtt: number): void => {
  if (rtt > acc.peakRtt) {
    acc.peakRtt = rtt;
  }
};

const addToAccumulator = (
  acc: ClusterAccumulator,
  exchange: DomainExchange,
  index: number,
): void => {
  acc.memberIndices.push(index);
  acc.memberOids.push(exchange.requestOid);
  acc.memberSeqs.push(exchange.seq);
  updatePeakRtt(acc, exchange.rtt);
  acc.retryCount += exchange.attemptCount - NO_ATTEMPTS;
  if (exchange.isTimeout) {
    acc.timeoutCount += TIMEOUT_INCREMENT;
  }
  for (const violation of exchange.violations) {
    acc.violationTypes.add(violation);
  }
};

const shouldStartNewCluster = (gap: number, currentRegion: string, prevRegion: string): boolean =>
  gap > GAP_WINDOW && currentRegion !== prevRegion;

interface AnomalousEntry {
  exchange: DomainExchange;
  index: number;
}

const collectAnomalous = (
  exchanges: readonly DomainExchange[],
  slowMs: number,
): AnomalousEntry[] => {
  const anomalous: AnomalousEntry[] = [];
  for (const [idx, exchange] of exchanges.entries()) {
    if (isAnomalous(exchange, slowMs)) {
      anomalous.push({ exchange, index: idx });
    }
  }
  return anomalous;
};

const needsNewCluster = (acc: ClusterAccumulator, item: AnomalousEntry): boolean => {
  const lastSeqIdx = acc.memberSeqs.length - STEP;
  const prevSeq = acc.memberSeqs[lastSeqIdx] ?? EMPTY_LENGTH;
  const gap = item.exchange.seq - prevSeq - STEP;
  const currentRegion = getRegion([item.exchange.requestOid]);
  const lastOidIdx = acc.memberOids.length - STEP;
  const lastOid = acc.memberOids[lastOidIdx] ?? '';
  const prevRegion = getRegion([lastOid]);
  return shouldStartNewCluster(gap, currentRegion, prevRegion);
};

const processAnomalousEntries = (
  anomalous: AnomalousEntry[],
  firstAcc: ClusterAccumulator,
): ClusterAccumulator[] => {
  let currentAcc = firstAcc;
  const accumulators: ClusterAccumulator[] = [];
  for (const item of anomalous.slice(STEP)) {
    if (needsNewCluster(currentAcc, item)) {
      accumulators.push(currentAcc);
      currentAcc = makeAccumulator(item.exchange, item.index);
    } else {
      addToAccumulator(currentAcc, item.exchange, item.index);
    }
  }
  accumulators.push(currentAcc);
  return accumulators;
};

const clusterAnomalous = (anomalous: AnomalousEntry[]): ClusterAccumulator[] => {
  const firstEntry = anomalous[EMPTY_LENGTH];
  if (!firstEntry) {
    return [];
  }
  const firstAcc = makeAccumulator(firstEntry.exchange, firstEntry.index);
  return processAnomalousEntries(anomalous, firstAcc);
};

export const buildIncidents = (
  exchanges: readonly DomainExchange[],
  slowMs: number,
): Incident[] => {
  const anomalous = collectAnomalous(exchanges, slowMs);
  if (anomalous.length === EMPTY_LENGTH) {
    return [];
  }
  const accumulators = clusterAnomalous(anomalous);
  return accumulators.map((acc) => buildCluster(acc, exchanges));
};
