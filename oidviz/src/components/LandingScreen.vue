<script setup lang="ts">
import { ref } from 'vue'
import type { AppState } from '../lib/model'

const props = defineProps<{ appState: AppState }>()
const emit = defineEmits<{ 'file-selected': [buffer: ArrayBuffer] }>()

const isDragging = ref(false)
const fileInputRef = ref<HTMLInputElement | null>(null)

function openFilePicker() {
  fileInputRef.value?.click()
}

function onFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  isDragging.value = false
  file.arrayBuffer().then(buf => emit('file-selected', buf))
}

function onDrop(event: DragEvent) {
  isDragging.value = false
  const file = event.dataTransfer?.files[0]
  if (!file) return
  // Only accept .oidtrace.jsonl.gz files
  if (!file.name.endsWith('.oidtrace.jsonl.gz')) return
  file.arrayBuffer().then(buf => emit('file-selected', buf))
}
</script>

<template>
  <div class="landing-root">
    <!-- Error state -->
    <div v-if="appState.phase === 'error'" role="alert" class="error-message">
      {{ appState.message }}
    </div>

    <!-- Drop zone -->
    <div
      class="drop-zone"
      :class="{ 'drag-over': isDragging }"
      role="region"
      aria-label="File drop zone"
      tabindex="0"
      @keydown.enter="openFilePicker"
      @keydown.space.prevent="openFilePicker"
      @dragover.prevent="isDragging = true"
      @dragleave="isDragging = false"
      @drop.prevent="onDrop"
    >
      <div v-if="appState.phase === 'loading'" class="loading-state">
        <div class="spinner" aria-hidden="true"></div>
        <span>Parsing trace file…</span>
      </div>
      <div v-else class="drop-content">
        <div class="drop-icon" aria-hidden="true">📂</div>
        <p>Drop a <code>.oidtrace.jsonl.gz</code> file here</p>
        <p class="drop-hint">or</p>
        <button class="open-btn" @click="openFilePicker">Browse files</button>
      </div>
    </div>

    <input
      ref="fileInputRef"
      type="file"
      accept=".oidtrace.jsonl.gz"
      style="display:none"
      @change="onFileChange"
    />
  </div>
</template>

<style scoped>
.landing-root {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  gap: 1rem;
  padding: 2rem;
}

.error-message {
  color: var(--err);
  background: color-mix(in srgb, var(--err) 10%, transparent);
  border: 1px solid var(--err);
  border-radius: 6px;
  padding: 0.75rem 1rem;
  max-width: 480px;
  width: 100%;
  text-align: center;
}

.drop-zone {
  border: 2px dashed var(--border);
  border-radius: 12px;
  padding: 3rem 2rem;
  max-width: 480px;
  width: 100%;
  text-align: center;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
  background: var(--surface);
}

.drop-zone:focus {
  outline: 2px solid var(--primary);
  outline-offset: 2px;
}

.drop-zone.drag-over {
  border-color: var(--primary);
  background: color-mix(in srgb, var(--primary) 8%, var(--surface));
}

.drop-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.5rem;
}

.drop-icon {
  font-size: 2.5rem;
}

.drop-hint {
  color: var(--text-muted);
  font-size: 0.875rem;
}

.open-btn {
  margin-top: 0.5rem;
  padding: 0.5rem 1.25rem;
  border: 1px solid var(--primary);
  background: var(--primary);
  color: white;
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.875rem;
}

.open-btn:hover {
  opacity: 0.9;
}

.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.75rem;
  color: var(--text-muted);
}

.spinner {
  width: 32px;
  height: 32px;
  border: 3px solid var(--border);
  border-top-color: var(--primary);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
