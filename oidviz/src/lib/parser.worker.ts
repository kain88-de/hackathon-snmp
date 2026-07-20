import {
	type DomainExchange,
	type ParseResult,
	type WorkerRequest,
	type WorkerResponse,
	asOid,
} from "./model.ts";
import type {
	Exchange,
	Header,
	Summary,
	SystemInfo,
	Varbind,
} from "./types.gen.ts";

const MS_PER_SECOND = 1000;
const OID_TRUNCATE_ARCS = 7;

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
		// SNMPv3 discovery exchanges carry no OID (oids: []); empty string reads as "none".
		requestOid: asOid(exchange.request.oids[0] ?? ""),
		responseOids: responseOids.map(asOid),
		rtt,
		sentAtMs,
		seq: exchange.seq,
		violations: exchange.violations ?? [],
	};
}

function isRecordObject(value: unknown): value is Record<string, unknown> {
	return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function isValidHeader(
	record: Record<string, unknown>,
): record is Header {
	const session = record.session;
	const snmp = record.snmp;
	const settings = record.settings;
	return (
		record.format_version === 1 &&
		typeof record.tool === "string" &&
		typeof record.started_at === "string" &&
		isRecordObject(session) &&
		typeof session.id === "string" &&
		typeof session.run === "number" &&
		typeof session.runs_total === "number" &&
		isRecordObject(snmp) &&
		typeof snmp.version === "string" &&
		isRecordObject(settings) &&
		typeof settings.bulk_size === "number" &&
		typeof settings.timeout_s === "number" &&
		typeof settings.retries === "number" &&
		typeof settings.start_oid === "string"
	);
}

export function isValidSystemInfo(
	record: Record<string, unknown>,
): record is SystemInfo {
	return (
		typeof record.at === "number" &&
		(record.point === "start" || record.point === "end") &&
		isRecordObject(record.values)
	);
}

function isValidExchangeRequest(
	request: unknown,
): request is Exchange["request"] {
	return (
		isRecordObject(request) &&
		typeof request.pdu === "string" &&
		typeof request.request_id === "number" &&
		Array.isArray(request.oids)
	);
}

function isValidAttempt(attempt: unknown): boolean {
	return (
		isRecordObject(attempt) &&
		typeof attempt.sent_at === "number" &&
		(attempt.received_at === null || typeof attempt.received_at === "number")
	);
}

function isValidVarbind(varbind: unknown): varbind is Varbind {
	return isRecordObject(varbind) && typeof varbind.oid === "string";
}

function isValidResponse(
	response: unknown,
): response is NonNullable<Exchange["response"]> {
	return (
		isRecordObject(response) &&
		typeof response.request_id === "number" &&
		typeof response.error_status === "number" &&
		typeof response.error_index === "number" &&
		Array.isArray(response.varbinds) &&
		response.varbinds.every(isValidVarbind)
	);
}

export function isValidExchange(
	record: Record<string, unknown>,
): record is Exchange {
	const attempts = record.attempts;
	if (
		typeof record.seq !== "number" ||
		!isValidExchangeRequest(record.request) ||
		!Array.isArray(attempts) ||
		attempts.length === 0 ||
		!attempts.every(isValidAttempt)
	) {
		return false;
	}
	const response = record.response;
	if (response !== undefined && !isValidResponse(response)) {
		return false;
	}
	const violations = record.violations;
	if (violations !== undefined && !Array.isArray(violations)) {
		return false;
	}
	return true;
}

export function isValidSummary(
	record: Record<string, unknown>,
): record is Summary {
	return (
		typeof record.at === "number" &&
		typeof record.exchanges === "number" &&
		typeof record.oids_seen === "number" &&
		typeof record.end_reason === "string" &&
		isRecordObject(record.violation_counts)
	);
}

export function parseTrace(buffer: ArrayBuffer): Promise<ParseResult> {
	const t0 = performance.now();

	let header: Header | null = null;
	let summary: Summary | null = null;
	let systemInfo: SystemInfo | null = null;
	const exchanges: DomainExchange[] = [];
	let truncated = false;

	// Validates one already-parsed record against its declared type and, if
	// valid, assigns it into the locals above. Returns false (record shape
	// does not match its type) or true (assigned, or an unhandled type that
	// is silently ignored per spec).
	function applyRecord(record: Record<string, unknown>): boolean {
		switch (record.type) {
			case "header": {
				if (!isValidHeader(record)) {
					return false;
				}
				header = record;
				return true;
			}
			case "system_info": {
				if (!isValidSystemInfo(record)) {
					return false;
				}
				systemInfo = record;
				return true;
			}
			case "exchange": {
				if (!isValidExchange(record)) {
					return false;
				}
				exchanges.push(mapExchange(record));
				return true;
			}
			case "summary": {
				if (!isValidSummary(record)) {
					return false;
				}
				summary = record;
				return true;
			}
			default: {
				return true;
			}
		}
	}

	// Parses one JSON line and dispatches it via applyRecord. Returns false
	// when the line fails to parse or fails shape validation (and sets
	// truncated = true), true otherwise.
	function handleLine(line: string): boolean {
		if (line.trim().length === 0) {
			return true;
		}
		let parsed: unknown;
		try {
			parsed = JSON.parse(line);
		} catch {
			truncated = true;
			return false;
		}
		if (!isRecordObject(parsed) || typeof parsed.type !== "string") {
			truncated = true;
			return false;
		}
		if (!applyRecord(parsed)) {
			truncated = true;
			return false;
		}
		return true;
	}

	const ds = new DecompressionStream("gzip");
	const writer = ds.writable.getWriter();
	const reader = ds.readable.getReader();
	const decoder = new TextDecoder();

	// Set synchronously with reader.cancel() below, in the same tick, so the
	// writer's rejection handler can never race ahead of it: by the time the
	// self-inflicted write error reaches .catch, stopped is already true.
	let stopped = false;

	let leftover = "";

	function pump(): Promise<void> {
		return reader.read().then(({ done, value }): Promise<void> | void => {
			if (done) {
				const finalLine = leftover + decoder.decode();
				handleLine(finalLine);
				return;
			}
			const chunk = leftover + decoder.decode(value, { stream: true });
			const parts = chunk.split("\n");
			leftover = parts.pop() ?? "";
			for (const line of parts) {
				if (!handleLine(line)) {
					stopped = true;
					reader.cancel();
					return;
				}
			}
			return pump();
		});
	}

	// CRITICAL: read and write MUST run concurrently to avoid deadlock.
	// Writing to the writable side blocks on backpressure if the readable
	// side is not already being consumed.
	return Promise.all([
		writer
			.write(new Uint8Array(buffer))
			.then((): Promise<void> => writer.close())
			.catch((error: unknown): void => {
				// Cancelling the readable side also errors the writable side.
				// Swallow that self-inflicted error; anything else (e.g. the
				// not-gzip fixture) is a genuine decompression failure and
				// must propagate.
				if (!stopped) {
					throw error;
				}
			}),
		pump(),
	]).then((): ParseResult => {
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
			truncated,
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
