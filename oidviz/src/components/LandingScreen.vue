<script setup lang="ts">
import { ref } from 'vue';
import type { AppState } from '../lib/model.ts';

defineProps<{ appState: AppState }>();
const emit = defineEmits<{ 'file-selected': [buffer: ArrayBuffer] }>();

const isDragging = ref(false);
const fileInput = ref<HTMLInputElement | null>(null);

const readFile = (file: File): void => {
  file.arrayBuffer().then((buffer) => {
    emit('file-selected', buffer);
  });
};

const onDrop = (event: DragEvent): void => {
  isDragging.value = false;
  const transfer = event.dataTransfer;
  if (transfer) {
    const [file] = transfer.files;
    if (file) {
      readFile(file);
    }
  }
};

const onKeyDown = (event: KeyboardEvent): void => {
  if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault();
    if (fileInput.value) {
      fileInput.value.click();
    }
  }
};

const onFileChange = (event: Event): void => {
  const input = event.target as HTMLInputElement;
  const { files } = input;
  if (files) {
    const [file] = files;
    if (file) {
      readFile(file);
    }
  }
};
</script>

<template>
  <div class="landing-screen">
    <!-- Error display -->
    <div v-if="appState.phase === 'error'" role="alert" class="error-message">
      Error: {{ appState.message }}
    </div>

    <!-- Drop zone -->
    <div
      v-if="appState.phase === 'landing' || appState.phase === 'loading'"
      role="region"
      aria-label="File drop zone — drag a .oidtrace.jsonl.gz file here or press Enter to browse"
      tabindex="0"
      class="drop-zone"
      :class="{ 'drop-zone--active': isDragging, 'drop-zone--loading': appState.phase === 'loading' }"
      @dragover.prevent="isDragging = true"
      @dragleave="isDragging = false"
      @drop.prevent="onDrop"
      @keydown="onKeyDown"
    >
      <div v-if="appState.phase === 'loading'" class="loading-indicator">
        <span class="sr-only">Loading trace file...</span>
        <!-- visual loading spinner -->
        <div class="spinner" aria-hidden="true"></div>
        <p>Parsing trace file...</p>
      </div>
      <div v-else class="drop-zone-content">
        <p>Drag a <code>.oidtrace.jsonl.gz</code> file here</p>
        <p>or press <kbd>Enter</kbd> to browse</p>
      </div>
    </div>

    <!-- Hidden file input -->
    <input
      ref="fileInput"
      type="file"
      accept=".gz"
      style="display:none"
      @change="onFileChange"
    />
  </div>
</template>

<style scoped>
.landing-screen {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  padding: 2rem;
  gap: 1rem;
}

.drop-zone {
  border: 2px dashed var(--color-border);
  border-radius: 8px;
  padding: 3rem;
  text-align: center;
  cursor: pointer;
  min-width: 400px;
  min-height: 200px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: border-color 0.2s;
}

.drop-zone:focus {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

.drop-zone--active {
  border-color: var(--color-primary);
  background: var(--color-surface);
}

.error-message {
  color: var(--color-err);
  padding: 1rem;
  border: 1px solid var(--color-err);
  border-radius: 4px;
}

.spinner {
  width: 32px;
  height: 32px;
  border: 3px solid var(--color-border);
  border-top-color: var(--color-primary);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
