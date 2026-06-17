import type { DomainExchange } from './model.ts';

export interface Findings {
  fast: DomainExchange[];
  slow: DomainExchange[];
  timeout: DomainExchange[];
}

const NO_DIFFERENCE = 0;

const sortSlow = (alpha: DomainExchange, beta: DomainExchange): number => beta.rtt - alpha.rtt;

const sortTimeout = (alpha: DomainExchange, beta: DomainExchange): number => alpha.seq - beta.seq;

const sortFast = (alpha: DomainExchange, beta: DomainExchange): number => {
  const byViolations = beta.violations.length - alpha.violations.length;
  if (byViolations !== NO_DIFFERENCE) {
    return byViolations;
  }
  return alpha.rtt - beta.rtt;
};

interface Buckets {
  fast: DomainExchange[];
  slow: DomainExchange[];
  timeout: DomainExchange[];
}

const partition = (exchanges: readonly DomainExchange[], slowMs: number): Buckets => {
  const slow: DomainExchange[] = [];
  const timeout: DomainExchange[] = [];
  const fast: DomainExchange[] = [];
  for (const ex of exchanges) {
    if (ex.isTimeout) {
      timeout.push(ex);
    } else if (ex.rtt > slowMs) {
      slow.push(ex);
    } else {
      fast.push(ex);
    }
  }
  return { fast, slow, timeout };
};

export const categorise = (exchanges: readonly DomainExchange[], slowMs: number): Findings => {
  const buckets = partition(exchanges, slowMs);
  buckets.slow.sort(sortSlow);
  buckets.timeout.sort(sortTimeout);
  buckets.fast.sort(sortFast);
  return buckets;
};
