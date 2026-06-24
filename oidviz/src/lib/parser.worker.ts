import {
	type DomainExchange,
	type ParseResult,
	type WorkerRequest,
	type WorkerResponse,
	asOid,
} from "./model.ts";
import type { Exchange, Header, Summary, SystemInfo } from "./types.gen.ts";

const MS_PER_SECOND = 1000;
const OID_TRUNCATE_ARCS = 7;

function readAllChunks(
	readable: ReadableStream<Uint8Array>,
): Promise<Uint8Array[]> {
	const chunks: Uint8Array[] = [];
	const reader = readable.getReader();

	function pump(): Promise<Uint8Array[]> {
		return reader
			.read()
			.then(({ done, value }): Promise<Uint8Array[]> | Uint8Array[] => {
				if (done) {
					reader.releaseLock();
					return chunks;
				}
				chunks.push(value);
				return pump();
			});
	}

	return pump();
}

function decompressGzip(buffer: ArrayBuffer): Promise<string> {
	const ds = new DecompressionStream("gzip");
	const writer = ds.writable.getWriter();

	// CRITICAL: read and write MUST run concurrently to avoid deadlock.
	// Writing to the writable side blocks on backpressure if the readable
	// side is not already being consumed.
	return Promise.all([
		writer
			.write(new Uint8Array(buffer))
			.then((): Promise<void> => writer.close()),
		readAllChunks(ds.readable),
	]).then(([, chunks]): string => {
		const totalLength = chunks.reduce(
			(sum: number, c: Uint8Array): number => sum + c.length,
			0,
		);
		const merged = new Uint8Array(totalLength);
		let offset = 0;
		for (const chunk of chunks) {
			merged.set(chunk, offset);
			offset += chunk.length;
		}
		return new TextDecoder().decode(merged);
	});
}

function truncateOid(oid: string): string {
	return oid.split(".").slice(0, OID_TRUNCATE_ARCS).join(".");
}

function getLastAttempt(exchange: Exchange): Exchange["attempts"][0] {
	// attempts is [first, ...rest[]] — at least one element is guaranteed.
	// We walk to the last element without triggering noUncheckedIndexedAccess.
	let last = exchange.attempts[0];
	for (const attempt of exchange.attempts) {
		last = attempt;
	}
	return last;
}

function mapExchange(exchange: Exchange): DomainExchange {
	const lastAttempt = getLastAttempt(exchange);
	const isTimeout = lastAttempt.received_at === null;

	const sentAtMs = lastAttempt.sent_at * MS_PER_SECOND;
	let receivedAtMs = 0;
	if (lastAttempt.received_at !== null) {
		receivedAtMs = lastAttempt.received_at * MS_PER_SECOND;
	}
	let rtt = 0;
	if (!isTimeout) {
		rtt = receivedAtMs - sentAtMs;
	}

	// responseOids: from exchange.response?.varbinds, unique, 7-arc-truncated
	const responseOids: string[] = [];
	if (exchange.response !== undefined) {
		const seen = new Set<string>();
		for (const varbind of exchange.response.varbinds) {
			const truncated = truncateOid(varbind.oid);
			if (!seen.has(truncated)) {
				seen.add(truncated);
				responseOids.push(truncated);
			}
		}
	}

	return {
		attemptCount: exchange.attempts.length,
		isTimeout,
		receivedAtMs,
		requestOid: asOid(exchange.request.oids[0]),
		responseOids: responseOids.map(asOid),
		rtt,
		sentAtMs,
		seq: exchange.seq,
		violations: exchange.violations ?? [],
	};
}

function parseTrace(buffer: ArrayBuffer): Promise<ParseResult> {
	const t0 = performance.now();

	return decompressGzip(buffer).then((text: string): ParseResult => {
		const lines = text
			.split("\n")
			.filter((l: string): boolean => l.trim().length > 0);

		let header: Header | null = null;
		let summary: Summary | null = null;
		let systemInfo: SystemInfo | null = null;
		const exchanges: DomainExchange[] = [];

		for (const line of lines) {
			const record = JSON.parse(line) as { type: string; [k: string]: unknown };
			switch (record.type) {
				case "header": {
					header = record as unknown as Header;
					break;
				}
				case "system_info": {
					systemInfo = record as unknown as SystemInfo;
					break;
				}
				case "exchange": {
					exchanges.push(mapExchange(record as unknown as Exchange));
					break;
				}
				case "summary": {
					summary = record as unknown as Summary;
					break;
				}
				default:
			}
		}

		if (header === null) {
			throw new Error("Trace file missing header record");
		}

		const parseMs = performance.now() - t0;

		return {
			exchanges,
			header,
			parseMs,
			summary,
			systemInfo,
			truncated: false,
		};
	});
}

self.addEventListener("message", (event: MessageEvent<WorkerRequest>): void => {
	const { type, buffer } = event.data;
	if (type !== "parse") {
		return;
	}

	parseTrace(buffer)
		.then((data: ParseResult): void => {
			const response: WorkerResponse = { data, type: "result" };
			self.postMessage(response);
		})
		.catch((error: unknown): void => {
			let message: string;
			if (error instanceof Error) {
				message = error.message;
			} else {
				message = String(error);
			}
			const response: WorkerResponse = { message, type: "error" };
			self.postMessage(response);
		});
});
