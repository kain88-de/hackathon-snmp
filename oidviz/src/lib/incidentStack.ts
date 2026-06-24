import type { DomainExchange, Incident, OidString } from "./model.ts";
import { asOid } from "./model.ts";
import { lookupOidName } from "./oidNames.ts";

const GAP_MERGE_MAX = 8;
const SCORE_VIOLATION_BONUS = 1000;
const SCORE_RETRY_FACTOR = 100;
const SCORE_TIMEOUT_FACTOR = 500;
const OID_PREFIX_ARC_COUNT = 3;

function isAnomalous(ex: DomainExchange, slowMs: number): boolean {
	return ex.isTimeout || ex.rtt > slowMs || ex.violations.length > 0;
}

function oidPrefix3(oid: OidString): string {
	const arcs = oid.split(".");
	return arcs.slice(0, OID_PREFIX_ARC_COUNT).join(".");
}

function computeRegion(
	members: number[],
	exchanges: readonly DomainExchange[],
): string {
	if (members.length === 0) {
		return "Unknown";
	}

	const freq = new Map<string, number>();
	for (const idx of members) {
		const ex = exchanges[idx];
		if (ex !== undefined) {
			const oid = ex.requestOid;
			freq.set(oid, (freq.get(oid) ?? 0) + 1);
		}
	}

	let bestOid: OidString = asOid("");
	let bestCount = 0;
	for (const [oid, count] of freq) {
		if (count > bestCount) {
			bestCount = count;
			bestOid = asOid(oid);
		}
	}

	const name = lookupOidName(bestOid);
	if (name !== null) {
		return name;
	}
	return oidPrefix3(bestOid);
}

interface IncidentWindow {
	endIdx: number;
	members: number[];
	startIdx: number;
}

interface MemberStats {
	peakRtt: number;
	retryCount: number;
	timeoutCount: number;
	violationTypes: Set<string>;
}

function computeMemberStats(
	members: number[],
	exchanges: readonly DomainExchange[],
): MemberStats {
	let peakRtt = 0;
	let retryCount = 0;
	let timeoutCount = 0;
	const violationTypes = new Set<string>();

	for (const idx of members) {
		const ex = exchanges[idx];
		if (ex !== undefined) {
			if (ex.rtt > peakRtt) {
				peakRtt = ex.rtt;
			}
			retryCount += ex.attemptCount - 1;
			if (ex.isTimeout) {
				timeoutCount += 1;
			}
			for (const v of ex.violations) {
				violationTypes.add(v);
			}
		}
	}

	return { peakRtt, retryCount, timeoutCount, violationTypes };
}

function windowToIncident(
	w: IncidentWindow,
	exchanges: readonly DomainExchange[],
): Incident {
	const stats = computeMemberStats(w.members, exchanges);
	const region = computeRegion(w.members, exchanges);

	const firstMember = w.members[0];
	const lastMember = w.members[w.members.length - 1];
	let firstEx: DomainExchange | undefined;
	if (firstMember !== undefined) {
		firstEx = exchanges[firstMember];
	}
	let lastEx: DomainExchange | undefined;
	if (lastMember !== undefined) {
		lastEx = exchanges[lastMember];
	}

	let violationBonus = 0;
	if (stats.violationTypes.size > 0) {
		violationBonus = SCORE_VIOLATION_BONUS;
	}
	const score =
		violationBonus +
		stats.peakRtt +
		stats.retryCount * SCORE_RETRY_FACTOR +
		stats.timeoutCount * SCORE_TIMEOUT_FACTOR;

	return {
		endIdx: w.endIdx,
		endSeq: lastEx?.seq ?? 0,
		members: w.members,
		peakRtt: stats.peakRtt,
		region,
		retryCount: stats.retryCount,
		score,
		startIdx: w.startIdx,
		startSeq: firstEx?.seq ?? 0,
		timeoutCount: stats.timeoutCount,
		violationTypes: stats.violationTypes,
	};
}

export function buildIncidents(
	exchanges: readonly DomainExchange[],
	slowMs: number,
): Incident[] {
	if (exchanges.length === 0) {
		return [];
	}

	const windows: IncidentWindow[] = [];
	let currentWindow: IncidentWindow | null = null;
	let lastAnomalousIdx = -1;

	for (let i = 0; i < exchanges.length; i += 1) {
		const ex = exchanges[i];
		if (ex === undefined || !isAnomalous(ex, slowMs)) {
			// Not anomalous — skip; gap is tracked by index arithmetic
		} else if (currentWindow === null) {
			currentWindow = { endIdx: i, members: [i], startIdx: i };
			lastAnomalousIdx = i;
		} else {
			const gap = i - lastAnomalousIdx - 1;
			if (gap <= GAP_MERGE_MAX) {
				currentWindow.endIdx = i;
				currentWindow.members.push(i);
				lastAnomalousIdx = i;
			} else {
				windows.push(currentWindow);
				currentWindow = { endIdx: i, members: [i], startIdx: i };
				lastAnomalousIdx = i;
			}
		}
	}

	if (currentWindow !== null) {
		windows.push(currentWindow);
	}

	const incidents: Incident[] = windows.map(
		(w): Incident => windowToIncident(w, exchanges),
	);

	incidents.sort((a, b): number => b.score - a.score);

	return incidents;
}
