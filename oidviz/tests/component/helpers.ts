// Synthetic-data factories shared by the component test suites (tests/component/*.test.ts).
// Each factory takes an optional partial-overrides argument — same pattern as the
// `makeExchange` helper duplicated across tests/unit/*.test.ts.

import { asOid } from "../../src/lib/model.ts";
import type {
	DomainExchange,
	FacetState,
	ParseResult,
	TrieNode,
} from "../../src/lib/model.ts";
import type { Header } from "../../src/lib/types.gen.ts";

export function makeExchange(overrides: Partial<DomainExchange> = {}): DomainExchange {
	return {
		seq: 1,
		rtt: 100,
		isTimeout: false,
		violations: [],
		attemptCount: 1,
		requestOid: asOid("1.3.6.1"),
		responseOids: [],
		sentAtMs: 0,
		receivedAtMs: 100,
		...overrides,
	};
}

export function makeFacetState(overrides: Partial<FacetState> = {}): FacetState {
	return {
		perf: "any",
		corr: "any",
		retryOnly: false,
		slowMs: 1000,
		...overrides,
	};
}

export function makeHeader(overrides: Partial<Header> = {}): Header {
	return {
		type: "header",
		format_version: 1,
		tool: "oidtrace 0.1.0",
		started_at: "2026-06-11T14:03:07Z",
		session: { id: "5e1f3a9c-6a86-4a0b-9b6e-2f6d6a9c1d42", run: 1, runs_total: 1 },
		snmp: { version: "2c" },
		settings: {
			bulk_size: 10,
			timeout_s: 2,
			retries: 1,
			start_oid: "1.3.6.1",
		},
		...overrides,
	};
}

export function makeParseResult(overrides: Partial<ParseResult> = {}): ParseResult {
	return {
		exchanges: [],
		header: makeHeader(),
		summary: null,
		systemInfo: null,
		parseMs: 0,
		truncated: false,
		...overrides,
	};
}

export function makeTrieNode(overrides: Partial<TrieNode> = {}): TrieNode {
	return {
		arc: "1",
		fullOid: asOid("1"),
		name: null,
		description: null,
		children: new Map(),
		leaves: [],
		expanded: false,
		stats: { count: 0, maxRtt: 0, violationCount: 0 },
		flags: { slow: false, violation: false, retry: false },
		...overrides,
	};
}
