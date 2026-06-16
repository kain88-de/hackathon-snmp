import type { Header, Summary, SystemInfo } from './types.gen';

// Branded nominal type for OID strings
export type OidString = string & { readonly _brand: 'OidString' };
// Single constructor (a cast, not validation — the worker is the only call site)
export function asOid(s: string): OidString {
  return s as OidString;
}

// DomainExchange — enriched form of a schema Exchange with computed fields baked in at parse time
export interface DomainExchange {
  seq: number;
  rtt: number; // ms
  isTimeout: boolean;
  violations: string[];
  attemptCount: number;
  requestOid: OidString;
  responseOids: OidString[]; // unique 7-arc-truncated OIDs from exchange.response?.varbinds
  sentAtMs: number; // exchange.attempts[0].sent_at * 1000
  receivedAtMs: number; // RTT end time in ms
}

// ParseResult — what the worker emits on success
export interface ParseResult {
  exchanges: DomainExchange[];
  header: Header; // from types.gen.ts
  summary: Summary | null;
  systemInfo: SystemInfo | null;
  parseMs: number;
  truncated: boolean;
}

// FilterState — reactive filter state
export interface FilterState {
  slow: boolean; // default true
  violations: boolean; // default true
  retries: boolean; // default true
  timeouts: boolean; // default false
  slowMs: number; // default 1000 (ms; UI inputs are in seconds, converts to ms)
}

// Incident — output of buildIncidents()
export interface Incident {
  startIdx: number;
  endIdx: number;
  startSeq: number;
  endSeq: number;
  members: number[]; // indices into exchanges array
  peakRtt: number; // ms
  retryCount: number; // sum of (attemptCount - 1) over members
  timeoutCount: number;
  violationTypes: Set<string>;
  region: string;
  score: number;
}

// TrieNode — internal node of the OID trie
export interface TrieNode {
  arc: string;
  fullOid: OidString;
  name: string | null;
  children: Map<string, TrieNode>;
  leaves: TrieLeaf[];
  expanded: boolean; // intentionally mutable — only mutable field in domain model
  stats: { count: number; maxRtt: number; violationCount: number };
  severity: 0 | 1 | 2; // 0=ok, 1=slow, 2=violation; propagated upward
}

// TrieLeaf
export interface TrieLeaf {
  exchange: DomainExchange;
  shared: boolean; // true if exchange.responseOids.length > 1
}

// FlatRow — flattened trie for virtualised rendering
export type FlatRow =
  | { kind: 'node'; depth: number; node: TrieNode }
  | { kind: 'leaf'; depth: number; exchange: DomainExchange; shared: boolean };

// Worker message protocol — typed discriminated unions
export type WorkerRequest = { type: 'parse'; buffer: ArrayBuffer };

export type WorkerResponse =
  | { type: 'result'; data: ParseResult }
  | { type: 'error'; message: string };

// Top-level app state machine
export type AppState =
  | { phase: 'landing' }
  | { phase: 'loading' }
  | { phase: 'viewer'; result: ParseResult }
  | { phase: 'error'; message: string };
