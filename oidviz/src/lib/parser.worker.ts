import {
  asOid,
  type DomainExchange,
  type ParseResult,
  type WorkerRequest,
  type WorkerResponse,
} from './model';
import type { Exchange, Header, Summary, SystemInfo } from './types.gen';

const DEFAULT_TIMEOUT_S = 2;
const MS_PER_S = 1000;
const MAX_OID_ARCS = 7;
const FIRST_IDX = 0;
const LAST_IDX = -1;
const ZERO = 0;

interface ParseState {
  exchanges: DomainExchange[];
  header: Header | null;
  summary: Summary | null;
  systemInfo: SystemInfo | null;
}

const buildFallbackExchange = (exchange: Exchange): DomainExchange => ({
  attemptCount: ZERO,
  isTimeout: false,
  receivedAtMs: ZERO,
  requestOid: asOid(exchange.request.oids[FIRST_IDX]),
  responseOids: [],
  rtt: ZERO,
  sentAtMs: ZERO,
  seq: exchange.seq,
  violations: [],
});

const computeResponseOids = (exchange: Exchange): ReturnType<typeof asOid>[] => {
  if (!exchange.response) {
    return [];
  }
  const seenOids = new Set<string>();
  const responseOids: ReturnType<typeof asOid>[] = [];
  for (const varbind of exchange.response.varbinds) {
    const truncated = varbind.oid.split('.').slice(FIRST_IDX, MAX_OID_ARCS).join('.');
    if (!seenOids.has(truncated)) {
      seenOids.add(truncated);
      responseOids.push(asOid(truncated));
    }
  }
  return responseOids;
};

interface RttFields {
  isTimeout: boolean;
  receivedAtMs: number;
  rtt: number;
  sentAtMs: number;
}

const computeRttTimeout = (sentAt: number, timeoutS: number, firstSentAt: number): RttFields => ({
  isTimeout: true,
  receivedAtMs: (sentAt + timeoutS) * MS_PER_S,
  rtt: (sentAt + timeoutS - firstSentAt) * MS_PER_S,
  sentAtMs: firstSentAt * MS_PER_S,
});

const computeRttSuccess = (receivedAt: number, firstSentAt: number): RttFields => ({
  isTimeout: false,
  receivedAtMs: receivedAt * MS_PER_S,
  rtt: (receivedAt - firstSentAt) * MS_PER_S,
  sentAtMs: firstSentAt * MS_PER_S,
});

const computeRttFields = (exchange: Exchange, timeoutS: number): RttFields => {
  const [firstAttempt] = exchange.attempts;
  const lastAttempt = exchange.attempts.at(LAST_IDX) ?? firstAttempt;
  if (lastAttempt.received_at === null) {
    return computeRttTimeout(lastAttempt.sent_at, timeoutS, firstAttempt.sent_at);
  }
  return computeRttSuccess(lastAttempt.received_at, firstAttempt.sent_at);
};

const enrichExchange = (exchange: Exchange, timeoutS: number): DomainExchange => {
  const [firstAttempt] = exchange.attempts;
  if (!firstAttempt) {
    return buildFallbackExchange(exchange);
  }
  const rttFields = computeRttFields(exchange, timeoutS);
  return {
    attemptCount: exchange.attempts.length,
    isTimeout: rttFields.isTimeout,
    receivedAtMs: rttFields.receivedAtMs,
    requestOid: asOid(exchange.request.oids[FIRST_IDX]),
    responseOids: computeResponseOids(exchange),
    rtt: rttFields.rtt,
    sentAtMs: rttFields.sentAtMs,
    seq: exchange.seq,
    violations: exchange.violations ?? [],
  };
};

const dispatchRecord = (rec: { type: unknown }, state: ParseState, timeoutS: number): void => {
  if (rec.type === 'header') {
    state.header = rec as Header;
  } else if (rec.type === 'system_info') {
    const sysInfo = rec as SystemInfo;
    if (sysInfo.point === 'start') {
      state.systemInfo = sysInfo;
    }
  } else if (rec.type === 'exchange') {
    state.exchanges.push(enrichExchange(rec as Exchange, timeoutS));
  } else if (rec.type === 'summary') {
    state.summary = rec as Summary;
  }
};

const tryParseRecord = (line: string): { type: unknown } | null => {
  try {
    const parsed: unknown = JSON.parse(line);
    if (typeof parsed !== 'object' || parsed === null || !('type' in parsed)) {
      return null;
    }
    return parsed as { type: unknown };
  } catch {
    return null;
  }
};

const parseLine = (line: string, state: ParseState, timeoutS: number): void => {
  const rec = tryParseRecord(line);
  if (rec !== null) {
    dispatchRecord(rec, state, timeoutS);
  }
};

const getTimeoutS = (state: ParseState): number => {
  if (state.header === null) {
    return DEFAULT_TIMEOUT_S;
  }
  return state.header.settings.timeout_s;
};

interface ChunkState {
  decoder: TextDecoder;
  parseState: ParseState;
  remainder: string;
  truncated: boolean;
}

const processChunk = (chunk: Uint8Array, cs: ChunkState): void => {
  const text = cs.decoder.decode(chunk, { stream: true });
  const lines = (cs.remainder + text).split('\n');
  cs.remainder = lines.pop() ?? '';
  const timeoutS = getTimeoutS(cs.parseState);
  for (const line of lines) {
    if (line.trim() !== '') {
      parseLine(line, cs.parseState, timeoutS);
    }
  }
};

const finalizeDecoder = (cs: ChunkState): void => {
  const final = cs.decoder.decode();
  if (final !== '') {
    cs.remainder += final;
  }
  if (cs.remainder.trim() === '') {
    return;
  }
  cs.truncated = true;
  const timeoutS = getTimeoutS(cs.parseState);
  try {
    parseLine(cs.remainder, cs.parseState, timeoutS);
  } catch {
    // Ignore errors on partial trailing line
  }
};

const readAllChunks = (
  reader: ReadableStreamDefaultReader<Uint8Array>,
  cs: ChunkState,
): Promise<void> => {
  const step = (): Promise<void> =>
    reader.read().then(({ done, value }) => {
      if (done) {
        return;
      }
      if (value) {
        processChunk(value, cs);
      }
      return step();
    });
  return step();
};

const buildResult = (cs: ChunkState, parseMs: number): ParseResult | null => {
  if (cs.parseState.header === null) {
    return null;
  }
  return {
    exchanges: cs.parseState.exchanges,
    header: cs.parseState.header,
    parseMs,
    summary: cs.parseState.summary,
    systemInfo: cs.parseState.systemInfo,
    truncated: cs.truncated,
  };
};

const parseBuffer = (buffer: ArrayBuffer): Promise<void> => {
  const startTime = performance.now();
  const stream = new DecompressionStream('gzip');
  const writer = stream.writable.getWriter();
  const reader = stream.readable.getReader();

  const cs: ChunkState = {
    decoder: new TextDecoder('utf-8'),
    parseState: { exchanges: [], header: null, summary: null, systemInfo: null },
    remainder: '',
    truncated: false,
  };

  return writer
    .write(new Uint8Array(buffer))
    .then(() => writer.close())
    .then(() => readAllChunks(reader, cs))
    .then(() => {
      finalizeDecoder(cs);
      const result = buildResult(cs, performance.now() - startTime);
      if (result === null) {
        const response: WorkerResponse = {
          message: 'No header record found in trace file',
          type: 'error',
        };
        globalThis.postMessage(response, globalThis.location.origin);
        return;
      }
      const successResponse: WorkerResponse = { data: result, type: 'result' };
      globalThis.postMessage(successResponse, globalThis.location.origin);
    });
};

const postError = (message: string): void => {
  const response: WorkerResponse = { message, type: 'error' };
  globalThis.postMessage(response, globalThis.location.origin);
};

const handleError = (error: unknown): void => {
  if (error instanceof Error) {
    postError(error.message);
    return;
  }
  postError(String(error));
};

globalThis.addEventListener('message', (event: MessageEvent<WorkerRequest>) => {
  const { buffer } = event.data;
  parseBuffer(buffer).catch(handleError);
});
