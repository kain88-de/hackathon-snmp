import type { Header, Summary, SystemInfo } from './types.gen.ts';

export type OidString = string & { readonly _brand: 'OidString' };
export const asOid = (oidStr: string): OidString => oidStr as OidString;

export interface DomainExchange {
  seq: number;
  rtt: number;
  isTimeout: boolean;
  violations: string[];
  attemptCount: number;
  requestOid: OidString;
  responseOids: OidString[];
  sentAtMs: number;
  receivedAtMs: number;
}

export interface ParseResult {
  exchanges: DomainExchange[];
  header: Header;
  summary: Summary | null;
  systemInfo: SystemInfo | null;
  parseMs: number;
  truncated: boolean;
}

export interface FacetState {
  perf: 'any' | 'fast' | 'slow' | 'timeout';
  corr: 'any' | 'violations';
  retryOnly: boolean;
  slowMs: number;
}

export interface Incident {
  startIdx: number;
  endIdx: number;
  startSeq: number;
  endSeq: number;
  members: number[];
  peakRtt: number;
  retryCount: number;
  timeoutCount: number;
  violationTypes: Set<string>;
  region: string;
  score: number;
}

export interface TrieNodeFlags {
  slow: boolean;
  violation: boolean;
  retry: boolean;
}

export interface TrieNode {
  arc: string;
  fullOid: OidString;
  name: string | null;
  children: Map<string, TrieNode>;
  leaves: TrieLeaf[];
  // Intentionally mutable — only mutable domain field
  expanded: boolean;
  stats: { count: number; maxRtt: number; violationCount: number };
  flags: TrieNodeFlags;
}

export interface TrieLeaf {
  exchange: DomainExchange;
  oid: OidString;
  shared: boolean;
}

export type FlatRow =
  | { kind: 'node'; depth: number; node: TrieNode }
  | { kind: 'leaf'; depth: number; exchange: DomainExchange; oid: OidString; shared: boolean };

export interface WorkerRequest {
  type: 'parse';
  buffer: ArrayBuffer;
}
export type WorkerResponse =
  | { type: 'result'; data: ParseResult }
  | { type: 'error'; message: string };

export type AppState =
  | { phase: 'landing' }
  | { phase: 'loading' }
  | { phase: 'viewer'; result: ParseResult }
  | { phase: 'error'; message: string };

export type ActiveView = 'findings' | 'incidents' | 'minimap' | 'oidtree';
