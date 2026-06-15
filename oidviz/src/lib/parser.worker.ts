import type { DomainExchange, OidString, ParseResult, WorkerRequest, WorkerResponse } from './model'
import { asOid } from './model'
import type { Exchange, Header, Summary, SystemInfo, Varbind } from './types.gen'

self.onmessage = (event: MessageEvent<WorkerRequest>) => {
  const req = event.data
  if (req.type === 'parse') {
    parseBuffer(req.buffer)
  }
}

async function parseBuffer(buffer: ArrayBuffer): Promise<void> {
  const t0 = performance.now()

  let header: Header | null = null
  let summary: Summary | null = null
  let systemInfo: SystemInfo | null = null
  const exchanges: DomainExchange[] = []
  let truncated = false

  try {
    const blob = new Blob([buffer])
    const ds = new DecompressionStream('gzip')
    const stream = blob.stream().pipeThrough(ds)
    const reader = stream.getReader()

    const decoder = new TextDecoder('utf-8')
    let leftover = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      const chunk = decoder.decode(value, { stream: true })
      leftover += chunk
      const lines = leftover.split('\n')
      leftover = lines.pop() ?? ''  // last item is incomplete line or ''

      for (const line of lines) {
        if (!line.trim()) continue
        try {
          const rec = JSON.parse(line) as { type: string; [key: string]: unknown }
          processRecord(rec, header, systemInfo, summary, exchanges, (h) => { header = h }, (si) => { systemInfo = si }, (s) => { summary = s })
        } catch {
          // ignore malformed lines
        }
      }
    }

    // Handle remaining leftover
    if (leftover.trim()) {
      truncated = true
      // try to parse what we have anyway
      try {
        const rec = JSON.parse(leftover) as { type: string; [key: string]: unknown }
        processRecord(rec, header, systemInfo, summary, exchanges, (h) => { header = h }, (si) => { systemInfo = si }, (s) => { summary = s })
      } catch {
        // ignore malformed partial line
      }
    }
  } catch (err) {
    // gzip decompression failed — not a valid gzip file
    const response: WorkerResponse = { type: 'error', message: String(err) }
    self.postMessage(response)
    return
  }

  if (header === null) {
    const response: WorkerResponse = { type: 'error', message: 'No header record found' }
    self.postMessage(response)
    return
  }

  const parseMs = performance.now() - t0
  const result: ParseResult = {
    exchanges,
    header, // format spec guarantees header is first record
    summary,
    systemInfo,
    parseMs,
    truncated,
  }
  const response: WorkerResponse = { type: 'result', data: result }
  self.postMessage(response)
}

function processRecord(
  rec: { type: string; [key: string]: unknown },
  header: Header | null,
  _systemInfo: SystemInfo | null,
  _summary: Summary | null,
  exchanges: DomainExchange[],
  setHeader: (h: Header) => void,
  setSystemInfo: (si: SystemInfo) => void,
  setSummary: (s: Summary) => void,
): void {
  switch (rec.type) {
    case 'header':
      setHeader(rec as unknown as Header)
      break
    case 'system_info': {
      const si = rec as unknown as SystemInfo
      if (si.point === 'start') {
        setSystemInfo(si)
      }
      break
    }
    case 'exchange': {
      const raw = rec as unknown as Exchange
      const timeoutS = header?.settings.timeout_s ?? 2.0
      exchanges.push(enrichExchange(raw, timeoutS))
      break
    }
    case 'summary':
      setSummary(rec as unknown as Summary) // last occurrence wins
      break
    case 'event':
      // silently skip
      break
    default:
      // unknown type — silently skip
      break
  }
}

function enrichExchange(raw: Exchange, timeoutS: number): DomainExchange {
  const attempts = raw.attempts
  // format spec guarantees minItems: 1 — safe to index without null check
  // biome-ignore lint/style/noNonNullAssertion: format spec guarantees minItems: 1
  const first = attempts[0]!
  // biome-ignore lint/style/noNonNullAssertion: format spec guarantees minItems: 1
  const last = attempts[attempts.length - 1]!

  const isTimeout = last.received_at === null

  // RTT: (last.received_at - first.sent_at) * 1000
  // If last attempt timed out, use (last.sent_at + timeout_s - first.sent_at) * 1000
  const receivedAtSec: number = isTimeout
    ? last.sent_at + timeoutS
    : (last.received_at ?? (last.sent_at + timeoutS))
  const rtt = (receivedAtSec - first.sent_at) * 1000
  const receivedAtMs = receivedAtSec * 1000
  const sentAtMs = first.sent_at * 1000

  // responseOids: unique 7-arc-truncated OIDs from response varbinds
  const responseOids = truncateAndDeduplicateOids(raw.response?.varbinds ?? [])

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
  }
}

function truncateOid(oid: string): string {
  // Take first 7 arc components
  return oid.split('.').slice(0, 7).join('.')
}

function truncateAndDeduplicateOids(varbinds: Array<Varbind>): OidString[] {
  const seen = new Set<string>()
  const result: OidString[] = []
  for (const vb of varbinds) {
    const truncated = truncateOid(vb.oid)
    if (!seen.has(truncated)) {
      seen.add(truncated)
      result.push(asOid(truncated))
    }
  }
  return result
}
