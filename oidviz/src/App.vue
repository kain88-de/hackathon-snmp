<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue';
import FindingsByCategory from './components/FindingsByCategory.vue';
import LandingScreen from './components/LandingScreen.vue';
import Sidebar from './components/Sidebar.vue';
import { matchesFacets } from './lib/filters.ts';
import { buildIncidents } from './lib/incidentStack.ts';
import type { ActiveView, AppState, FacetState, ParseResult, WorkerResponse } from './lib/model.ts';
import { autoExpand, buildTrie, flatten, rollup } from './lib/oidTrie.ts';

// State machine
const appState = ref<AppState>({ phase: 'landing' });
const darkMode = ref(false);
const activeView = ref<ActiveView>('findings');
const facetState = ref<FacetState>({ corr: 'any', perf: 'any', retryOnly: false, slowMs: 1000 });

// Worker
let worker: Worker | null = null;

const initWorker = (): void => {
  worker = new Worker(new URL('lib/parser.worker.ts', import.meta.url), { type: 'module' });
  worker.addEventListener('message', (event: MessageEvent): void => {
    const response = event.data as WorkerResponse;
    if (response.type === 'result') {
      appState.value = { phase: 'viewer', result: response.data };
      return;
    }
    appState.value = { message: response.message, phase: 'error' };
  });
};

// Computed from ParseResult
const parseResult = computed<ParseResult | null>(() => {
  if (appState.value.phase !== 'viewer') {
    return null;
  }
  return appState.value.result;
});

const filteredExchanges = computed(() => {
  const result = parseResult.value;
  if (!result) {
    return [];
  }
  return result.exchanges.filter((ex) => matchesFacets(ex, facetState.value));
});

// Incidents built from FULL list (not filtered)
const incidents = computed(() => {
  const result = parseResult.value;
  if (!result) {
    return [];
  }
  return buildIncidents(result.exchanges, facetState.value.slowMs);
});

// OidRoot: full rebuild on facet change
const oidFlatRows = computed(() => {
  const root = buildTrie(filteredExchanges.value);
  rollup(root, facetState.value.slowMs);
  autoExpand(root);
  return flatten(root);
});

// File handling — called by LandingScreen (wired in next task)
const handleFileSelected = (buffer: ArrayBuffer): void => {
  appState.value = { phase: 'loading' };
  if (!worker) {
    initWorker();
  }
  if (worker) {
    worker.postMessage({ buffer, type: 'parse' }, [buffer]);
  }
};

// Dark mode
const setTheme = (isDark: boolean): void => {
  let theme = '';
  if (isDark) {
    theme = 'dark';
  }
  document.documentElement.dataset.theme = theme;
};

// Called by Sidebar (wired in next task)
const toggleDarkMode = (): void => {
  darkMode.value = !darkMode.value;
  setTheme(darkMode.value);
};

const handleFacetChange = (patch: Partial<FacetState>): void => {
  const current = facetState.value;
  facetState.value = {
    corr: patch.corr ?? current.corr,
    perf: patch.perf ?? current.perf,
    retryOnly: patch.retryOnly ?? current.retryOnly,
    slowMs: patch.slowMs ?? current.slowMs,
  };
};

const handleViewChange = (view: ActiveView): void => {
  activeView.value = view;
};

const handleFocusExchange = (_seq: number): void => {
  activeView.value = 'minimap';
};

onMounted(() => {
  darkMode.value = globalThis.matchMedia('(prefers-color-scheme: dark)').matches;
  setTheme(darkMode.value);
  initWorker();
});

onUnmounted(() => {
  if (worker) {
    worker.terminate();
  }
});
</script>

<template>
  <div class="app-layout">
    <Sidebar
      :appState="appState"
      :result="parseResult"
      :facetState="facetState"
      :activeView="activeView"
      :darkMode="darkMode"
      @file-selected="handleFileSelected"
      @fixture-selected="handleFileSelected"
      @view-change="handleViewChange"
      @facet-change="handleFacetChange"
      @toggle-dark-mode="toggleDarkMode"
    />
    <main class="main-content">
      <LandingScreen
        v-if="appState.phase === 'landing' || appState.phase === 'loading' || appState.phase === 'error'"
        :appState="appState"
        @file-selected="handleFileSelected"
      />
      <div v-else-if="appState.phase === 'viewer'">
        <FindingsByCategory
          v-if="activeView === 'findings'"
          :exchanges="filteredExchanges"
          :facetState="facetState"
          @focus-exchange="handleFocusExchange"
        />
        <div v-else-if="activeView === 'incidents'">
          Incidents placeholder
          <!-- incidents passed here in next task -->
        </div>
        <div v-else-if="activeView === 'minimap'">
          Minimap placeholder
          <!-- oidFlatRows passed here in next task -->
        </div>
        <div v-else-if="activeView === 'oidtree'">OID Tree placeholder</div>
      </div>
    </main>
  </div>
</template>
