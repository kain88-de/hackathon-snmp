<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
// biome-ignore lint/correctness/noUnusedImports: used in <template> — Biome cannot cross-reference script setup bindings with template
import AppSidebar from './components/AppSidebar.vue';
// biome-ignore lint/correctness/noUnusedImports: used in <template>
import FindingsByCategory from './components/FindingsByCategory.vue';
// biome-ignore lint/correctness/noUnusedImports: used in <template>
import IncidentModal from './components/IncidentModal.vue';
// biome-ignore lint/correctness/noUnusedImports: used in <template>
import IncidentStack from './components/IncidentStack.vue';
// biome-ignore lint/correctness/noUnusedImports: used in <template>
import LandingScreen from './components/LandingScreen.vue';
// biome-ignore lint/correctness/noUnusedImports: used in <template>
import MinimapDetail from './components/MinimapDetail.vue';
// biome-ignore lint/correctness/noUnusedImports: used in <template>
import OidTree from './components/OidTree.vue';
import { matchesFacets } from './lib/filters.ts';
import { buildIncidents } from './lib/incidentStack.ts';
import type {
  ActiveView,
  AppState,
  FacetState,
  FlatRow,
  ParseResult,
  TrieNode,
  WorkerResponse,
} from './lib/model.ts';
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

// OID trie — mutable root kept as ref so expand/collapse can re-flatten without full rebuild
const oidRoot = ref<TrieNode | null>(null);
const oidFlatRows = ref<FlatRow[]>([]);

const rebuildTrie = (): void => {
  const root = buildTrie(filteredExchanges.value);
  rollup(root, facetState.value.slowMs);
  autoExpand(root);
  oidRoot.value = root;
  oidFlatRows.value = flatten(root);
};

const collapseNode = (node: TrieNode): void => {
  node.expanded = false;
  for (const child of node.children.values()) {
    collapseNode(child);
  }
};

const handleReflatten = (): void => {
  if (!oidRoot.value) {
    return;
  }
  oidFlatRows.value = flatten(oidRoot.value);
};

const handleCollapseAll = (): void => {
  const root = oidRoot.value;
  if (!root) {
    return;
  }
  collapseNode(root);
  oidFlatRows.value = flatten(root);
};

watch(
  [filteredExchanges, (): number => facetState.value.slowMs],
  (): void => {
    rebuildTrie();
  },
  { immediate: true },
);

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

const modalIncidentIndex = ref<number | null>(null);
const openIncidentModal = (index: number): void => {
  modalIncidentIndex.value = index;
};
const MODAL_FIRST = 0;
const MODAL_LAST_OFFSET = 1;
const navigateModal = (delta: number): void => {
  if (modalIncidentIndex.value === null) {
    return;
  }
  modalIncidentIndex.value = Math.max(
    MODAL_FIRST,
    Math.min(incidents.value.length - MODAL_LAST_OFFSET, modalIncidentIndex.value + delta),
  );
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
    <AppSidebar
      :app-state="appState"
      :result="parseResult"
      :facet-state="facetState"
      :active-view="activeView"
      :dark-mode="darkMode"
      @file-selected="handleFileSelected"
      @fixture-selected="handleFileSelected"
      @view-change="handleViewChange"
      @facet-change="handleFacetChange"
      @toggle-dark-mode="toggleDarkMode"
    />
    <main class="main-content">
      <LandingScreen
        v-if="appState.phase === 'landing' || appState.phase === 'loading' || appState.phase === 'error'"
        :app-state="appState"
        @file-selected="handleFileSelected"
      />
      <div v-else-if="appState.phase === 'viewer'">
        <FindingsByCategory
          v-if="activeView === 'findings'"
          :exchanges="filteredExchanges"
          :facet-state="facetState"
          @focus-exchange="handleFocusExchange"
        />
        <IncidentStack
          v-else-if="activeView === 'incidents'"
          :incidents="incidents"
          :facet-state="facetState"
          :exchanges="parseResult?.exchanges ?? []"
          @open-incident="openIncidentModal"
        />
        <MinimapDetail
          v-else-if="activeView === 'minimap'"
          :exchanges="filteredExchanges"
          :facet-state="facetState"
          @focus-exchange="handleFocusExchange"
        />
        <OidTree
          v-else-if="activeView === 'oidtree'"
          :flat-rows="oidFlatRows"
          :facet-state="facetState"
          :matching-count="filteredExchanges.length"
          @reflatten="handleReflatten"
          @collapse-all="handleCollapseAll"
        />
      </div>
    </main>
  </div>
  <IncidentModal
    v-if="modalIncidentIndex !== null"
    :incident="incidents[modalIncidentIndex]!"
    :exchanges="parseResult?.exchanges ?? []"
    :index="modalIncidentIndex"
    :total="incidents.length"
    @close="modalIncidentIndex = null"
    @navigate="navigateModal"
  />
</template>
