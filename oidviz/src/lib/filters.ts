import type { DomainExchange, FilterState, Incident } from './model';

export function matchesFilters(
  ex: Readonly<DomainExchange>,
  state: Readonly<FilterState>,
): boolean {
  const { slow, violations, retries, timeouts } = state;
  if (!slow && !violations && !retries && !timeouts) return true;
  if (slow && ex.rtt > state.slowMs) return true;
  if (violations && ex.violations.length > 0) return true;
  if (retries && ex.attemptCount > 1) return true;
  if (timeouts && ex.isTimeout) return true;
  return false;
}

export function clusterMatchesFilters(
  incident: Readonly<Incident>,
  state: Readonly<FilterState>,
): boolean {
  const { slow, violations, retries, timeouts } = state;
  if (!slow && !violations && !retries && !timeouts) return true;
  if (slow && incident.peakRtt > state.slowMs) return true;
  if (violations && incident.violationTypes.size > 0) return true;
  if (retries && incident.retryCount > 0) return true;
  if (timeouts && incident.timeoutCount > 0) return true;
  return false;
}
