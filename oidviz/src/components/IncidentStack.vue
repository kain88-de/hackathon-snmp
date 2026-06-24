<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { clusterMatchesFacets } from "../lib/filters.ts";
import type { DomainExchange, FacetState, Incident } from "../lib/model.ts";

const props = defineProps<{
	exchanges: DomainExchange[];
	facetState: FacetState;
	incidents: Incident[];
}>();

const emit = defineEmits<{ "open-incident": [index: number] }>();

const ROW_HEIGHT = 48;
const DEFAULT_CONTAINER_HEIGHT = 600;

const filteredIncidents = computed((): Incident[] =>
	props.incidents.filter((inc): boolean =>
		clusterMatchesFacets(inc, props.facetState),
	),
);

const totalHeight = computed(
	(): number => filteredIncidents.value.length * ROW_HEIGHT,
);

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
	slice: Incident[];
	startIdx: number;
	topSpacerHeight: number;
}

const visibleItems = computed((): VisibleSlice => {
	const scrollY = scrollTop.value;
	const viewEnd = scrollY + (containerHeight.value || DEFAULT_CONTAINER_HEIGHT);
	const all = filteredIncidents.value;

	const startIdx = Math.max(0, Math.floor(scrollY / ROW_HEIGHT) - 1);
	const endIdx = Math.min(all.length, Math.ceil(viewEnd / ROW_HEIGHT) + 1);

	const topSpacerHeight = startIdx * ROW_HEIGHT;
	const bottomSpacerHeight = (all.length - endIdx) * ROW_HEIGHT;

	return {
		bottomSpacerHeight,
		slice: all.slice(startIdx, endIdx),
		startIdx,
		topSpacerHeight,
	};
});

function formatViolations(inc: Incident): string {
	if (inc.violationTypes.size === 0) {
		return "";
	}
	return [...inc.violationTypes].join(", ");
}
</script>

<template>
	<div
		ref="containerEl"
		class="incident-stack"
		@scroll="onScroll"
	>
		<div v-if="filteredIncidents.length === 0" class="empty-state">
			No incidents match the current filters.
		</div>

		<div
			v-else
			:style="{ height: totalHeight + 'px', position: 'relative' }"
		>
			<div :style="{ height: visibleItems.topSpacerHeight + 'px' }" />

			<div
				v-for="(inc, localIdx) in visibleItems.slice"
				:key="inc.startSeq"
				class="incident-row"
				:data-incident-idx="visibleItems.startIdx + localIdx"
				tabindex="0"
				role="button"
				:aria-label="`Incident ${visibleItems.startIdx + localIdx + 1}: ${inc.region}, score ${inc.score}`"
				@click="emit('open-incident', visibleItems.startIdx + localIdx)"
				@keydown.enter="emit('open-incident', visibleItems.startIdx + localIdx)"
				@keydown.space.prevent="emit('open-incident', visibleItems.startIdx + localIdx)"
			>
				<span class="score-badge">{{ inc.score }}</span>
				<span class="region">{{ inc.region }}</span>
				<span class="stat stat-rtt">{{ inc.peakRtt }}ms</span>
				<span v-if="inc.timeoutCount > 0" class="chip chip-timeout">
					{{ inc.timeoutCount }} timeout{{ inc.timeoutCount > 1 ? 's' : '' }}
				</span>
				<span v-if="inc.retryCount > 0" class="chip chip-retry">
					{{ inc.retryCount }} retry
				</span>
				<span
					v-if="inc.violationTypes.size > 0"
					class="chip chip-violation"
					:title="formatViolations(inc)"
				>
					{{ inc.violationTypes.size }} viol
				</span>
			</div>

			<div :style="{ height: visibleItems.bottomSpacerHeight + 'px' }" />
		</div>
	</div>
</template>

<style scoped>
.incident-stack {
	height: 100%;
	overflow-y: auto;
	font-family: var(--font-mono);
	font-size: 13px;
}

.empty-state {
	padding: 40px 16px;
	color: var(--color-text-muted);
	text-align: center;
}

.incident-row {
	height: 48px;
	display: flex;
	align-items: center;
	gap: 8px;
	padding: 0 12px;
	cursor: pointer;
	border-bottom: 1px solid var(--color-border);
	background: var(--color-surface);
}

.incident-row:hover,
.incident-row:focus {
	background: var(--color-primary-bg);
	outline: none;
}

.score-badge {
	min-width: 56px;
	text-align: right;
	font-weight: 600;
	color: var(--color-text);
	flex-shrink: 0;
}

.region {
	flex: 1;
	overflow: hidden;
	text-overflow: ellipsis;
	white-space: nowrap;
	color: var(--color-text);
}

.stat-rtt {
	white-space: nowrap;
	min-width: 60px;
	text-align: right;
	color: var(--color-text-muted);
	flex-shrink: 0;
}

.chip {
	font-size: 11px;
	padding: 2px 6px;
	border-radius: 3px;
	white-space: nowrap;
	flex-shrink: 0;
}

.chip-timeout {
	color: var(--dim-timeout);
	background: var(--dim-timeout-bg);
}

.chip-retry {
	color: var(--dim-retry);
	background: var(--dim-retry-bg);
}

.chip-violation {
	color: var(--dim-violation);
	background: var(--dim-violation-bg);
}

.chip-slow {
	color: var(--dim-slow);
	background: var(--dim-slow-bg);
}
</style>
