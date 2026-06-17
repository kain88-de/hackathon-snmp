<script setup lang="ts">
import { ref } from 'vue';
import type { ActiveView, AppState, FacetState, ParseResult } from '../lib/model.ts';

const props = defineProps<{
  appState: AppState;
  result: ParseResult | null;
  facetState: FacetState;
  activeView: ActiveView;
  darkMode: boolean;
}>();

const emit = defineEmits<{
  'file-selected': [buffer: ArrayBuffer];
  'fixture-selected': [buffer: ArrayBuffer];
  'view-change': [view: ActiveView];
  'facet-change': [patch: Partial<FacetState>];
  'toggle-dark-mode': [];
}>();

const MS_PER_SECOND = 1000;
const MIN_THRESHOLD_SECONDS = 0;
const NO_FILES = 0;

const FIXTURES = ['trace-5k', 'trace-50k', 'trace-100k', 'trace-focused'] as const;

const VIEWS: { id: ActiveView; label: string }[] = [
  { id: 'findings', label: 'Findings' },
  { id: 'incidents', label: 'Incident Stack' },
  { id: 'minimap', label: 'Minimap' },
  { id: 'oidtree', label: 'OID Tree' },
];

const PERF_OPTIONS: { label: string; value: FacetState['perf'] }[] = [
  { label: 'Any', value: 'any' },
  { label: 'Fast', value: 'fast' },
  { label: 'Slow', value: 'slow' },
  { label: 'Timeout', value: 'timeout' },
];

const fileInput = ref<HTMLInputElement | null>(null);

const openFilePicker = (): void => {
  if (fileInput.value !== null) {
    fileInput.value.click();
  }
};

const onFileChange = (event: Event): void => {
  const input = event.target as HTMLInputElement;
  if (input.files === null || input.files.length === NO_FILES) {
    return;
  }
  const [file] = input.files;
  if (!file) {
    return;
  }
  file
    .arrayBuffer()
    .then((buffer) => {
      emit('file-selected', buffer);
    })
    .catch(() => {
      // Ignore read errors
    });
};

const fetchFixture = (name: string): void => {
  fetch(`/../traceformat/examples/${name}.oidtrace.jsonl.gz`)
    .then((response) => response.arrayBuffer())
    .then((buffer) => {
      emit('fixture-selected', buffer);
    })
    .catch(() => {
      // Ignore fetch errors
    });
};

const onSlowThresholdChange = (event: Event): void => {
  const input = event.target as HTMLInputElement;
  const seconds = Number.parseFloat(input.value);
  if (!Number.isNaN(seconds) && seconds > MIN_THRESHOLD_SECONDS) {
    emit('facet-change', { slowMs: seconds * MS_PER_SECOND });
  }
};
</script>

<template>
  <aside
    class="sidebar"
    aria-label="OIDviz controls"
  >
    <div class="sidebar-header">
      <h1 class="sidebar-title">
        OIDviz
      </h1>
      <button
        type="button"
        aria-label="Toggle dark mode"
        @click="emit('toggle-dark-mode')"
      >
        {{ props.darkMode ? '☀️' : '🌙' }}
      </button>
    </div>

    <section aria-labelledby="file-section-label">
      <h2
        id="file-section-label"
        class="sidebar-section-title"
      >
        Load Trace
      </h2>
      <button
        type="button"
        @click="openFilePicker"
      >
        Open File
      </button>
      <input
        ref="fileInput"
        type="file"
        accept=".gz"
        style="display: none"
        @change="onFileChange"
      >

      <div class="fixture-buttons">
        <button
          v-for="fixture in FIXTURES"
          :key="fixture"
          type="button"
          @click="fetchFixture(fixture)"
        >
          {{ fixture }}
        </button>
      </div>
    </section>

    <nav aria-label="Views">
      <button
        v-for="view in VIEWS"
        :key="view.id"
        type="button"
        :aria-current="props.activeView === view.id ? 'page' : undefined"
        @click="emit('view-change', view.id)"
      >
        {{ view.label }}
      </button>
    </nav>

    <section
      v-if="props.appState.phase === 'viewer'"
      aria-labelledby="facet-section-label"
    >
      <h2
        id="facet-section-label"
        class="sidebar-section-title"
      >
        Filters
      </h2>

      <fieldset>
        <legend>Performance</legend>
        <label
          v-for="opt in PERF_OPTIONS"
          :key="opt.value"
        >
          <input
            type="radio"
            name="perf"
            :value="opt.value"
            :checked="props.facetState.perf === opt.value"
            @change="emit('facet-change', { perf: opt.value })"
          >
          {{ opt.label }}
        </label>
      </fieldset>

      <fieldset>
        <legend>Correctness</legend>
        <label>
          <input
            type="radio"
            name="corr"
            value="any"
            :checked="props.facetState.corr === 'any'"
            @change="emit('facet-change', { corr: 'any' })"
          >
          Any
        </label>
        <label>
          <input
            type="radio"
            name="corr"
            value="violations"
            :checked="props.facetState.corr === 'violations'"
            @change="emit('facet-change', { corr: 'violations' })"
          >
          Violations only
        </label>
      </fieldset>

      <label>
        <input
          type="checkbox"
          :checked="props.facetState.retryOnly"
          @change="emit('facet-change', { retryOnly: !props.facetState.retryOnly })"
        >
        Retries only
      </label>

      <label for="slow-threshold">Slow threshold (s)</label>
      <input
        id="slow-threshold"
        type="number"
        min="0.1"
        step="0.1"
        :value="props.facetState.slowMs / MS_PER_SECOND"
        @change="onSlowThresholdChange"
      >

      <div class="sidebar-stats">
        <div>Exchanges: {{ props.appState.result.exchanges.length }}</div>
      </div>
    </section>

    <div
      aria-live="polite"
      class="truncation-warning"
    >
      <span v-if="result !== null && result.truncated">&#x26A0; Trace file was truncated</span>
    </div>
  </aside>
</template>
