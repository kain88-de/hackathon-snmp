<script setup lang="ts">
import { onMounted, onUnmounted, watch } from "vue";
import { ref } from "vue";
import {
	AUTOFOCUS_WINDOW_FRACTION,
	MAX_H,
	MINI_H,
	MT,
	RG,
	RH,
	autoFocus,
	drawDetail,
	drawMinimap,
	exchangeStatus,
	getWindowExchanges,
	worstBucketStatus,
} from "../lib/minimapDraw.ts";
import type { DomainExchange, FacetState } from "../lib/model.ts";
import { minMaxValues } from "../lib/utils.ts";

const props = defineProps<{
	exchanges: DomainExchange[];
	facetState: FacetState;
}>();

const emit = defineEmits<{ "focus-exchange": [seq: number] }>();

const containerEl = ref<HTMLElement | null>(null);
const miniCanvas = ref<HTMLCanvasElement | null>(null);
const detailCanvas = ref<HTMLCanvasElement | null>(null);
const tooltipEl = ref<HTMLDivElement | null>(null);

// Mutable selection state — plain vars for perf (no reactive overhead per frame)
let selectedColStart = 0;
let selectedColEnd = 0;
let isDragging = false;
let dragStartCol = 0;
let totalCols = 0;

type DragMode = "create" | "pan" | "edge-left" | "edge-right";
let dragMode: DragMode = "create";
let dragPanAnchorCol = 0;
let dragPanStartL = 0;
let dragPanStartR = 0;

const EDGE_GRAB_PX = 6;
const TOOLTIP_X_OFFSET = 12;
const TOOLTIP_Y_OFFSET = 4;
const OID_TRUNCATE_LEN = 40;
const ARROW_SHIFT_FRACTION = 0.2;

function escHtml(s: string): string {
	return s
		.replaceAll("&", "&amp;")
		.replaceAll("<", "&lt;")
		.replaceAll(">", "&gt;")
		.replaceAll('"', "&quot;");
}

function showTooltip(html: string, clientX: number, clientY: number): void {
	const el = tooltipEl.value;
	if (!el) {
		return;
	}
	el.innerHTML = html;
	el.style.display = "block";
	el.style.left = `${clientX + TOOLTIP_X_OFFSET}px`;
	el.style.top = `${clientY - TOOLTIP_Y_OFFSET}px`;
}

function hideTooltip(): void {
	const el = tooltipEl.value;
	if (!el) {
		return;
	}
	el.style.display = "none";
}

function dragModeForCol(col: number): DragMode {
	const winW = selectedColEnd - selectedColStart;
	if (winW > 0 && col >= selectedColStart && col < selectedColEnd) {
		if (col - selectedColStart <= EDGE_GRAB_PX) {
			return "edge-left";
		}
		if (selectedColEnd - 1 - col <= EDGE_GRAB_PX) {
			return "edge-right";
		}
		return "pan";
	}
	return "create";
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
	return Math.floor((y - MT) / (RH + RG));
}

function applyDragMove(col: number, cols: number): void {
	if (dragMode === "pan") {
		const delta = col - dragPanAnchorCol;
		const winW = dragPanStartR - dragPanStartL;
		const newStart = Math.max(0, Math.min(cols - winW, dragPanStartL + delta));
		selectedColStart = newStart;
		selectedColEnd = newStart + winW;
	} else if (dragMode === "edge-left") {
		selectedColStart = Math.max(0, Math.min(col, selectedColEnd - 1));
	} else if (dragMode === "edge-right") {
		selectedColEnd = Math.max(selectedColStart + 1, Math.min(cols, col + 1));
	} else {
		selectedColStart = Math.min(dragStartCol, col);
		selectedColEnd = Math.max(dragStartCol, col) + 1;
	}
}

function updateCursor(mini: HTMLCanvasElement, col: number): void {
	const mode = dragModeForCol(col);
	if (mode === "edge-left" || mode === "edge-right") {
		mini.style.cursor = "ew-resize";
	} else if (mode === "pan") {
		mini.style.cursor = "grab";
	} else {
		mini.style.cursor = "crosshair";
	}
}

function windowExchanges(): DomainExchange[] {
	const mini = miniCanvas.value;
	return getWindowExchanges(
		props.exchanges,
		totalCols,
		selectedColStart,
		selectedColEnd,
		mini?.width ?? 0,
	);
}

function onMinimapHover(e: MouseEvent, col: number): void {
	const exchanges = props.exchanges;
	if (exchanges.length === 0 || totalCols === 0) {
		return;
	}
	const times = exchanges.map((ex): number => ex.sentAtMs);
	const [minT, maxT] = minMaxValues(times);
	const timeRange = maxT - minT || 1;
	const bucket = exchanges.filter((ex): boolean => {
		const c = Math.min(
			totalCols - 1,
			Math.floor(((ex.sentAtMs - minT) / timeRange) * (totalCols - 1)),
		);
		return c === col;
	});
	const count = bucket.length;
	const status = worstBucketStatus(bucket, props.facetState.slowMs);
	const relMs = minT + (col / totalCols) * timeRange - minT;
	const plural = count === 1 ? "" : "s";
	const html =
		`<strong>${count} exchange${plural}</strong><br>` +
		`Status: ${status}<br>` +
		`+${relMs.toFixed(0)}ms`;
	showTooltip(html, e.clientX, e.clientY);
}

function onDetailHover(e: MouseEvent): void {
	const rowIdx = detailRowFromMouseY(e.clientY);
	if (rowIdx === null) {
		hideTooltip();
		return;
	}
	const ex = windowExchanges()[rowIdx];
	if (ex === undefined) {
		hideTooltip();
		return;
	}
	const oid =
		ex.requestOid.length > OID_TRUNCATE_LEN
			? `${ex.requestOid.slice(0, OID_TRUNCATE_LEN)}…`
			: ex.requestOid;
	const status = exchangeStatus(ex, props.facetState.slowMs);
	const html =
		`<strong>${escHtml(oid)}</strong><br>` +
		`RTT: ${ex.rtt.toFixed(1)}ms<br>` +
		`Status: ${status}`;
	showTooltip(html, e.clientX, e.clientY);
}

function redraw(): void {
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

	if (mini) {
		totalCols = drawMinimap(
			mini,
			props.exchanges,
			props.facetState.slowMs,
			selectedColStart,
			selectedColEnd,
		);
	}
	if (detail) {
		drawDetail(detail, windowExchanges(), props.facetState.slowMs);
	}
}

function runAutoFocus(): void {
	const mini = miniCanvas.value;
	if (!mini || props.exchanges.length === 0) {
		return;
	}
	const result = autoFocus(mini, props.exchanges);
	if (result !== null) {
		selectedColStart = result.colStart;
		selectedColEnd = result.colEnd;
	}
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

	redraw();
	if (props.exchanges.length > 0) {
		runAutoFocus();
		redraw();
	}

	const mini = miniCanvas.value;
	if (mini) {
		mini.setAttribute("tabindex", "0");

		mini.addEventListener("mousedown", (e: MouseEvent): void => {
			isDragging = true;
			dragStartCol = colFromMouseX(mini, e.clientX);
			dragMode = dragModeForCol(dragStartCol);
			if (dragMode === "pan") {
				dragPanAnchorCol = dragStartCol;
				dragPanStartL = selectedColStart;
				dragPanStartR = selectedColEnd;
			} else if (dragMode !== "edge-left" && dragMode !== "edge-right") {
				selectedColStart = dragStartCol;
				selectedColEnd = dragStartCol + 1;
			}
			redraw();
		});

		mini.addEventListener("mousemove", (e: MouseEvent): void => {
			const col = colFromMouseX(mini, e.clientX);
			if (!isDragging) {
				updateCursor(mini, col);
				onMinimapHover(e, col);
				return;
			}
			hideTooltip();
			applyDragMove(col, totalCols || mini.width);
			redraw();
		});

		mini.addEventListener("mouseup", (e: MouseEvent): void => {
			if (!isDragging) {
				return;
			}
			isDragging = false;
			const col = colFromMouseX(mini, e.clientX);
			if (dragMode === "create" && col === dragStartCol) {
				const windowHalf = Math.max(
					1,
					Math.floor((totalCols || mini.width) * AUTOFOCUS_WINDOW_FRACTION),
				);
				selectedColStart = Math.max(0, col - windowHalf);
				selectedColEnd = Math.min(totalCols || mini.width, col + windowHalf);
			}
			redraw();
		});

		mini.addEventListener("mouseleave", (): void => {
			mini.style.cursor = "crosshair";
			hideTooltip();
			if (isDragging) {
				isDragging = false;
				redraw();
			}
		});

		mini.addEventListener("keydown", (e: KeyboardEvent): void => {
			if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") {
				return;
			}
			e.preventDefault();
			const cols = totalCols || mini.width;
			const winW = selectedColEnd - selectedColStart;
			const shift = Math.max(1, Math.round(winW * ARROW_SHIFT_FRACTION));
			if (e.key === "ArrowLeft") {
				const newStart = Math.max(0, selectedColStart - shift);
				selectedColStart = newStart;
				selectedColEnd = newStart + winW;
			} else {
				const newEnd = Math.min(cols, selectedColEnd + shift);
				selectedColEnd = newEnd;
				selectedColStart = newEnd - winW;
			}
			redraw();
		});
	}

	const detail = detailCanvas.value;
	if (detail) {
		detail.addEventListener("click", (e: MouseEvent): void => {
			const rowIdx = detailRowFromMouseY(e.clientY);
			if (rowIdx === null || props.exchanges.length === 0) {
				return;
			}
			const target = windowExchanges()[rowIdx];
			if (target !== undefined) {
				emit("focus-exchange", target.seq);
			}
		});

		detail.addEventListener("mousemove", (e: MouseEvent): void => {
			onDetailHover(e);
		});

		detail.addEventListener("mouseleave", (): void => {
			hideTooltip();
		});
	}
});

watch(
	(): readonly [DomainExchange[], FacetState] =>
		[props.exchanges, props.facetState] as const,
	(): void => {
		if (props.exchanges.length > 0) {
			runAutoFocus();
		}
		redraw();
	},
);
</script>

<template>
	<div ref="containerEl" class="minimap-detail">
		<div class="minimap-section">
			<div class="color-legend">
				<span class="legend-item">
					<span class="legend-swatch" style="background: var(--dim-timeout)" />
					Timeout
				</span>
				<span class="legend-item">
					<span class="legend-swatch" style="background: var(--dim-violation)" />
					Violation
				</span>
				<span class="legend-item">
					<span class="legend-swatch" style="background: var(--dim-slow)" />
					Slow
				</span>
				<span class="legend-item">
					<span class="legend-swatch" style="background: var(--dim-retry)" />
					Retry
				</span>
				<span class="legend-item">
					<span class="legend-swatch" style="background: var(--dim-none)" />
					Normal
				</span>
			</div>
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
				:height="MAX_H"
				aria-label="Exchange detail view"
			/>
		</div>
		<div ref="tooltipEl" class="canvas-tooltip" />
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
	cursor: crosshair;
}

.color-legend {
	display: flex;
	flex-direction: row;
	gap: 12px;
	margin-bottom: 4px;
	font-size: 11px;
	color: var(--color-text-muted);
}

.legend-item {
	display: flex;
	align-items: center;
	gap: 4px;
}

.legend-swatch {
	display: inline-block;
	width: 10px;
	height: 10px;
	border-radius: 2px;
	flex-shrink: 0;
}

.canvas-tooltip {
	position: fixed;
	display: none;
	background: var(--color-surface);
	border: 1px solid var(--color-border);
	border-radius: 4px;
	box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
	padding: 6px 8px;
	font-size: 11px;
	line-height: 1.5;
	pointer-events: none;
	z-index: 1000;
	white-space: nowrap;
}
</style>
