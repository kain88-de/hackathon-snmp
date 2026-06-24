<script setup lang="ts">
import { computed, ref, watch } from "vue";
import FindingsByCategory from "./components/FindingsByCategory.vue";
import IncidentModal from "./components/IncidentModal.vue";
import IncidentStack from "./components/IncidentStack.vue";
import LandingScreen from "./components/LandingScreen.vue";
import Sidebar from "./components/Sidebar.vue";
import { clusterMatchesFacets, matchesFacets } from "./lib/filters.ts";
import { buildIncidents } from "./lib/incidentStack.ts";
import type {
	ActiveView,
	AppState,
	DomainExchange,
	FacetState,
	Incident,
	ParseResult,
	WorkerResponse,
} from "./lib/model.ts";

const state = ref<AppState>({ phase: "landing" });
const facetState = ref<FacetState>({
	corr: "any",
	perf: "any",
	retryOnly: false,
	slowMs: 1000,
});
const activeView = ref<ActiveView>("findings");
const selectedIncidentIndex = ref<number | null>(null);
// Track the DOM element that triggered the modal, so we can restore focus on close
let modalTriggerEl: HTMLElement | null = null;

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

// Built from full exchange list (not filtered), because clustering is anomaly-driven
const incidents = computed((): Incident[] => {
	if (state.value.phase !== "viewer") {
		return [];
	}
	return buildIncidents(state.value.result.exchanges, facetState.value.slowMs);
});

// Filtered incidents: same filter applied in IncidentStack, used for modal lookup
const filteredIncidents = computed((): Incident[] =>
	incidents.value.filter((inc): boolean =>
		clusterMatchesFacets(inc, facetState.value),
	),
);

function onOpenIncident(index: number): void {
	// Capture the currently focused element as the trigger for focus restoration
	if (document.activeElement instanceof HTMLElement) {
		modalTriggerEl = document.activeElement;
	} else {
		modalTriggerEl = null;
	}
	selectedIncidentIndex.value = index;
}

function onCloseIncident(): void {
	selectedIncidentIndex.value = null;
	// Restore focus to the trigger row
	modalTriggerEl?.focus();
	modalTriggerEl = null;
}

function onNavigateIncident(delta: number): void {
	if (selectedIncidentIndex.value === null) {
		return;
	}
	const next = selectedIncidentIndex.value + delta;
	if (next >= 0 && next < filteredIncidents.value.length) {
		selectedIncidentIndex.value = next;
	}
}

// Clear a stale selectedIncidentIndex when facet changes shrink filteredIncidents
watch(filteredIncidents, (list): void => {
	if (
		selectedIncidentIndex.value !== null &&
		selectedIncidentIndex.value >= list.length
	) {
		selectedIncidentIndex.value = null;
	}
});
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
				<template v-else-if="activeView === 'incidents'">
					<IncidentStack
						:incidents="incidents"
						:facet-state="facetState"
						:exchanges="filteredExchanges"
						@open-incident="onOpenIncident"
					/>
					<IncidentModal
						v-if="selectedIncidentIndex !== null"
						:incident="filteredIncidents[selectedIncidentIndex]!"
						:exchanges="state.result.exchanges"
						:facet-state="facetState"
						:index="selectedIncidentIndex"
						:total="filteredIncidents.length"
						:slow-ms="facetState.slowMs"
						@close="onCloseIncident"
						@navigate="onNavigateIncident"
					/>
				</template>
				<p v-else-if="activeView === 'minimap'">
					Minimap view — placeholder
				</p>
				<p v-else-if="activeView === 'oidtree'">
					OID Tree view — placeholder
				</p>
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
