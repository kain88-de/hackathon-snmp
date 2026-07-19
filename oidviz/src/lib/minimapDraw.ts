import type { DomainExchange } from "./model.ts";
import { minMaxValues } from "./utils.ts";

// Layout constants shared with MinimapDetail.vue
export const MINI_H = 80;
export const MAX_H = 32_767;
export const AUTOFOCUS_WINDOW_FRACTION = 0.05;

// Layout constants also needed by MinimapDetail for hit-testing
export const MT = 24;
export const RH = 9;
export const RG = 3;

const ML = 64;
const BH = 6;

const CANVAS_CENTER_DIVISOR = 2;
const PIXEL_OFFSET = 0.5;
const DETAIL_BOTTOM_PADDING = 20;
const MINIMAP_BAR_Y_DIVISOR = 2;
const ML_LABEL_OFFSET = 4;
const MIN_BAR_W = 3;
const VIOLATION_SCORE_BONUS = 1e9;
const RTT_SCORE_SCALE = 1000;

export function exchangeColour(
	ex: DomainExchange,
	slowMs: number,
	style: CSSStyleDeclaration,
): string {
	if (ex.isTimeout) {
		return style.getPropertyValue("--dim-timeout").trim();
	}
	if (ex.violations.length > 0) {
		return style.getPropertyValue("--dim-violation").trim();
	}
	if (ex.rtt > slowMs) {
		return style.getPropertyValue("--dim-slow").trim();
	}
	if (ex.attemptCount > 1) {
		return style.getPropertyValue("--dim-retry").trim();
	}
	return style.getPropertyValue("--dim-none").trim();
}

export function bucketColour(
	bucket: DomainExchange[],
	slowMs: number,
	style: CSSStyleDeclaration,
): string {
	let hasViolation = false;
	let hasSlow = false;
	let hasRetry = false;
	for (const ex of bucket) {
		if (ex.isTimeout) {
			return style.getPropertyValue("--dim-timeout").trim();
		}
		if (ex.violations.length > 0) {
			hasViolation = true;
		} else if (ex.rtt > slowMs) {
			hasSlow = true;
		} else if (ex.attemptCount > 1) {
			hasRetry = true;
		}
	}
	if (hasViolation) {
		return style.getPropertyValue("--dim-violation").trim();
	}
	if (hasSlow) {
		return style.getPropertyValue("--dim-slow").trim();
	}
	if (hasRetry) {
		return style.getPropertyValue("--dim-retry").trim();
	}
	return style.getPropertyValue("--dim-none").trim();
}

export function bucketScore(bucket: DomainExchange[]): number {
	if (bucket.length === 0) {
		return 0;
	}
	const hasViolation = bucket.some((ex): boolean => ex.violations.length > 0);
	let maxRtt = Number.NEGATIVE_INFINITY;
	for (const ex of bucket) {
		if (ex.rtt > maxRtt) {
			maxRtt = ex.rtt;
		}
	}
	let violationBonus = 0;
	if (hasViolation) {
		violationBonus = VIOLATION_SCORE_BONUS;
	}
	return violationBonus + maxRtt * RTT_SCORE_SCALE + bucket.length;
}

export function worstBucketStatus(
	bucket: DomainExchange[],
	slowMs: number,
): string {
	for (const ex of bucket) {
		if (ex.isTimeout) {
			return "Timeout";
		}
	}
	for (const ex of bucket) {
		if (ex.violations.length > 0) {
			return "Violation";
		}
	}
	for (const ex of bucket) {
		if (ex.rtt > slowMs) {
			return "Slow";
		}
	}
	for (const ex of bucket) {
		if (ex.attemptCount > 1) {
			return "Retry";
		}
	}
	return "Normal";
}

export function exchangeStatus(ex: DomainExchange, slowMs: number): string {
	if (ex.isTimeout) {
		return "Timeout";
	}
	if (ex.violations.length > 0) {
		return "Violation";
	}
	if (ex.rtt > slowMs) {
		return "Slow";
	}
	if (ex.attemptCount > 1) {
		return "Retry";
	}
	return "Normal";
}

interface TimeRange {
	minT: number;
	maxT: number;
	timeRange: number;
}

// Keyed by array identity: a new trace load (or facet-filtered array) is a new
// reference, so the cache invalidates itself — no manual busting needed.
const timeRangeCache = new WeakMap<DomainExchange[], TimeRange>();

// Derived from exchanges alone (never from selection state), yet was being
// recomputed from scratch on every hover/drag pointer-move event — findings.md
// #14. Cached per exchanges-array identity so repeated calls during one
// interaction reuse the same result instead of rescanning the full trace.
export function getTimeRange(exchanges: DomainExchange[]): TimeRange {
	const cached = timeRangeCache.get(exchanges);
	if (cached) {
		return cached;
	}
	const times = exchanges.map((ex): number => ex.sentAtMs);
	const [minT, maxT] = minMaxValues(times);
	const result: TimeRange = { maxT, minT, timeRange: maxT - minT || 1 };
	timeRangeCache.set(exchanges, result);
	return result;
}

interface ColumnBuckets {
	cols: number;
	buckets: DomainExchange[][];
}

const columnBucketsCache = new WeakMap<DomainExchange[], ColumnBuckets>();

// Column assignment (which pixel column each exchange's timestamp falls into)
// only depends on exchanges + column count, yet drawMinimap and autoFocus each
// rebuilt it independently on every call, and minimap hover ran its own O(n)
// filter per pointer-move to find one column's bucket — findings.md #14.
// Cached per (exchanges, cols) so drawing, auto-focus, and hover all share one
// precomputed index instead of rescanning the full trace each time.
export function getColumnBuckets(
	exchanges: DomainExchange[],
	cols: number,
): DomainExchange[][] {
	const cached = columnBucketsCache.get(exchanges);
	if (cached && cached.cols === cols) {
		return cached.buckets;
	}
	const { minT, timeRange } = getTimeRange(exchanges);
	const buckets: DomainExchange[][] = Array.from(
		{ length: cols },
		(): DomainExchange[] => [],
	);
	for (const ex of exchanges) {
		const col = Math.min(
			cols - 1,
			Math.floor(((ex.sentAtMs - minT) / timeRange) * (cols - 1)),
		);
		buckets[col]?.push(ex);
	}
	columnBucketsCache.set(exchanges, { buckets, cols });
	return buckets;
}

export function drawEmpty(canvas: HTMLCanvasElement): void {
	const ctx = canvas.getContext("2d");
	if (!ctx) {
		return;
	}
	const style = getComputedStyle(canvas);
	ctx.fillStyle = style.getPropertyValue("--color-bg").trim();
	ctx.fillRect(0, 0, canvas.width, canvas.height);
	ctx.fillStyle = style.getPropertyValue("--color-text-muted").trim();
	ctx.font = "13px system-ui, sans-serif";
	ctx.textAlign = "center";
	ctx.textBaseline = "middle";
	ctx.fillText(
		"No data",
		canvas.width / CANVAS_CENTER_DIVISOR,
		canvas.height / CANVAS_CENTER_DIVISOR,
	);
}

export function getWindowExchanges(
	exchanges: DomainExchange[],
	totalCols: number,
	colStart: number,
	colEnd: number,
	miniWidth: number,
): DomainExchange[] {
	if (totalCols === 0 || colEnd <= colStart) {
		return exchanges;
	}
	const { minT, timeRange } = getTimeRange(exchanges);
	const tStart = minT + (colStart / miniWidth) * timeRange;
	const tEnd = minT + (colEnd / miniWidth) * timeRange;
	const filtered = exchanges.filter(
		(ex): boolean => ex.sentAtMs >= tStart && ex.sentAtMs <= tEnd,
	);
	return filtered.length > 0 ? filtered : exchanges;
}

export function drawMinimap(
	canvas: HTMLCanvasElement,
	exchanges: DomainExchange[],
	slowMs: number,
	colStart: number,
	colEnd: number,
): number {
	const ctx = canvas.getContext("2d");
	if (!ctx) {
		return 0;
	}
	const w = canvas.width;
	const style = getComputedStyle(canvas);
	ctx.fillStyle = style.getPropertyValue("--color-bg").trim();
	ctx.fillRect(0, 0, w, MINI_H);

	if (exchanges.length === 0) {
		drawEmpty(canvas);
		return 0;
	}

	const cols = w;
	const buckets = getColumnBuckets(exchanges, cols);

	const barY = Math.floor((MINI_H - BH) / MINIMAP_BAR_Y_DIVISOR);
	for (const [col, bucket] of buckets.entries()) {
		if (bucket.length > 0) {
			ctx.fillStyle = bucketColour(bucket, slowMs, style);
			ctx.fillRect(col, barY, 1, BH);
		}
	}

	if (colEnd > colStart) {
		ctx.fillStyle = "rgba(59,130,246,0.25)";
		ctx.fillRect(colStart, 0, colEnd - colStart, MINI_H);
		ctx.strokeStyle = "rgba(59,130,246,0.7)";
		ctx.lineWidth = 1;
		ctx.strokeRect(
			colStart + PIXEL_OFFSET,
			PIXEL_OFFSET,
			colEnd - colStart - 1,
			MINI_H - 1,
		);
	}

	return cols;
}

export function drawDetail(
	canvas: HTMLCanvasElement,
	windowExchanges: DomainExchange[],
	slowMs: number,
): { hiddenCount: number } {
	const ctx = canvas.getContext("2d");
	if (!ctx) {
		return { hiddenCount: 0 };
	}
	const style = getComputedStyle(canvas);

	if (windowExchanges.length === 0) {
		drawEmpty(canvas);
		return { hiddenCount: 0 };
	}

	const rows = windowExchanges.length;
	const contentH = MT + rows * (RH + RG) + DETAIL_BOTTOM_PADDING;
	const newH = Math.min(contentH, MAX_H);
	if (canvas.height !== newH) {
		canvas.height = newH;
	}

	const w = canvas.width;
	ctx.fillStyle = style.getPropertyValue("--color-bg").trim();
	ctx.fillRect(0, 0, w, newH);

	const wTimes = windowExchanges.map((ex): number => ex.sentAtMs);
	const [wMinT, wMaxT] = minMaxValues(wTimes);
	const wRange = wMaxT - wMinT || 1;
	const drawW = w - ML;
	const monoFont =
		style.getPropertyValue("--font-mono").trim() || "ui-monospace, monospace";

	ctx.fillStyle = style.getPropertyValue("--color-text-muted").trim();
	ctx.font = `11px ${monoFont}`;
	ctx.textAlign = "left";
	ctx.textBaseline = "middle";
	ctx.fillText(
		`${rows} exchanges  Δt ${wRange.toFixed(0)} ms`,
		ML,
		MT / CANVAS_CENTER_DIVISOR,
	);

	let hiddenCount = 0;
	for (const [i, ex] of windowExchanges.entries()) {
		const y = MT + i * (RH + RG);
		if (y + RH > newH) {
			// Rows are drawn in increasing y order, so once one no longer fits
			// under the (possibly MAX_H-capped) canvas height, neither does any
			// row after it.
			hiddenCount = rows - i;
			break;
		}

		const relMs = ex.sentAtMs - wMinT;
		ctx.fillStyle = style.getPropertyValue("--color-text-muted").trim();
		ctx.font = `9px ${monoFont}`;
		ctx.textAlign = "right";
		ctx.textBaseline = "top";
		ctx.fillText(`${relMs.toFixed(0)}`, ML - ML_LABEL_OFFSET, y);

		const xPos =
			ML + Math.floor(((ex.sentAtMs - wMinT) / wRange) * (drawW - 1));
		const barW = Math.max(MIN_BAR_W, Math.floor((ex.rtt / wRange) * drawW));
		ctx.fillStyle = exchangeColour(ex, slowMs, style);
		ctx.fillRect(xPos, y, Math.min(barW, w - xPos), RH);
	}

	return { hiddenCount };
}

export function autoFocus(
	canvas: HTMLCanvasElement,
	exchanges: DomainExchange[],
): { colStart: number; colEnd: number } | null {
	const w = canvas.width || canvas.clientWidth;
	if (w === 0 || exchanges.length === 0) {
		return null;
	}
	const cols = w;
	const buckets = getColumnBuckets(exchanges, cols);
	let bestScore = -1;
	let bestCol = 0;
	for (const [col, bucket] of buckets.entries()) {
		const score = bucketScore(bucket);
		if (score > bestScore) {
			bestScore = score;
			bestCol = col;
		}
	}
	const windowHalf = Math.max(1, Math.floor(cols * AUTOFOCUS_WINDOW_FRACTION));
	return {
		colEnd: Math.min(cols, bestCol + windowHalf),
		colStart: Math.max(0, bestCol - windowHalf),
	};
}
