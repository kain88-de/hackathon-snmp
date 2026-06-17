import type { DomainExchange, FacetState, Incident } from './model.ts';

const NONE = 0;
const SINGLE_ATTEMPT = 1;

export const matchesFacets = (
  ex: Readonly<DomainExchange>,
  state: Readonly<FacetState>,
): boolean => {
  const perfOk =
    state.perf === 'any' ||
    (state.perf === 'fast' && !ex.isTimeout && ex.rtt <= state.slowMs) ||
    (state.perf === 'slow' && !ex.isTimeout && ex.rtt > state.slowMs) ||
    (state.perf === 'timeout' && ex.isTimeout);

  const corrOk = state.corr === 'any' || ex.violations.length > NONE;
  const retryOk = !state.retryOnly || ex.attemptCount > SINGLE_ATTEMPT;

  return perfOk && corrOk && retryOk;
};

export const clusterMatchesFacets = (
  incident: Readonly<Incident>,
  state: Readonly<FacetState>,
): boolean => {
  const perfOk =
    state.perf === 'any' ||
    (state.perf === 'timeout' && incident.timeoutCount > NONE) ||
    (state.perf === 'slow' && incident.peakRtt > state.slowMs && incident.timeoutCount === NONE) ||
    (state.perf === 'fast' && incident.peakRtt <= state.slowMs && incident.timeoutCount === NONE);

  const corrOk = state.corr === 'any' || incident.violationTypes.size > NONE;
  const retryOk = !state.retryOnly || incident.retryCount > NONE;

  return perfOk && corrOk && retryOk;
};
