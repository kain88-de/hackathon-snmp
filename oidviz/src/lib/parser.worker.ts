import type {
  DomainExchange,
  OidString,
  ParseResult,
  WorkerRequest,
  WorkerResponse,
} from './model';
import { asOid } from './model';
import type {
  Exchange,
  Header,
  Summary,
  SystemInfo,
  Varbind,
} from './types.gen';

self.addEventListener('message', (event: MessageEvent<WorkerRequest>) => {
  const req = event.data;
  if (req.type === 'parse') {
    parseBuffer(req.buffer);
  }
});

function parseLine(line: string, ctx: ParseContext): void {
  if (!line.trim()) {
    return;
  }
  try {
    const rec = JSON.parse(line) as { type: string; [key: string]: unknown };
    processRecord(rec, ctx);
  } catch {
    // ignore malformed lines
  }
}

// eslint-disable-next-line no-async-await -- streaming gzip decompression requires async/await
async function parseBuffer(buffer: ArrayBuffer): Promise<void> {
  const t0 = performance.now();

  let header: Header | null = null;
  let summary: Summary | null = null;
  let systemInfo: SystemInfo | null = null;
  const exchanges: DomainExchange[] = [];
  let truncated = false;

  const ctx: ParseContext = {
    exchanges,
    get header() {
      return header;
    },
    setHeader: (h) => {
      header = h;
    },
    setSystemInfo: (si) => {
      systemInfo = si;
    },
    setSummary: (s) => {
      summary = s;
    },
  };

  try {
    const blob = new Blob([buffer]);
    const ds = new DecompressionStream('gzip');
    const stream = blob.stream().pipeThrough(ds);
    const reader = stream.getReader();

    const decoder = new TextDecoder('utf8');
    let leftover = '';

    while (true) {
      // eslint-disable-next-line no-await-in-loop -- streaming read must be sequential
      const { done, value } = await reader.read();
      if (done) {
        break;
      }
      leftover += decoder.decode(value, { stream: true });
      const lines = leftover.split('\n');
      leftover = lines.pop() ?? ''; // last item is incomplete line or ''
      for (const line of lines) {
        parseLine(line, ctx);
      }
    }

    // Handle remaining leftover
    if (leftover.trim()) {
      truncated = true;
      parseLine(leftover, ctx); // try to parse partial last line
    }
  } catch (error) {
    // gzip decompression failed — not a valid gzip file
    const response: WorkerResponse = { type: 'error', message: String(error) };
    self.postMessage(response);
    return;
  }

  if (header === null) {
    const response: WorkerResponse = {
      type: 'error',
      message: 'No header record found',
    };
    self.postMessage(response);
    return;
  }

  const parseMs = performance.now() - t0;
  const result: ParseResult = {
    exchanges,
    header, // format spec guarantees header is first record
    summary,
    systemInfo,
    parseMs,
    truncated,
  };
  const response: WorkerResponse = { type: 'result', data: result };
  self.postMessage(response);
}

const DEFAULT_TIMEOUT_S = 2;

interface ParseContext {
  exchanges: DomainExchange[];
  header: Header | null;
  setHeader: (h: Header) => void;
  setSystemInfo: (si: SystemInfo) => void;
  setSummary: (s: Summary) => void;
}

function processRecord(
  rec: { type: string; [key: string]: unknown },
  ctx: ParseContext,
): void {
  switch (rec.type) {
    case 'header': {
      ctx.setHeader(rec as unknown as Header);
      break;
    }
    case 'system_info': {
      const si = rec as unknown as SystemInfo;
      if (si.point === 'start') {
        ctx.setSystemInfo(si);
      }
      break;
    }
    case 'exchange': {
      const raw = rec as unknown as Exchange;
      const timeoutS = ctx.header?.settings.timeout_s ?? DEFAULT_TIMEOUT_S;
      ctx.exchanges.push(enrichExchange(raw, timeoutS));
      break;
    }
    case 'summary': {
      ctx.setSummary(rec as unknown as Summary); // last occurrence wins
      break;
    }
    default: // silently skip events and unknown types
  }
}

const MS_PER_S = 1000;
const OID_TRUNCATE_ARCS = 7;
const LAST_INDEX = -1;

function enrichExchange(raw: Exchange, timeoutS: number): DomainExchange {
  const attempts = raw.attempts;
  // format spec guarantees minItems: 1 — tuple type ensures attempts[0] is always defined
  const first = attempts[0];
  // at(LAST_INDEX) is safe: tuple guarantees at least one element
  const last = attempts.at(LAST_INDEX) ?? first;

  const isTimeout = last.received_at === null;

  // RTT: (last.received_at - first.sent_at) * 1000
  // If last attempt timed out, use (last.sent_at + timeout_s - first.sent_at) * 1000
  const receivedAtSec: number = isTimeout
    ? last.sent_at + timeoutS
    : (last.received_at ?? last.sent_at + timeoutS);
  const rtt = (receivedAtSec - first.sent_at) * MS_PER_S;
  const receivedAtMs = receivedAtSec * MS_PER_S;
  const sentAtMs = first.sent_at * MS_PER_S;

  // responseOids: unique 7-arc-truncated OIDs from response varbinds
  const responseOids = truncateAndDeduplicateOids(raw.response?.varbinds ?? []);

  return {
    seq: raw.seq,
    rtt,
    isTimeout,
    violations: raw.violations ?? [],
    attemptCount: attempts.length,
    requestOid: asOid(raw.request.oids[0] ?? ''),
    responseOids,
    sentAtMs,
    receivedAtMs,
  };
}

function truncateOid(oid: string): string {
  // Take first OID_TRUNCATE_ARCS arc components
  return oid.split('.').slice(0, OID_TRUNCATE_ARCS).join('.');
}

function truncateAndDeduplicateOids(varbinds: Varbind[]): OidString[] {
  const seen = new Set<string>();
  const result: OidString[] = [];
  for (const vb of varbinds) {
    const truncated = truncateOid(vb.oid);
    if (!seen.has(truncated)) {
      seen.add(truncated);
      result.push(asOid(truncated));
    }
  }
  return result;
}
