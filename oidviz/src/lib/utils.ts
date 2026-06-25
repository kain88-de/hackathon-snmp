import type { DomainExchange } from "./model.ts";

export function minMaxValues(arr: number[]): [number, number] {
	let max = Number.NEGATIVE_INFINITY;
	let min = Number.POSITIVE_INFINITY;
	for (const v of arr) {
		if (v < min) {
			min = v;
		}
		if (v > max) {
			max = v;
		}
	}
	return [min, max];
}

export function rttCssClass(ex: DomainExchange, slowMs: number): string {
	if (ex.isTimeout) {
		return "dim-timeout";
	}
	if (ex.rtt > slowMs) {
		return "dim-slow";
	}
	return "dim-fast";
}

export function rttCssClassFromRtt(rtt: number, slowMs: number): string {
	if (rtt > slowMs) {
		return "dim-slow";
	}
	return "dim-fast";
}
