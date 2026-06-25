import type { DomainExchange, FacetState } from "./model.ts";

function perfMatchesExchange(
	ex: Readonly<DomainExchange>,
	state: Readonly<FacetState>,
): boolean {
	if (state.perf === "any") {
		return true;
	}
	if (state.perf === "timeout") {
		return ex.isTimeout;
	}
	if (state.perf === "fast") {
		return !ex.isTimeout && ex.rtt <= state.slowMs;
	}
	// slow
	return !ex.isTimeout && ex.rtt > state.slowMs;
}

export function matchesFacets(
	ex: Readonly<DomainExchange>,
	state: Readonly<FacetState>,
): boolean {
	if (!perfMatchesExchange(ex, state)) {
		return false;
	}
	if (state.corr === "violations" && ex.violations.length === 0) {
		return false;
	}
	if (state.retryOnly && ex.attemptCount <= 1) {
		return false;
	}
	return true;
}
