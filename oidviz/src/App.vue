<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import IncidentStack from './components/IncidentStack.vue'
import LandingScreen from './components/LandingScreen.vue'
import MinimapDetail from './components/MinimapDetail.vue'
import OidTree from './components/OidTree.vue'
import Sidebar from './components/Sidebar.vue'
import { buildIncidents } from './lib/incidentStack'
import type { AppState, FilterState, FlatRow, ParseResult, TrieNode, WorkerRequest, WorkerResponse } from './lib/model'
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

let oidRoot: TrieNode | null = null

const flatRows = ref<FlatRow[]>([])

watch(
  [viewerResult, filterState],
  () => {
    const result = viewerResult.value
    if (!result) { flatRows.value = []; return }
    const root = buildTrie(result.exchanges, filterState.value)
    rollup(root, filterState.value.slowMs)
    autoExpand(root)
    oidRoot = root
    flatRows.value = flatten(root)
  },
  { deep: false, immediate: true }
)

function reflattenOidTree() {
  if (oidRoot) flatRows.value = flatten(oidRoot)
}

function collapseAllNodes() {
  if (!oidRoot) return
  collapseAll(oidRoot)
  flatRows.value = flatten(oidRoot)
}

function collapseAll(node: TrieNode) {
  node.expanded = false
  for (const child of node.children.values()) collapseAll(child)
}

const oidMatchingCount = computed(() => {
  if (!oidRoot) return 0
  return countLeaves(oidRoot)
})

function countLeaves(node: TrieNode): number {
  let count = node.leaves.length
  for (const child of node.children.values()) count += countLeaves(child)
  return count
}
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
    <h1 class="sr-only">OIDviz</h1>
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
        <MinimapDetail
          v-else-if="activeView === 'minimap'"
          :exchanges="viewerResult?.exchanges ?? []"
          :filterState="filterState"
        />
        <OidTree
          v-else-if="activeView === 'oidtree'"
          :flatRows="flatRows"
          :filterState="filterState"
          :matchingCount="oidMatchingCount"
          @reflatten="reflattenOidTree"
          @collapse-all="collapseAllNodes"
        />
      </div>
    </template>
  </main>
</template>
