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

const { containerEl, containerHeight, onScroll, scrollTop } =
	useVirtualScroll();

type Section = "fast" | "slow" | "timeout";

type VirtualItem =
	| { expanded: boolean; kind: "header"; label: string; section: Section }
	| { exchange: DomainExchange; kind: "row" };

const expanded: Record<Section, Ref<boolean>> = {
	fast: ref(true),
	slow: ref(true),
	timeout: ref(true),
};

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
		for (const ex of findings.slow) {
			list.push({ exchange: ex, kind: "row" });
		}
	}

	list.push({
		expanded: expanded.timeout.value,
		kind: "header",
		label: `Timed out (${findings.timeout.length})`,
		section: "timeout",
	});
	if (expanded.timeout.value) {
		for (const ex of findings.timeout) {
			list.push({ exchange: ex, kind: "row" });
		}
	}

	if (findings.fast.length > 0) {
		list.push({
			expanded: expanded.fast.value,
			kind: "header",
			label: `Fast (${findings.fast.length})`,
			section: "fast",
		});
		if (expanded.fast.value) {
			for (const ex of findings.fast) {
				list.push({ exchange: ex, kind: "row" });
			}
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

function itemHeight(item: VirtualItem): number {
	return item.kind === "header" ? HEADER_HEIGHT : ROW_HEIGHT;
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
				<button
					v-else
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
						v-if="item.exchange.violations.length > 0"
						class="badge badge-violation"
						:title="item.exchange.violations.join(', ')"
						>{{ item.exchange.violations.join(", ") }}</span
					>
					<span
						v-if="item.exchange.attemptCount > 1"
						class="badge badge-retry"
						>×{{ item.exchange.attemptCount }}</span
					>
				</button>
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
	width: 100%;
	box-sizing: border-box;
	border: none;
	border-bottom: 1px solid var(--color-border);
	background: var(--color-surface);
	font: inherit;
	text-align: left;
	cursor: pointer;
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
	max-width: 200px;
	overflow: hidden;
	text-overflow: ellipsis;
	flex-shrink: 0;
}

.badge-retry {
	color: var(--dim-retry);
	background: var(--dim-retry-bg);
}
</style>
