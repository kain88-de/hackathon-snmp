<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { categorise } from "../lib/findings.ts";
import type { DomainExchange, FacetState } from "../lib/model.ts";

const props = defineProps<{
	exchanges: DomainExchange[];
	facetState: FacetState;
}>();

const emit = defineEmits<{
	"focus-exchange": [seq: number];
}>();

const ROW_HEIGHT = 32;
const HEADER_HEIGHT = 40;
const DEFAULT_CONTAINER_HEIGHT = 600;

const slowExpanded = ref(true);
const timeoutExpanded = ref(true);
const fastExpanded = ref(true);

type VirtualItem =
	| {
			kind: "header";
			label: string;
			section: "slow" | "timeout" | "fast";
			expanded: boolean;
	  }
	| { exchange: DomainExchange; kind: "row" };

const items = computed((): VirtualItem[] => {
	const findings = categorise(props.exchanges, props.facetState.slowMs);
	const list: VirtualItem[] = [];

	list.push({
		expanded: slowExpanded.value,
		kind: "header",
		label: `Slow (${findings.slow.length})`,
		section: "slow",
	});
	if (slowExpanded.value) {
		for (const ex of findings.slow) {
			list.push({ exchange: ex, kind: "row" });
		}
	}

	list.push({
		expanded: timeoutExpanded.value,
		kind: "header",
		label: `Timed out (${findings.timeout.length})`,
		section: "timeout",
	});
	if (timeoutExpanded.value) {
		for (const ex of findings.timeout) {
			list.push({ exchange: ex, kind: "row" });
		}
	}

	if (findings.fast.length > 0) {
		list.push({
			expanded: fastExpanded.value,
			kind: "header",
			label: `Fast (${findings.fast.length})`,
			section: "fast",
		});
		if (fastExpanded.value) {
			for (const ex of findings.fast) {
				list.push({ exchange: ex, kind: "row" });
			}
		}
	}

	return list;
});

function toggleSection(section: "slow" | "timeout" | "fast"): void {
	if (section === "slow") {
		slowExpanded.value = !slowExpanded.value;
	} else if (section === "timeout") {
		timeoutExpanded.value = !timeoutExpanded.value;
	} else {
		fastExpanded.value = !fastExpanded.value;
	}
}

function itemHeight(item: VirtualItem): number {
	if (item.kind === "header") {
		return HEADER_HEIGHT;
	}
	return ROW_HEIGHT;
}

// Pixel offsets for each item
const itemOffsets = computed((): number[] => {
	const offsets: number[] = [];
	let offset = 0;
	for (const item of items.value) {
		offsets.push(offset);
		offset += itemHeight(item);
	}
	return offsets;
});

const totalHeight = computed((): number => {
	let total = 0;
	for (const item of items.value) {
		total += itemHeight(item);
	}
	return total;
});

const scrollTop = ref(0);
const containerHeight = ref(DEFAULT_CONTAINER_HEIGHT);
const containerEl = ref<HTMLElement | null>(null);

onMounted((): void => {
	if (containerEl.value !== null) {
		containerHeight.value =
			containerEl.value.clientHeight || DEFAULT_CONTAINER_HEIGHT;
	}
});

function onScroll(e: Event): void {
	scrollTop.value = (e.target as HTMLElement).scrollTop;
}

interface VisibleSlice {
	bottomSpacerHeight: number;
	endIdx: number;
	slice: VirtualItem[];
	startIdx: number;
	topSpacerHeight: number;
}

function findStartIdx(
	allItems: VirtualItem[],
	offsets: number[],
	scrollY: number,
): number {
	let startIdx = 0;
	for (let i = 0; i < allItems.length; i += 1) {
		const offset = offsets[i] ?? 0;
		const item = allItems[i];
		if (item === undefined) {
			break;
		}
		const itemEnd = offset + itemHeight(item);
		if (itemEnd <= scrollY) {
			startIdx = i + 1;
		} else {
			break;
		}
	}
	return startIdx;
}

interface EndIdxOptions {
	offsets: number[];
	startIdx: number;
	totalCount: number;
	viewEnd: number;
}

function findEndIdx(opts: EndIdxOptions): number {
	for (let i = opts.startIdx; i < opts.totalCount; i += 1) {
		const offset = opts.offsets[i] ?? 0;
		if (offset >= opts.viewEnd) {
			return i;
		}
	}
	return opts.totalCount;
}

const visibleItems = computed((): VisibleSlice => {
	const scrollY = scrollTop.value;
	const viewEnd = scrollY + (containerHeight.value || DEFAULT_CONTAINER_HEIGHT);
	const offsets = itemOffsets.value;
	const allItems = items.value;
	const total = totalHeight.value;

	const startIdx = findStartIdx(allItems, offsets, scrollY);
	const endIdx = findEndIdx({
		offsets,
		startIdx,
		totalCount: allItems.length,
		viewEnd,
	});

	let topSpacerHeight = 0;
	if (startIdx > 0) {
		topSpacerHeight = offsets[startIdx] ?? 0;
	}

	let bottomStart = total;
	if (endIdx < allItems.length) {
		bottomStart = offsets[endIdx] ?? total;
	}
	const bottomSpacerHeight = total - bottomStart;

	return {
		bottomSpacerHeight,
		endIdx,
		slice: allItems.slice(startIdx, endIdx),
		startIdx,
		topSpacerHeight,
	};
});

function rttClass(ex: DomainExchange): string {
	if (ex.isTimeout) {
		return "dim-timeout";
	}
	if (ex.rtt > props.facetState.slowMs) {
		return "dim-slow";
	}
	return "dim-fast";
}
</script>

<template>
	<div
		ref="containerEl"
		class="findings-container"
		@scroll="onScroll"
	>
		<div :style="{ height: totalHeight + 'px', position: 'relative' }">
			<div :style="{ height: visibleItems.topSpacerHeight + 'px' }" />

			<template
				v-for="(item, i) in visibleItems.slice"
				:key="item.kind === 'row' ? item.exchange.seq : `header-${visibleItems.startIdx + i}`"
			>
				<button
					v-if="item.kind === 'header'"
					class="section-header"
					:data-label="item.label"
					:aria-expanded="item.expanded"
					@click="toggleSection(item.section)"
				>
					<span class="chevron">{{ item.expanded ? "▼" : "▶" }}</span>
					{{ item.label }}
				</button>
				<div
					v-else
					class="exchange-row"
					:data-seq="item.exchange.seq"
					@click="emit('focus-exchange', item.exchange.seq)"
				>
					<span class="oid" :title="item.exchange.requestOid">{{
						item.exchange.requestOid
					}}</span>
					<span class="rtt" :class="rttClass(item.exchange)"
						>{{ item.exchange.rtt }}ms</span
					>
					<span
						v-if="item.exchange.violations.length > 0"
						class="badge badge-violation"
						>{{ item.exchange.violations.length }} viol</span
					>
					<span
						v-if="item.exchange.attemptCount > 1"
						class="badge badge-retry"
						>×{{ item.exchange.attemptCount }}</span
					>
				</div>
			</template>

			<div :style="{ height: visibleItems.bottomSpacerHeight + 'px' }" />
		</div>
	</div>
</template>

<style scoped>
.findings-container {
	height: 100%;
	overflow-y: auto;
	font-family: var(--font-mono);
	font-size: 13px;
}

.section-header {
	height: 40px;
	display: flex;
	align-items: center;
	gap: 6px;
	padding: 0 12px;
	width: 100%;
	box-sizing: border-box;
	font-size: 12px;
	font-weight: 600;
	color: var(--color-text-muted);
	background: var(--color-bg);
	border: none;
	border-bottom: 1px solid var(--color-border);
	z-index: 1;
	cursor: pointer;
	text-align: left;
	font-family: var(--font-mono);
}

.section-header:hover {
	background: var(--color-primary-bg);
}

.chevron {
	font-size: 10px;
}

.exchange-row {
	height: 32px;
	display: flex;
	align-items: center;
	gap: 8px;
	padding: 0 12px;
	cursor: pointer;
	border-bottom: 1px solid var(--color-border);
	background: var(--color-surface);
}

.exchange-row:hover {
	background: var(--color-primary-bg);
}

.oid {
	flex: 1;
	overflow: hidden;
	text-overflow: ellipsis;
	white-space: nowrap;
	color: var(--color-text);
}

.rtt {
	white-space: nowrap;
	min-width: 60px;
	text-align: right;
}

.dim-slow {
	color: var(--dim-slow);
}

.dim-timeout {
	color: var(--dim-timeout);
}

.dim-fast {
	color: var(--dim-none);
}

.badge {
	font-size: 11px;
	padding: 1px 5px;
	border-radius: 3px;
	white-space: nowrap;
}

.badge-violation {
	color: var(--dim-violation);
	background: var(--dim-violation-bg);
}

.badge-retry {
	color: var(--dim-retry);
	background: var(--dim-retry-bg);
}
</style>
