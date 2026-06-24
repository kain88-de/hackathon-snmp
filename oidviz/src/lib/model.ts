import type { Header, Summary, SystemInfo } from "./types.gen.ts";

export type OidString = string & { readonly _brand: "OidString" };
export function asOid(s: string): OidString {
	return s as OidString;
}

export interface DomainExchange {
	seq: number;
	rtt: number; // ms
	isTimeout: boolean;
	violations: string[]; // open enum per format spec — string[] is correct
	attemptCount: number;
	requestOid: OidString;
	responseOids: OidString[]; // unique, 7-arc-truncated; [] when no response
	sentAtMs: number;
	receivedAtMs: number;
}

export interface ParseResult {
	exchanges: DomainExchange[];
	header: Header;
	summary: Summary | null; // null not absent — exactOptionalPropertyTypes
	systemInfo: SystemInfo | null;
	parseMs: number;
	truncated: boolean;
}

export interface FacetState {
	perf: "any" | "fast" | "slow" | "timeout"; // default 'any'
	corr: "any" | "violations"; // default 'any'
	retryOnly: boolean; // default false
	slowMs: number; // default 1000ms; UI input is seconds
}

export interface Incident {
	startIdx: number;
	endIdx: number;
	startSeq: number;
	endSeq: number;
	members: number[]; // indices into the exchanges array
	peakRtt: number; // ms
	retryCount: number; // sum of (attemptCount - 1) over members
	timeoutCount: number;
	violationTypes: Set<string>; // Set encodes "distinct" — score uses .size
	region: string; // a label, NOT OidString
	score: number;
}

export interface TrieNodeFlags {
	slow: boolean;
	violation: boolean;
	retry: boolean; // timeout absent by construction: no response OIDs
}

export interface TrieNode {
	arc: string; // arc label — plain string, not OidString
	fullOid: OidString;
	name: string | null;
	children: Map<string, TrieNode>;
	leaves: TrieLeaf[];
	expanded: boolean; // intentionally mutable — only mutable domain field
	stats: { count: number; maxRtt: number; violationCount: number };
	flags: TrieNodeFlags; // OR-rolled from children + own leaves
}

export interface TrieLeaf {
	exchange: DomainExchange;
	oid: OidString; // placement path (response OID), not requestOid
	shared: boolean;
}

export type FlatRow =
	| { kind: "node"; depth: number; node: TrieNode }
	| {
			kind: "leaf";
			depth: number;
			exchange: DomainExchange;
			oid: OidString;
			shared: boolean;
	  };

export interface WorkerRequest {
	type: "parse";
	buffer: ArrayBuffer;
}
export type WorkerResponse =
	| { type: "result"; data: ParseResult }
	| { type: "error"; message: string };

export type AppState =
	| { phase: "landing" }
	| { phase: "loading" }
	| { phase: "viewer"; result: ParseResult }
	| { phase: "error"; message: string };

export type ActiveView = "findings" | "incidents" | "minimap" | "oidtree";
