<script setup lang="ts">
import { type Ref, computed, ref } from "vue";
import { useVirtualScroll } from "../composables/useVirtualScroll.ts";
import { categorise } from "../lib/findings.ts";
import type { DomainExchange, FacetState } from "../lib/model.ts";
import { lookupOidName } from "../lib/oidNames.gen.ts";
import { rttCssClass } from "../lib/utils.ts";
import {
	computeOffsets,
	sumHeights,
	varHeightEndIdx,
	varHeightStartIdx,
} from "../lib/virtualScroll.ts";

const props = defineProps<{
	exchanges: DomainExchange[];
	facetState: FacetState;
}>();

const emit = defineEmits<{
	"focus-exchange": [seq: number];
}>();

const ROW_HEIGHT = 32;
const HEADER_HEIGHT = 40;
const VIOLATION_LINE_HEIGHT = 20;
const VIOLATION_DETAIL_PADDING = 8;

const { containerEl, containerHeight, onScroll, scrollTop } =
	useVirtualScroll();

type Section = "fast" | "slow" | "timeout";

type VirtualItem =
	| { expanded: boolean; kind: "header"; label: string; section: Section }
	| { exchange: DomainExchange; kind: "row" }
	| { exchange: DomainExchange; kind: "violation-detail" };

const expanded: Record<Section, Ref<boolean>> = {
	fast: ref(true),
	slow: ref(true),
	timeout: ref(true),
};

// Which exchanges (by seq) have their violation fold-out open — independent
// of the row's own click handler, which emits focus-exchange.
const expandedViolations = ref<Set<number>>(new Set());

function toggleViolations(seq: number): void {
	const next = new Set(expandedViolations.value);
	if (next.has(seq)) {
		next.delete(seq);
	} else {
		next.add(seq);
	}
	expandedViolations.value = next;
}

function pushExchangeRows(
	list: VirtualItem[],
	exchanges: DomainExchange[],
): void {
	for (const ex of exchanges) {
		list.push({ exchange: ex, kind: "row" });
		if (ex.violations.length > 0 && expandedViolations.value.has(ex.seq)) {
			list.push({ exchange: ex, kind: "violation-detail" });
		}
	}
}

const items = computed((): VirtualItem[] => {
	const findings = categorise(props.exchanges, props.facetState.slowMs);
	const list: VirtualItem[] = [];

	list.push({
		expanded: expanded.slow.value,
		kind: "header",
		label: `Slow (${findings.slow.length})`,
		section: "slow",
	});
	if (expanded.slow.value) {
		pushExchangeRows(list, findings.slow);
	}

	list.push({
		expanded: expanded.timeout.value,
		kind: "header",
		label: `Timed out (${findings.timeout.length})`,
		section: "timeout",
	});
	if (expanded.timeout.value) {
		pushExchangeRows(list, findings.timeout);
	}

	if (findings.fast.length > 0) {
		list.push({
			expanded: expanded.fast.value,
			kind: "header",
			label: `Fast (${findings.fast.length})`,
			section: "fast",
		});
		if (expanded.fast.value) {
			pushExchangeRows(list, findings.fast);
		}
	}

	return list;
});

function toggleSection(section: Section): void {
	expanded[section].value = !expanded[section].value;
}

// Called only from the template, which iterates the virtualized (visible-only)
// slice — never the full exchange list — so this stays cheap regardless of
// trace size.
function oidInfo(
	exchange: DomainExchange,
): { name: string; description: string | null } | null {
	return lookupOidName(exchange.requestOid);
}

function itemKey(item: VirtualItem, headerIdx: number): string {
	if (item.kind === "header") {
		return `header-${headerIdx}`;
	}
	if (item.kind === "row") {
		return `row-${item.exchange.seq}`;
	}
	return `violation-detail-${item.exchange.seq}`;
}

function itemHeight(item: VirtualItem): number {
	if (item.kind === "header") {
		return HEADER_HEIGHT;
	}
	if (item.kind === "violation-detail") {
		return (
			item.exchange.violations.length * VIOLATION_LINE_HEIGHT +
			VIOLATION_DETAIL_PADDING
		);
	}
	return ROW_HEIGHT;
}

const itemOffsets = computed((): number[] =>
	computeOffsets(items.value, itemHeight),
);

const totalHeight = computed((): number => sumHeights(items.value, itemHeight));

interface VisibleSlice {
	bottomSpacerHeight: number;
	endIdx: number;
	slice: VirtualItem[];
	startIdx: number;
	topSpacerHeight: number;
}

const visibleItems = computed((): VisibleSlice => {
	const scrollY = scrollTop.value;
	const viewEnd = scrollY + containerHeight.value;
	const offsets = itemOffsets.value;
	const allItems = items.value;
	const total = totalHeight.value;

	const startIdx = varHeightStartIdx(allItems, offsets, itemHeight, scrollY);
	const endIdx = varHeightEndIdx(offsets, startIdx, allItems.length, viewEnd);

	const topSpacerHeight = startIdx > 0 ? (offsets[startIdx] ?? 0) : 0;
	const bottomStart =
		endIdx < allItems.length ? (offsets[endIdx] ?? total) : total;

	return {
		bottomSpacerHeight: total - bottomStart,
		endIdx,
		slice: allItems.slice(startIdx, endIdx),
		startIdx,
		topSpacerHeight,
	};
});
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
				:key="itemKey(item, visibleItems.startIdx + i)"
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
					v-else-if="item.kind === 'row'"
					class="exchange-row-wrapper"
					:data-seq="item.exchange.seq"
				>
					<button
						type="button"
						class="exchange-row"
						:data-seq="item.exchange.seq"
						@click="emit('focus-exchange', item.exchange.seq)"
					>
						<span
							class="oid"
							:title="oidInfo(item.exchange)?.description ?? undefined"
							>{{ item.exchange.requestOid }}</span
						>
						<span v-if="oidInfo(item.exchange)?.name" class="oid-name">{{
							oidInfo(item.exchange)?.name
						}}</span>
						<span class="rtt" :class="rttCssClass(item.exchange, facetState.slowMs)"
							>{{ item.exchange.rtt.toFixed(1) }}ms</span
						>
						<span
							v-if="item.exchange.attemptCount > 1"
							class="badge badge-retry"
							>×{{ item.exchange.attemptCount }}</span
						>
					</button>
					<template v-if="item.exchange.violations.length > 0">
						<span class="badge badge-violation"
							>{{ item.exchange.violations.length }} viol</span
						>
						<button
							type="button"
							class="violation-toggle"
							:aria-expanded="expandedViolations.has(item.exchange.seq)"
							:aria-label="`${expandedViolations.has(item.exchange.seq) ? 'Collapse' : 'Expand'} violation details`"
							@click="toggleViolations(item.exchange.seq)"
						>
							<span class="chevron">{{
								expandedViolations.has(item.exchange.seq) ? "▾" : "▸"
							}}</span>
						</button>
					</template>
				</div>
				<div v-else class="violation-detail">
					<div
						v-for="violation in item.exchange.violations"
						:key="violation"
						class="violation-line"
					>
						{{ violation }}
					</div>
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

.exchange-row-wrapper {
	height: 32px;
	display: flex;
	align-items: center;
	gap: 4px;
	padding-right: 8px;
	width: 100%;
	box-sizing: border-box;
	border-bottom: 1px solid var(--color-border);
	background: var(--color-surface);
}

.exchange-row-wrapper:hover {
	background: var(--color-primary-bg);
}

.exchange-row {
	height: 100%;
	min-width: 0;
	flex: 1;
	display: flex;
	align-items: center;
	gap: 8px;
	padding: 0 12px;
	box-sizing: border-box;
	border: none;
	background: transparent;
	font: inherit;
	text-align: left;
	cursor: pointer;
}

.violation-toggle {
	flex-shrink: 0;
	width: 20px;
	height: 100%;
	display: flex;
	align-items: center;
	justify-content: center;
	border: none;
	background: transparent;
	color: var(--color-text-muted);
	cursor: pointer;
}

.violation-toggle:hover {
	color: var(--color-text);
}

.violation-detail {
	box-sizing: border-box;
	padding: 4px 12px 4px 44px;
	background: var(--color-bg);
	border-bottom: 1px solid var(--color-border);
	display: flex;
	flex-direction: column;
	justify-content: center;
}

.violation-line {
	font-size: 12px;
	line-height: 20px;
	color: var(--dim-violation);
}

.oid {
	flex: 1;
	overflow: hidden;
	text-overflow: ellipsis;
	white-space: nowrap;
	color: var(--color-text);
}

.oid-name {
	color: var(--color-text-muted);
	font-size: 11px;
	overflow: hidden;
	text-overflow: ellipsis;
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
