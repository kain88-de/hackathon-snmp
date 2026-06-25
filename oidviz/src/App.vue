<script setup lang="ts">
import { computed, ref, watch } from "vue";
import FindingsByCategory from "./components/FindingsByCategory.vue";
import LandingScreen from "./components/LandingScreen.vue";
import MinimapDetail from "./components/MinimapDetail.vue";
import OidTree from "./components/OidTree.vue";
import Sidebar from "./components/Sidebar.vue";
import { matchesFacets } from "./lib/filters.ts";
import type {
	ActiveView,
	AppState,
	DomainExchange,
	FacetState,
	FlatRow,
	ParseResult,
	TrieNode,
	WorkerResponse,
} from "./lib/model.ts";
import {
	autoExpand,
	buildTrie,
	collapseAll,
	flatten,
	rollup,
} from "./lib/oidTrie.ts";

const state = ref<AppState>({ phase: "landing" });
const facetState = ref<FacetState>({
	corr: "any",
	perf: "any",
	retryOnly: false,
	slowMs: 1000,
});
const activeView = ref<ActiveView>("findings");

let worker: Worker | null = null;

function onFileSelected(buffer: ArrayBuffer): void {
	state.value = { phase: "loading" };

	// Terminate any in-flight worker before creating a new one
	if (worker !== null) {
		worker.terminate();
		worker = null;
	}

	const w = new Worker(new URL("./lib/parser.worker.ts", import.meta.url), {
		type: "module",
	});

	w.addEventListener("message", (event: MessageEvent<WorkerResponse>): void => {
		const msg = event.data;
		if (msg.type === "result") {
			state.value = { phase: "viewer", result: msg.data };
		} else {
			state.value = { message: msg.message, phase: "error" };
		}
		worker = null;
	});

	w.addEventListener("error", (err: ErrorEvent): void => {
		state.value = { message: err.message, phase: "error" };
		worker = null;
	});

	worker = w;
	// Transfer the ArrayBuffer so we avoid copying it
	w.postMessage({ buffer, type: "parse" }, [buffer]);
}

function onViewChange(view: ActiveView): void {
	activeView.value = view;
}

function onFacetChange(patch: Partial<FacetState>): void {
	Object.assign(facetState.value, patch);
}

function currentResult(): ParseResult | null {
	if (state.value.phase === "viewer") {
		return state.value.result;
	}
	return null;
}

const filteredExchanges = computed((): DomainExchange[] => {
	if (state.value.phase !== "viewer") {
		return [];
	}
	return state.value.result.exchanges.filter((ex): boolean =>
		matchesFacets(ex, facetState.value),
	);
});

function onFocusExchange(_seq: number): void {
	// no-op for now — placeholder for future navigation
}

// OID Tree
const oidRoot = computed((): TrieNode | null => {
	if (state.value.phase !== "viewer") {
		return null;
	}
	const root = buildTrie(filteredExchanges.value);
	rollup(root, facetState.value.slowMs);
	autoExpand(root);
	return root;
});

const flatRows = ref<FlatRow[]>([]);

watch(
	oidRoot,
	(root): void => {
		if (root === null) {
			flatRows.value = [];
		} else {
			flatRows.value = flatten(root);
		}
	},
	{ immediate: true },
);

function onReflatten(): void {
	if (oidRoot.value !== null) {
		flatRows.value = flatten(oidRoot.value);
	}
}

function onCollapseAll(): void {
	if (oidRoot.value === null) {
		return;
	}
	collapseAll(oidRoot.value);
	flatRows.value = flatten(oidRoot.value);
}
</script>

<template>
	<div id="app" :data-phase="state.phase">
		<Sidebar
			:app-state="state"
			:result="currentResult()"
			:facet-state="facetState"
			:active-view="activeView"
			@file-selected="onFileSelected"
			@view-change="onViewChange"
			@facet-change="onFacetChange"
		/>

		<div class="app-main">
			<LandingScreen
				v-if="state.phase === 'landing' || state.phase === 'loading'"
				:app-state="state"
				@file-selected="onFileSelected"
			/>

			<div v-else-if="state.phase === 'viewer'" class="viewer-content">
				<FindingsByCategory
					v-if="activeView === 'findings'"
					:exchanges="filteredExchanges"
					:facet-state="facetState"
				/>
				<MinimapDetail
					v-else-if="activeView === 'minimap'"
					:exchanges="filteredExchanges"
					:facet-state="facetState"
					@focus-exchange="onFocusExchange"
				/>
				<OidTree
					v-else-if="activeView === 'oidtree'"
					:flat-rows="flatRows"
					:facet-state="facetState"
					:matching-count="filteredExchanges.length"
					@reflatten="onReflatten"
					@collapse-all="onCollapseAll"
				/>
			</div>

			<div v-else-if="state.phase === 'error'" class="error-page" role="alert">
				<p>Error: {{ state.message }}</p>
			</div>
		</div>
	</div>
</template>

<style scoped>
#app {
	display: flex;
	flex-direction: row;
	height: 100%;
}

.app-main {
	flex: 1;
	display: flex;
	flex-direction: column;
	height: 100%;
	overflow: hidden;
}

.viewer-content {
	flex: 1;
	overflow: hidden;
	display: flex;
	flex-direction: column;
}

.error-page {
	padding: 40px;
	color: var(--dim-timeout);
}
</style>
