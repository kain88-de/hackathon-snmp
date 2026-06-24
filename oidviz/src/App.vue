<script setup lang="ts">
import { ref } from "vue";
import LandingScreen from "./components/LandingScreen.vue";
import type {
	ActiveView,
	AppState,
	FacetState,
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
</script>

<template>
	<div id="app" :data-phase="state.phase">
		<LandingScreen
			v-if="state.phase === 'landing' || state.phase === 'loading'"
			:app-state="state"
			@file-selected="onFileSelected"
		/>

		<div v-else-if="state.phase === 'viewer'" class="viewer-root">
			<nav class="viewer-nav">
				<button
					:class="{ active: activeView === 'findings' }"
					@click="activeView = 'findings'"
				>
					Findings
				</button>
				<button
					:class="{ active: activeView === 'incidents' }"
					@click="activeView = 'incidents'"
				>
					Incidents
				</button>
				<button
					:class="{ active: activeView === 'minimap' }"
					@click="activeView = 'minimap'"
				>
					Minimap
				</button>
				<button
					:class="{ active: activeView === 'oidtree' }"
					@click="activeView = 'oidtree'"
				>
					OID Tree
				</button>
			</nav>

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
	flex-direction: column;
	height: 100%;
}

.viewer-nav {
	display: flex;
	gap: 8px;
	padding: 12px 16px;
	border-bottom: 1px solid var(--color-border);
}

.viewer-nav button {
	padding: 6px 14px;
	border: 1px solid var(--color-border);
	border-radius: 4px;
	background: var(--color-surface);
	color: var(--color-text);
	cursor: pointer;
}

.viewer-nav button.active {
	background: var(--color-primary);
	border-color: var(--color-primary);
	color: #fff;
}

.viewer-content {
	padding: 24px;
}

.error-page {
	padding: 40px;
	color: var(--dim-timeout);
}
</style>
