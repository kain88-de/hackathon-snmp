<script setup lang="ts">
import { onMounted, onUnmounted, watch } from "vue";
import { ref } from "vue";
import type { DomainExchange, FacetState } from "../lib/model.ts";

const props = defineProps<{
	exchanges: DomainExchange[];
	facetState: FacetState;
}>();

const emit = defineEmits<{ "focus-exchange": [seq: number] }>();

// Layout constants — exact values from spec
const MINI_H = 80;
const ML = 64;
const MT = 24;
const RH = 9;
const RG = 3;
const BH = 6;
const MAX_H = 32_767;

// Named constants for numbers that would otherwise be magic
const CANVAS_CENTER_DIVISOR = 2;
const PIXEL_OFFSET = 0.5;
const DETAIL_BOTTOM_PADDING = 20;
const AUTOFOCUS_WINDOW_FRACTION = 0.05;
const MINIMAP_BAR_Y_DIVISOR = 2;
const ML_LABEL_OFFSET = 4; // px gap between label and bar left edge
const MIN_BAR_W = 3; // minimum exchange bar width px
const VIOLATION_SCORE_BONUS = 1e9; // score bump for buckets with violations
const RTT_SCORE_SCALE = 1000; // ms → score units

const containerEl = ref<HTMLElement | null>(null);
const miniCanvas = ref<HTMLCanvasElement | null>(null);
const detailCanvas = ref<HTMLCanvasElement | null>(null);

// Selected time window: column index range [colStart, colEnd)
// Not wrapped in reactive/ref — plain mutable state for performance
let selectedColStart = 0;
let selectedColEnd = 0;
let isDragging = false;
let dragStartCol = 0;
let totalCols = 0; // updated on each minimap draw

function exchangeColour(
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

function bucketColour(
	bucket: DomainExchange[],
	slowMs: number,
	style: CSSStyleDeclaration,
): string {
	// Display precedence: Timeout > Violation > Slow > Retry > None
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

function drawEmpty(canvas: HTMLCanvasElement): void {
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

function drawMinimap(): void {
	const canvas = miniCanvas.value;
	if (!canvas) {
		return;
	}
	const ctx = canvas.getContext("2d");
	if (!ctx) {
		return;
	}

	const w = canvas.width;
	const style = getComputedStyle(canvas);
	const bgColor = style.getPropertyValue("--color-bg").trim();
	const slowMs = props.facetState.slowMs;

	ctx.fillStyle = bgColor;
	ctx.fillRect(0, 0, w, MINI_H);

	const exchanges = props.exchanges;
	if (exchanges.length === 0) {
		drawEmpty(canvas);
		totalCols = 0;
		return;
	}

	const cols = w;
	totalCols = cols;

	const times = exchanges.map((ex): number => ex.sentAtMs);
	const minT = Math.min(...times);
	const maxT = Math.max(...times);
	const timeRange = maxT - minT || 1;

	// Build buckets
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

	// Draw bars
	const barY = Math.floor((MINI_H - BH) / MINIMAP_BAR_Y_DIVISOR);
	for (const [col, bucket] of buckets.entries()) {
		if (bucket.length > 0) {
			ctx.fillStyle = bucketColour(bucket, slowMs, style);
			ctx.fillRect(col, barY, 1, BH);
		}
	}

	// Draw selection highlight
	if (selectedColEnd > selectedColStart) {
		ctx.fillStyle = "rgba(59,130,246,0.25)";
		ctx.fillRect(
			selectedColStart,
			0,
			selectedColEnd - selectedColStart,
			MINI_H,
		);
		// Selection border
		ctx.strokeStyle = "rgba(59,130,246,0.7)";
		ctx.lineWidth = 1;
		ctx.strokeRect(
			selectedColStart + PIXEL_OFFSET,
			PIXEL_OFFSET,
			selectedColEnd - selectedColStart - 1,
			MINI_H - 1,
		);
	}
}

function getWindowExchanges(): DomainExchange[] {
	const exchanges = props.exchanges;
	if (
		totalCols === 0 ||
		selectedColEnd <= selectedColStart ||
		miniCanvas.value === null
	) {
		return exchanges;
	}
	const miniW = miniCanvas.value.width;
	const times = exchanges.map((ex): number => ex.sentAtMs);
	const minT = Math.min(...times);
	const maxT = Math.max(...times);
	const timeRange = maxT - minT || 1;
	const tStart = minT + (selectedColStart / miniW) * timeRange;
	const tEnd = minT + (selectedColEnd / miniW) * timeRange;
	const filtered = exchanges.filter(
		(ex): boolean => ex.sentAtMs >= tStart && ex.sentAtMs <= tEnd,
	);
	if (filtered.length > 0) {
		return filtered;
	}
	return exchanges;
}

function drawDetail(): void {
	const canvas = detailCanvas.value;
	if (!canvas) {
		return;
	}
	const ctx = canvas.getContext("2d");
	if (!ctx) {
		return;
	}

	const style = getComputedStyle(canvas);
	const bgColor = style.getPropertyValue("--color-bg").trim();
	const slowMs = props.facetState.slowMs;

	const exchanges = props.exchanges;
	if (exchanges.length === 0) {
		drawEmpty(canvas);
		return;
	}

	const windowExchanges = getWindowExchanges();
	const rows = windowExchanges.length;
	const contentH = MT + rows * (RH + RG) + DETAIL_BOTTOM_PADDING;
	const newH = Math.min(contentH, MAX_H);

	if (canvas.height !== newH) {
		canvas.height = newH;
	}

	const w = canvas.width;

	ctx.fillStyle = bgColor;
	ctx.fillRect(0, 0, w, newH);

	// Time range for the window
	const wTimes = windowExchanges.map((ex): number => ex.sentAtMs);
	const wMinT = Math.min(...wTimes);
	const wMaxT = Math.max(...wTimes);
	const wRange = wMaxT - wMinT || 1;

	const drawW = w - ML;
	const monoFont =
		style.getPropertyValue("--font-mono").trim() || "ui-monospace, monospace";

	// Draw top margin label
	ctx.fillStyle = style.getPropertyValue("--color-text-muted").trim();
	ctx.font = `11px ${monoFont}`;
	ctx.textAlign = "left";
	ctx.textBaseline = "middle";
	ctx.fillText(
		`${rows} exchanges  Δt ${wRange.toFixed(0)} ms`,
		ML,
		MT / CANVAS_CENTER_DIVISOR,
	);

	// Draw rows
	for (const [i, ex] of windowExchanges.entries()) {
		const y = MT + i * (RH + RG);

		// Time label in left margin
		const relMs = ex.sentAtMs - wMinT;
		ctx.fillStyle = style.getPropertyValue("--color-text-muted").trim();
		ctx.font = `9px ${monoFont}`;
		ctx.textAlign = "right";
		ctx.textBaseline = "top";
		ctx.fillText(`${relMs.toFixed(0)}`, ML - ML_LABEL_OFFSET, y);

		// Exchange bar
		const xPos =
			ML + Math.floor(((ex.sentAtMs - wMinT) / wRange) * (drawW - 1));
		const barW = Math.max(MIN_BAR_W, Math.floor((ex.rtt / wRange) * drawW));
		ctx.fillStyle = exchangeColour(ex, slowMs, style);
		ctx.fillRect(xPos, y, Math.min(barW, w - xPos), RH);
	}
}

function autoFocus(): void {
	const canvas = miniCanvas.value;
	if (!canvas || props.exchanges.length === 0) {
		return;
	}

	const w = canvas.width || canvas.clientWidth;
	if (w === 0) {
		return;
	}

	const cols = w;
	const exchanges = props.exchanges;
	const times = exchanges.map((ex): number => ex.sentAtMs);
	const minT = Math.min(...times);
	const maxT = Math.max(...times);
	const timeRange = maxT - minT || 1;

	// Build buckets
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

	// Score: violationBonus + maxRtt * 1000 + count
	let bestScore = -1;
	let bestCol = 0;
	for (const [col, bucket] of buckets.entries()) {
		if (bucket.length > 0) {
			const hasViolation = bucket.some(
				(ex): boolean => ex.violations.length > 0,
			);
			const maxRtt = Math.max(...bucket.map((ex): number => ex.rtt));
			let violationBonus = 0;
			if (hasViolation) {
				violationBonus = VIOLATION_SCORE_BONUS;
			}
			const score = violationBonus + maxRtt * RTT_SCORE_SCALE + bucket.length;
			if (score > bestScore) {
				bestScore = score;
				bestCol = col;
			}
		}
	}

	// Select a window around the best column — AUTOFOCUS_WINDOW_FRACTION of total width
	const windowHalf = Math.max(1, Math.floor(cols * AUTOFOCUS_WINDOW_FRACTION));
	selectedColStart = Math.max(0, bestCol - windowHalf);
	selectedColEnd = Math.min(cols, bestCol + windowHalf);
}

function redraw(): void {
	// Sync canvas physical dimensions to CSS layout dimensions
	const mini = miniCanvas.value;
	const detail = detailCanvas.value;
	if (mini) {
		const cssW = mini.clientWidth;
		if (cssW > 0 && mini.width !== cssW) {
			mini.width = cssW;
		}
		mini.height = MINI_H;
	}
	if (detail) {
		const cssW = detail.clientWidth;
		if (cssW > 0 && detail.width !== cssW) {
			detail.width = cssW;
		}
	}

	drawMinimap();
	drawDetail();
}

function colFromMouseX(canvas: HTMLCanvasElement, clientX: number): number {
	const rect = canvas.getBoundingClientRect();
	const x = clientX - rect.left;
	return Math.max(0, Math.min(canvas.width - 1, Math.floor(x)));
}

function detailRowFromMouseY(clientY: number): number | null {
	const canvas = detailCanvas.value;
	if (!canvas) {
		return null;
	}
	const rect = canvas.getBoundingClientRect();
	const y = clientY - rect.top;
	if (y < MT) {
		return null;
	}
	const row = Math.floor((y - MT) / (RH + RG));
	return row;
}

onMounted((): void => {
	const observer = new ResizeObserver((): void => {
		redraw();
	});
	if (containerEl.value) {
		observer.observe(containerEl.value);
	}
	onUnmounted((): void => {
		observer.disconnect();
	});

	// Initial draw
	redraw();

	// Auto-focus after first draw
	if (props.exchanges.length > 0) {
		autoFocus();
		redraw();
	}

	// Minimap interactions
	const mini = miniCanvas.value;
	if (mini) {
		mini.addEventListener("mousedown", (e: MouseEvent): void => {
			isDragging = true;
			dragStartCol = colFromMouseX(mini, e.clientX);
			selectedColStart = dragStartCol;
			selectedColEnd = dragStartCol + 1;
			redraw();
		});

		mini.addEventListener("mousemove", (e: MouseEvent): void => {
			if (!isDragging) {
				return;
			}
			const col = colFromMouseX(mini, e.clientX);
			selectedColStart = Math.min(dragStartCol, col);
			selectedColEnd = Math.max(dragStartCol, col) + 1;
			redraw();
		});

		mini.addEventListener("mouseup", (e: MouseEvent): void => {
			if (!isDragging) {
				return;
			}
			isDragging = false;
			const col = colFromMouseX(mini, e.clientX);
			if (col === dragStartCol) {
				// Single click — select small window around click
				const windowHalf = Math.max(
					1,
					Math.floor((totalCols || mini.width) * AUTOFOCUS_WINDOW_FRACTION),
				);
				selectedColStart = Math.max(0, col - windowHalf);
				selectedColEnd = Math.min(totalCols || mini.width, col + windowHalf);
			} else {
				selectedColStart = Math.min(dragStartCol, col);
				selectedColEnd = Math.max(dragStartCol, col) + 1;
			}
			redraw();
		});

		// Cancel drag if mouse leaves canvas
		mini.addEventListener("mouseleave", (): void => {
			if (isDragging) {
				isDragging = false;
				redraw();
			}
		});
	}

	// Detail canvas: click on row → emit focus-exchange
	const detail = detailCanvas.value;
	if (detail) {
		detail.addEventListener("click", (e: MouseEvent): void => {
			const rowIdx = detailRowFromMouseY(e.clientY);
			if (rowIdx === null) {
				return;
			}

			const exchanges = props.exchanges;
			if (exchanges.length === 0) {
				return;
			}

			const windowExchanges = getWindowExchanges();

			const target = windowExchanges[rowIdx];
			if (target !== undefined) {
				emit("focus-exchange", target.seq);
			}
		});
	}
});

// Redraw when exchanges or facet changes
watch(
	(): readonly [DomainExchange[], FacetState] =>
		[props.exchanges, props.facetState] as const,
	(): void => {
		if (props.exchanges.length > 0) {
			autoFocus();
		}
		redraw();
	},
);
</script>

<template>
	<div ref="containerEl" class="minimap-detail">
		<div class="minimap-section">
			<canvas
				ref="miniCanvas"
				class="minimap-canvas"
				:height="MINI_H"
				aria-label="Minimap overview"
			/>
		</div>
		<div class="detail-section">
			<canvas
				ref="detailCanvas"
				class="detail-canvas"
				aria-label="Exchange detail view"
			/>
		</div>
	</div>
</template>

<style scoped>
.minimap-detail {
	display: flex;
	flex-direction: column;
	flex: 1;
	overflow: hidden;
	background: var(--color-bg);
	padding: 8px 12px;
	gap: 8px;
	height: 100%;
}

.minimap-section {
	flex-shrink: 0;
}

.minimap-canvas {
	display: block;
	width: 100%;
	cursor: crosshair;
	border: 1px solid var(--color-border);
	border-radius: 4px;
}

.detail-section {
	flex: 1;
	overflow-y: auto;
	border: 1px solid var(--color-border);
	border-radius: 4px;
	background: var(--color-surface);
}

.detail-canvas {
	display: block;
	width: 100%;
}
</style>
