<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import IncidentStack from './components/IncidentStack.vue'
import LandingScreen from './components/LandingScreen.vue'
import Sidebar from './components/Sidebar.vue'
import { buildIncidents } from './lib/incidentStack'
import type { AppState, FilterState, ParseResult, WorkerRequest, WorkerResponse } from './lib/model'
import { autoExpand, buildTrie, flatten, rollup } from './lib/oidTrie'

const appState = ref<AppState>({ phase: 'landing' })
const filterState = ref<FilterState>({
  slow: true,
  violations: true,
  retries: true,
  timeouts: false,
  slowMs: 1000,
})
const activeView = ref<'incidents' | 'minimap' | 'oidtree'>('incidents')
const darkMode = ref(false)

onMounted(() => {
  darkMode.value = window.matchMedia('(prefers-color-scheme: dark)').matches
  updateTheme()

  worker = new Worker(new URL('./lib/parser.worker.ts', import.meta.url), { type: 'module' })
  worker.onmessage = (event: MessageEvent) => {
    const msg = event.data as WorkerResponse
    switch (msg.type) {
      case 'result':
        appState.value = { phase: 'viewer', result: msg.data }
        break
      case 'error':
        appState.value = { phase: 'error', message: msg.message }
        break
    }
  }
})

function updateTheme() {
  document.documentElement.dataset.theme = darkMode.value ? 'dark' : ''
}

function toggleDarkMode() {
  darkMode.value = !darkMode.value
  updateTheme()
}

let worker: Worker | null = null

onUnmounted(() => {
  worker?.terminate()
})

function handleFile(buffer: ArrayBuffer) {
  appState.value = { phase: 'loading' }
  const req: WorkerRequest = { type: 'parse', buffer }
  worker?.postMessage(req, [buffer])
}

const viewerResult = computed<ParseResult | null>(() => {
  if (appState.value.phase === 'viewer') return appState.value.result
  return null
})

const incidents = computed(() => {
  const result = viewerResult.value
  if (!result) return []
  return buildIncidents(result.exchanges, filterState.value.slowMs)
})

const flatRows = computed(() => {
  const result = viewerResult.value
  if (!result) return []
  const root = buildTrie(result.exchanges, filterState.value)
  rollup(root, filterState.value.slowMs)
  autoExpand(root)
  return flatten(root)
})

// Suppress unused variable warnings for computed values used by child components
void flatRows
</script>

<template>
  <Sidebar
    :appState="appState"
    :result="viewerResult"
    :filterState="filterState"
    :activeView="activeView"
    :darkMode="darkMode"
    @file-selected="buf => handleFile(buf)"
    @fixture-selected="buf => handleFile(buf)"
    @view-change="view => (activeView = view)"
    @filter-change="patch => (filterState = { ...filterState, ...patch })"
    @toggle-dark-mode="toggleDarkMode"
  />
  <main class="main-area">
    <LandingScreen
      v-if="appState.phase !== 'viewer'"
      :appState="appState"
      @file-selected="handleFile"
    />
    <!-- Viewer state -->
    <template v-if="appState.phase === 'viewer'">
      <div class="view-area">
        <IncidentStack
          v-if="activeView === 'incidents'"
          :incidents="incidents"
          :filterState="filterState"
          :exchanges="viewerResult?.exchanges ?? []"
        />
        <div v-else-if="activeView === 'minimap'">Minimap view (placeholder)</div>
        <div v-else>OID Tree view (placeholder)</div>
      </div>
    </template>
  </main>
</template>
