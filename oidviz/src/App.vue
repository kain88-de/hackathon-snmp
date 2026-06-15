<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
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

const errorMessage = computed<string | null>(() => {
  if (appState.value.phase === 'error') return appState.value.message
  return null
})

const fileInput = ref<HTMLInputElement | null>(null)

function openFilePicker() {
  fileInput.value?.click()
}

function onFileInput(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  file.arrayBuffer().then(handleFile)
}

// Suppress unused variable warnings for computed values used by child components
void incidents
void flatRows
void toggleDarkMode
void activeView
</script>

<template>
  <aside class="sidebar">
    <!-- Sidebar placeholder for now — will be replaced in Task 9 -->
    <div class="sidebar-brand">OIDviz</div>
  </aside>
  <main class="main-area">
    <!-- Landing / Loading / Error state -->
    <template v-if="appState.phase === 'landing' || appState.phase === 'loading' || appState.phase === 'error'">
      <div class="landing-placeholder">
        <span v-if="appState.phase === 'loading'">Parsing…</span>
        <span v-else-if="appState.phase === 'error'" role="alert">{{ errorMessage }}</span>
        <span v-else>Drop a .oidtrace.jsonl.gz file here</span>
        <input type="file" accept=".oidtrace.jsonl.gz" style="display:none" ref="fileInput" @change="onFileInput" />
        <button @click="openFilePicker">Open file</button>
      </div>
    </template>
    <!-- Viewer state -->
    <template v-if="appState.phase === 'viewer'">
      <div class="view-area">
        <div v-if="activeView === 'incidents'">Incidents view (placeholder)</div>
        <div v-else-if="activeView === 'minimap'">Minimap view (placeholder)</div>
        <div v-else>OID Tree view (placeholder)</div>
      </div>
    </template>
  </main>
</template>
