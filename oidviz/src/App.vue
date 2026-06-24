<script setup lang="ts">
import { ref } from "vue";
import LandingScreen from "./components/LandingScreen.vue";
import Sidebar from "./components/Sidebar.vue";
import type {
	ActiveView,
	AppState,
	FacetState,
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
</script>

<template>
	<div id="app" :data-phase="state.phase">
		<LandingScreen
			v-if="state.phase === 'landing' || state.phase === 'loading'"
			:app-state="state"
			@file-selected="onFileSelected"
		/>

		<div v-else-if="state.phase === 'viewer'" class="viewer-root">
			<Sidebar
				:app-state="state"
				:result="currentResult()"
				:facet-state="facetState"
				:active-view="activeView"
				@file-selected="onFileSelected"
				@view-change="onViewChange"
				@facet-change="onFacetChange"
			/>

			<div class="viewer-content">
				<p v-if="activeView === 'findings'">
					Findings view — {{ state.result.exchanges.length }} exchanges
					(perf: {{ facetState.perf }}, slowMs:
					{{ facetState.slowMs }})
				</p>
				<p v-else-if="activeView === 'incidents'">
					Incidents view — placeholder
				</p>
				<p v-else-if="activeView === 'minimap'">
					Minimap view — placeholder
				</p>
				<p v-else-if="activeView === 'oidtree'">
					OID Tree view — placeholder
				</p>
			</div>
		</div>

		<div v-else-if="state.phase === 'error'" class="error-page" role="alert">
			<p>Error: {{ state.message }}</p>
		</div>
	</div>
</template>

<style scoped>
.viewer-root {
	display: flex;
	flex-direction: row;
	height: 100%;
}

.viewer-content {
	flex: 1;
	padding: 24px;
	overflow: auto;
}

.error-page {
	padding: 40px;
	color: var(--dim-timeout);
}
</style>
