import type { DomainExchange, FacetState, Incident } from "./model.ts";

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

function perfMatchesIncident(
	incident: Readonly<Incident>,
	state: Readonly<FacetState>,
): boolean {
	if (state.perf === "any") {
		return true;
	}
	if (state.perf === "timeout") {
		return incident.timeoutCount > 0;
	}
	if (state.perf === "fast") {
		return incident.peakRtt <= state.slowMs && incident.timeoutCount === 0;
	}
	// slow
	return incident.peakRtt > state.slowMs;
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

export function clusterMatchesFacets(
	incident: Readonly<Incident>,
	state: Readonly<FacetState>,
): boolean {
	if (!perfMatchesIncident(incident, state)) {
		return false;
	}
	if (state.corr === "violations" && incident.violationTypes.size === 0) {
		return false;
	}
	if (state.retryOnly && incident.retryCount === 0) {
		return false;
	}
	return true;
}
