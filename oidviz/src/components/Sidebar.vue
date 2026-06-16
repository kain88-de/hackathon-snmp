<script setup lang="ts">
import { computed, ref } from 'vue';
import type { AppState, FilterState, ParseResult } from '../lib/model';

const props = defineProps<{
  appState: AppState;
  result: ParseResult | null;
  filterState: FilterState;
  activeView: 'incidents' | 'minimap' | 'oidtree';
  darkMode: boolean;
}>();

const emit = defineEmits<{
  'file-selected': [buffer: ArrayBuffer];
  'fixture-selected': [buffer: ArrayBuffer];
  'view-change': [view: 'incidents' | 'minimap' | 'oidtree'];
  'filter-change': [patch: Partial<FilterState>];
  'toggle-dark-mode': [];
}>();

const fileInputRef = ref<HTMLInputElement | null>(null);

function openFilePicker() {
  fileInputRef.value?.click();
}

function onFileChange(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) {
    return;
  }
  file.arrayBuffer().then((buf) => emit('file-selected', buf));
}

function loadFixture(name: string) {
  fetch(`/tools/fixtures/${name}.oidtrace.jsonl.gz`)
    .then((response) => response.arrayBuffer())
    .then((buf) => {
      emit('fixture-selected', buf);
    })
    .catch(() => {
      /* ignore fetch errors */
    });
}

function onSlowChange(e: Event) {
  emit('filter-change', { slow: (e.target as HTMLInputElement).checked });
}

const MS_PER_S = 1000;

function onSlowMsChange(e: Event) {
  const val = Number.parseFloat((e.target as HTMLInputElement).value);
  if (!Number.isNaN(val)) {
    emit('filter-change', { slowMs: val * MS_PER_S });
  }
}

const sysDescrLine1 = computed(() => {
  const descr = String(props.result?.systemInfo?.values?.sysDescr ?? '');
  return descr.split('\n')[0] ?? descr;
});

const sysDescrFull = computed(() => {
  return String(props.result?.systemInfo?.values?.sysDescr ?? '');
});

const sysObjectId = computed(() => {
  return String(props.result?.systemInfo?.values?.sysObjectID ?? '');
});

const CENTISECS_PER_SEC = 100;
const SECS_PER_DAY = 86_400;
const SECS_PER_HOUR = 3600;
const SECS_PER_MIN = 60;

const sysUpTimeFormatted = computed(() => {
  const raw = props.result?.systemInfo?.values?.sysUpTime;
  if (raw === null || raw === undefined) {
    return '';
  }
  // sysUpTime is in centiseconds (TimeTicks)
  const totalSecs = Math.floor(Number(raw) / CENTISECS_PER_SEC);
  const days = Math.floor(totalSecs / SECS_PER_DAY);
  const hours = Math.floor((totalSecs % SECS_PER_DAY) / SECS_PER_HOUR);
  const mins = Math.floor((totalSecs % SECS_PER_HOUR) / SECS_PER_MIN);
  const secs = totalSecs % SECS_PER_MIN;
  if (days > 0) {
    return `${days}d ${hours}h ${mins}m`;
  }
  if (hours > 0) {
    return `${hours}h ${mins}m ${secs}s`;
  }
  return `${mins}m ${secs}s`;
});

const totalViolations = computed(() => {
  const counts = props.result?.summary?.violation_counts;
  if (!counts) {
    return 0;
  }
  return Object.values(counts).reduce((sum, n) => sum + n, 0);
});

const durationFormatted = computed(() => {
  const at = props.result?.summary?.at;
  if (at === null || at === undefined) {
    return '';
  }
  const totalSecs = Math.floor(at);
  const days = Math.floor(totalSecs / SECS_PER_DAY);
  const hours = Math.floor((totalSecs % SECS_PER_DAY) / SECS_PER_HOUR);
  const mins = Math.floor((totalSecs % SECS_PER_HOUR) / SECS_PER_MIN);
  const secs = totalSecs % SECS_PER_MIN;
  if (days > 0) {
    return `${days}d ${hours}h ${mins}m`;
  }
  if (hours > 0) {
    return `${hours}h ${mins}m ${secs}s`;
  }
  return `${mins}m ${secs}s`;
});

const viewLabels: { [K in 'incidents' | 'minimap' | 'oidtree']: string } = {
  incidents: 'Incidents',
  minimap: 'Minimap',
  oidtree: 'OID Tree',
};
</script>

<template>
  <aside aria-label="Sidebar" aria-live="polite">
    <!-- Brand -->
    <header class="sidebar-section sidebar-brand">
      <span class="brand-name">OIDviz</span>
      <button class="icon-btn" :aria-pressed="darkMode" @click="emit('toggle-dark-mode')" aria-label="Toggle dark mode">
        {{ darkMode ? '☀️' : '🌙' }}
      </button>
    </header>

    <!-- Load -->
    <section class="sidebar-section">
      <button class="sidebar-btn" @click="openFilePicker">Open trace file…</button>
      <input ref="fileInputRef" type="file" accept=".oidtrace.jsonl.gz" style="display:none" @change="onFileChange" />
      <div class="fixture-list">
        <button class="fixture-btn" @click="loadFixture('trace-5k')">trace-5k</button>
        <button class="fixture-btn" @click="loadFixture('trace-50k')">trace-50k</button>
        <button class="fixture-btn" @click="loadFixture('trace-100k')">trace-100k</button>
        <button class="fixture-btn" @click="loadFixture('trace-focused')">trace-focused</button>
      </div>
    </section>

    <!-- Device -->
    <section v-if="result?.systemInfo" class="sidebar-section">
      <div class="section-title">Device</div>
      <div class="info-row">
        <span class="label">Description</span>
        <span class="value" :title="sysDescrFull">{{ sysDescrLine1 }}</span>
      </div>
      <div class="info-row">
        <span class="label">OID</span>
        <span class="value">{{ sysObjectID }}</span>
      </div>
      <div class="info-row">
        <span class="label">Uptime</span>
        <span class="value">{{ sysUpTimeFormatted }}</span>
      </div>
    </section>

    <!-- Walk info -->
    <section v-if="appState.phase === 'viewer'" class="sidebar-section">
      <div class="section-title">Walk</div>
      <div v-if="result?.header.label" class="info-row">
        <span class="label">Label</span>
        <span class="value">{{ result.header.label }}</span>
      </div>
      <div class="info-row">
        <span class="label">SNMP</span>
        <span class="value">{{ result?.header.snmp.version }}</span>
      </div>
      <div class="info-row">
        <span class="label">Start OID</span>
        <span class="value">{{ result?.header.settings.start_oid }}</span>
      </div>
      <div class="info-row">
        <span class="label">Exchanges</span>
        <span class="value">{{ result?.exchanges.length }}</span>
      </div>
      <div class="info-row">
        <span class="label">OIDs seen</span>
        <span class="value">{{ result?.summary?.oids_seen ?? '—' }}</span>
      </div>
      <div class="info-row">
        <span class="label">Duration</span>
        <span class="value">{{ durationFormatted || '—' }}</span>
      </div>
      <div class="info-row">
        <span class="label">Violations</span>
        <span class="value" :class="totalViolations > 0 ? 'violations-bad' : 'violations-ok'">{{ totalViolations }}</span>
      </div>
      <div class="info-row">
        <span class="label">End reason</span>
        <span class="value">{{ result?.summary?.end_reason ?? 'unknown' }}</span>
      </div>
      <div class="info-row">
        <span class="label">Parse time</span>
        <span class="value">{{ result?.parseMs.toFixed(0) }}ms</span>
      </div>
    </section>

    <!-- Views -->
    <section v-if="appState.phase === 'viewer'" class="sidebar-section">
      <div class="section-title">Views</div>
      <button
        v-for="view in (['incidents', 'minimap', 'oidtree'] as const)"
        :key="view"
        class="sidebar-btn"
        :class="{ active: activeView === view }"
        :aria-current="activeView === view ? 'page' : undefined"
        @click="emit('view-change', view)"
      >{{ viewLabels[view] }}</button>
    </section>

    <!-- Filters -->
    <section v-if="appState.phase === 'viewer'" class="sidebar-section">
      <div class="section-title">Filters</div>
      <label class="filter-row">
        <input type="checkbox" :checked="filterState.slow" @change="onSlowChange" />
        Slow &gt;
        <input type="number" :value="filterState.slowMs / 1000" @change="onSlowMsChange" min="0" step="0.1" class="threshold-input" />
        s
      </label>
      <label class="filter-row">
        <input type="checkbox" :checked="filterState.violations" @change="e => emit('filter-change', { violations: (e.target as HTMLInputElement).checked })" />
        Violations
      </label>
      <label class="filter-row">
        <input type="checkbox" :checked="filterState.retries" @change="e => emit('filter-change', { retries: (e.target as HTMLInputElement).checked })" />
        Retries
      </label>
      <label class="filter-row">
        <input type="checkbox" :checked="filterState.timeouts" @change="e => emit('filter-change', { timeouts: (e.target as HTMLInputElement).checked })" />
        Timeouts
      </label>
    </section>

    <!-- Walk config -->
    <section v-if="appState.phase === 'viewer'" class="sidebar-section">
      <div class="section-title">Walk config</div>
      <div class="info-row">
        <span class="label">Bulk size</span>
        <span class="value">{{ result?.header.settings.bulk_size }}</span>
      </div>
      <div class="info-row">
        <span class="label">Timeout</span>
        <span class="value">{{ result?.header.settings.timeout_s }}s</span>
      </div>
      <div class="info-row">
        <span class="label">Retries</span>
        <span class="value">{{ result?.header.settings.retries }}</span>
      </div>
      <div class="info-row">
        <span class="label">Start OID</span>
        <span class="value">{{ result?.header.settings.start_oid }}</span>
      </div>
      <div v-if="result?.header.settings.time_budget_s != null" class="info-row">
        <span class="label">Time budget</span>
        <span class="value">{{ result.header.settings.time_budget_s }}s</span>
      </div>
      <div v-if="result?.header.settings.resume_from != null" class="info-row">
        <span class="label">Resume from</span>
        <span class="value">{{ result.header.settings.resume_from }}</span>
      </div>
    </section>

    <!-- Truncation warning -->
    <div v-if="result?.truncated" class="truncation-warning" aria-live="polite" role="status">
      ⚠️ Trace file was truncated — data may be incomplete.
    </div>
  </aside>
</template>
