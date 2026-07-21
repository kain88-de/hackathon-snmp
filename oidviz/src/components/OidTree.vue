<script setup lang="ts">
import { computed } from "vue";
import { useVirtualScroll } from "../composables/useVirtualScroll.ts";
import type {
	DomainExchange,
	FacetState,
	FlatRow,
	TrieNode,
} from "../lib/model.ts";
import { rttCssClass, rttCssClassFromRtt } from "../lib/utils.ts";

const props = defineProps<{
	flatRows: FlatRow[];
	facetState: FacetState;
	matchingCount: number;
}>();

const emit = defineEmits<{ reflatten: []; "collapse-all": [] }>();

const ROW_HEIGHT = 32;
const VIRTUAL_OVERSCAN = 2;

const { containerEl, containerHeight, onScroll, scrollTop } =
	useVirtualScroll();

const totalHeight = computed((): number => props.flatRows.length * ROW_HEIGHT);

interface VisibleSlice {
	slice: FlatRow[];
	startIdx: number;
	topSpacerHeight: number;
	bottomSpacerHeight: number;
}

const visibleItems = computed((): VisibleSlice => {
	const scrollY = scrollTop.value;
	const viewEnd = scrollY + containerHeight.value;
	const count = props.flatRows.length;
	const total = totalHeight.value;

	const startIdx = Math.max(
		0,
		Math.floor(scrollY / ROW_HEIGHT) - VIRTUAL_OVERSCAN,
	);
	const endIdx = Math.min(
		count,
		Math.ceil(viewEnd / ROW_HEIGHT) + VIRTUAL_OVERSCAN,
	);

	return {
		bottomSpacerHeight: Math.max(0, total - endIdx * ROW_HEIGHT),
		slice: props.flatRows.slice(startIdx, endIdx),
		startIdx,
		topSpacerHeight: startIdx * ROW_HEIGHT,
	};
});

function onNodeClick(node: TrieNode): void {
	// TrieNode.expanded is intentionally mutable — see model.ts
	node.expanded = !node.expanded;
	emit("reflatten");
}

function flagClass(row: FlatRow): string[] {
	if (row.kind !== "node") {
		return [];
	}
	const classes: string[] = [];
	if (row.node.flags.slow) {
		classes.push("has-slow");
	}
	if (row.node.flags.violation) {
		classes.push("has-violation");
	}
	if (row.node.flags.retry) {
		classes.push("has-retry");
	}
	return classes;
}

function rowKey(row: FlatRow, idx: number): string {
	if (row.kind === "node") {
		return `node-${row.node.fullOid}`;
	}
	return `leaf-${idx}-${row.oid}`;
}

function leafRttClass(ex: DomainExchange): string {
	return rttCssClass(ex, props.facetState.slowMs);
}

function nodeRttClass(rtt: number): string {
	return rttCssClassFromRtt(rtt, props.facetState.slowMs);
}
</script>

<template>
	<div class="oid-tree">
		<div class="oid-tree-toolbar">
			<span class="oid-tree-count">{{ matchingCount }} exchanges</span>
			<button
				type="button"
				class="oid-tree-collapse-btn"
				@click="emit('collapse-all')"
			>
				Collapse all
			</button>
		</div>

		<div
			ref="containerEl"
			class="oid-tree-list"
			@scroll="onScroll"
		>
			<div :style="{ height: totalHeight + 'px', position: 'relative' }">
				<div :style="{ height: visibleItems.topSpacerHeight + 'px' }" />

				<template
					v-for="(row, i) in visibleItems.slice"
					:key="rowKey(row, visibleItems.startIdx + i)"
				>
					<div
						v-if="row.kind === 'node'"
						class="trie-row trie-node"
						:class="flagClass(row)"
						:style="{ paddingLeft: (row.depth * 16 + 8) + 'px' }"
						:data-trie-row="true"
						:aria-expanded="row.node.expanded"
						role="button"
						tabindex="0"
						@click="onNodeClick(row.node)"
						@keydown.enter="onNodeClick(row.node)"
						@keydown.space.prevent="onNodeClick(row.node)"
					>
						<span class="trie-toggle">{{ row.node.expanded ? '▾' : '▸' }}</span>
						<span class="trie-arc">{{ row.node.arc }}</span>
						<span
							v-if="row.node.name"
							class="trie-name"
							:title="row.node.description ?? undefined"
						>{{ row.node.name }}</span>
						<span class="trie-stats">
							<span class="trie-count">{{ row.node.stats.count }}</span>
							<span
								v-if="row.node.stats.maxRtt > 0"
								class="trie-maxrtt"
								:class="nodeRttClass(row.node.stats.maxRtt)"
							>{{ row.node.stats.maxRtt.toFixed(1) }}ms</span>
						</span>
						<span v-if="row.node.flags.slow" class="badge badge-slow">slow</span>
						<span v-if="row.node.flags.violation" class="badge badge-violation">viol</span>
						<span v-if="row.node.flags.retry" class="badge badge-retry">retry</span>
					</div>

					<div
						v-else
						class="trie-row trie-leaf"
						:style="{ paddingLeft: (row.depth * 16 + 8) + 'px' }"
						:data-trie-row="true"
					>
						<span class="trie-leaf-oid" :title="row.description ?? undefined">{{ row.exchange.requestOid }}</span>
						<span v-if="row.name" class="trie-leaf-name">{{ row.name }}</span>
						<span
							class="trie-leaf-rtt"
							:class="leafRttClass(row.exchange)"
						>{{ row.exchange.rtt.toFixed(1) }}ms</span>
						<span
							v-if="row.exchange.violations.length > 0"
							class="badge badge-violation"
						>{{ row.exchange.violations.length }} viol</span>
						<span v-if="row.shared" class="badge badge-shared">shared</span>
					</div>
				</template>

				<div :style="{ height: visibleItems.bottomSpacerHeight + 'px' }" />
			</div>
		</div>
	</div>
</template>

<style scoped>
.oid-tree {
	height: 100%;
	display: flex;
	flex-direction: column;
	font-family: var(--font-mono);
	font-size: 13px;
}

.oid-tree-toolbar {
	display: flex;
	align-items: center;
	gap: 12px;
	padding: 8px 12px;
	border-bottom: 1px solid var(--color-border);
	background: var(--color-bg);
	flex-shrink: 0;
}

.oid-tree-count {
	color: var(--color-text-muted);
	font-size: 12px;
}

.oid-tree-collapse-btn {
	background: transparent;
	color: var(--color-text-muted);
	border: 1px solid var(--color-border);
	border-radius: 4px;
	padding: 3px 8px;
	font-size: 12px;
	cursor: pointer;
}

.oid-tree-collapse-btn:hover {
	background: var(--color-surface);
}

.oid-tree-list {
	flex: 1;
	overflow-y: auto;
}

.trie-row {
	height: 32px;
	display: flex;
	align-items: center;
	gap: 6px;
	border-bottom: 1px solid var(--color-border);
	background: var(--color-surface);
	white-space: nowrap;
	overflow: hidden;
}

.trie-node {
	cursor: pointer;
}

.trie-node:hover {
	background: var(--color-primary-bg);
}

.trie-toggle {
	flex-shrink: 0;
	width: 14px;
	color: var(--color-text-muted);
}

.trie-arc {
	font-weight: 600;
	color: var(--color-text);
}

.trie-name {
	color: var(--color-text-muted);
	font-size: 11px;
	overflow: hidden;
	text-overflow: ellipsis;
}

.trie-stats {
	margin-left: auto;
	display: flex;
	align-items: center;
	gap: 8px;
	flex-shrink: 0;
}

.trie-count {
	color: var(--color-text-muted);
	font-size: 11px;
}

.trie-maxrtt {
	font-size: 11px;
}

.trie-leaf {
	cursor: default;
}

.trie-leaf-oid {
	flex: 1;
	overflow: hidden;
	text-overflow: ellipsis;
	color: var(--color-text);
}

.trie-leaf-name {
	color: var(--color-text-muted);
	font-size: 11px;
	overflow: hidden;
	text-overflow: ellipsis;
}

.trie-leaf-rtt {
	white-space: nowrap;
	min-width: 60px;
	text-align: right;
	flex-shrink: 0;
}

.dim-slow {
	color: var(--dim-slow);
}

.dim-fast {
	color: var(--dim-none);
}

.dim-timeout {
	color: var(--dim-timeout);
}

.badge {
	font-size: 11px;
	padding: 1px 5px;
	border-radius: 3px;
	white-space: nowrap;
	flex-shrink: 0;
}

.badge-slow {
	color: var(--dim-slow);
	background: var(--dim-slow-bg);
}

.badge-violation {
	color: var(--dim-violation);
	background: var(--dim-violation-bg);
}

.badge-retry {
	color: var(--dim-retry);
	background: var(--dim-retry-bg);
}

.badge-shared {
	color: var(--color-text-muted);
	background: var(--color-border);
}
</style>
