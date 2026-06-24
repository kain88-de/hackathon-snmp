import type { DomainExchange } from "./model.ts";

export interface Findings {
	slow: DomainExchange[]; // !isTimeout && rtt > slowMs, sorted RTT desc
	timeout: DomainExchange[]; // isTimeout, sorted seq asc
	fast: DomainExchange[]; // !isTimeout && rtt <= slowMs, sorted violation count desc then RTT desc
}

export function categorise(
	exchanges: readonly DomainExchange[],
	slowMs: number,
): Findings {
	const slow: DomainExchange[] = [];
	const timeout: DomainExchange[] = [];
	const fast: DomainExchange[] = [];

	for (const ex of exchanges) {
		if (ex.isTimeout) {
			timeout.push(ex);
		} else if (ex.rtt > slowMs) {
			slow.push(ex);
		} else {
			fast.push(ex);
		}
	}

	slow.sort((a, b): number => b.rtt - a.rtt);
	timeout.sort((a, b): number => a.seq - b.seq);
	fast.sort(
		(a, b): number =>
			b.violations.length - a.violations.length || b.rtt - a.rtt,
	);

	return { fast, slow, timeout };
}
