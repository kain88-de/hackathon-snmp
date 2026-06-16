<script setup lang="ts">
import { nextTick, onMounted, ref, useId } from 'vue';
import type { DomainExchange, Incident } from '../lib/model';

const props = defineProps<{
  incident: Incident;
  exchanges: DomainExchange[];
  index: number;
  total: number;
}>();

const emit = defineEmits<{
  close: [];
  navigate: [delta: number];
}>();

const headingRef = ref<HTMLElement | null>(null);
const headingId = useId();

onMounted(() => {
  nextTick(() => headingRef.value?.focus());
});

function truncateOid(oid: string): string {
  if (oid.length <= 50) return oid;
  return `${oid.slice(0, 47)}…`;
}
</script>

<template>
  <div
    class="modal-overlay"
    @keydown.escape="emit('close')"
    @click.self="emit('close')"
  >
    <div
      class="modal-panel"
      role="dialog"
      aria-modal="true"
      :aria-labelledby="headingId"
    >
      <div class="modal-header">
        <h2 :id="headingId" ref="headingRef" tabindex="-1">
          Incident {{ props.index + 1 }} of {{ props.total }} — {{ props.incident.region }}
          (seq {{ props.incident.startSeq }}–{{ props.incident.endSeq }})
        </h2>
        <div class="modal-nav">
          <button @click="emit('navigate', -1)" :disabled="props.index === 0" aria-label="Previous incident">‹</button>
          <button @click="emit('navigate', 1)" :disabled="props.index === props.total - 1" aria-label="Next incident">›</button>
          <button @click="emit('close')" aria-label="Close">×</button>
        </div>
      </div>

      <dl class="stats-grid">
        <div><dt>Peak RTT</dt><dd>{{ props.incident.peakRtt.toFixed(0) }}ms</dd></div>
        <div><dt>Timeouts</dt><dd>{{ props.incident.timeoutCount }}</dd></div>
        <div><dt>Retries</dt><dd>{{ props.incident.retryCount }}</dd></div>
        <div><dt>Exchanges</dt><dd>{{ props.incident.members.length }}</dd></div>
        <div><dt>Violations</dt><dd>{{ props.incident.violationTypes.size > 0 ? [...props.incident.violationTypes].join(', ') : '—' }}</dd></div>
      </dl>

      <div class="exchange-table-wrapper">
        <table class="exchange-table">
          <thead>
            <tr><th>Seq</th><th>OID</th><th>RTT</th><th>Flag</th></tr>
          </thead>
          <tbody>
            <tr v-for="idx in props.incident.members" :key="idx">
              <td>{{ props.exchanges[idx]?.seq }}</td>
              <td>
                <span
                  :title="props.exchanges[idx]?.requestOid"
                  class="oid-cell"
                >{{ truncateOid(props.exchanges[idx]?.requestOid ?? '') }}</span>
              </td>
              <td>{{ props.exchanges[idx]?.rtt.toFixed(0) }}ms</td>
              <td>
                <span v-if="props.exchanges[idx]?.isTimeout" class="flag timeout">timeout</span>
                <span
                  v-for="v in (props.exchanges[idx]?.violations ?? [])"
                  :key="v"
                  class="flag violation"
                >{{ v }}</span>
                <span
                  v-if="(props.exchanges[idx]?.attemptCount ?? 1) > 1"
                  class="flag retry"
                >retry×{{ (props.exchanges[idx]?.attemptCount ?? 1) - 1 }}</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
}

.modal-panel {
  background: var(--surface);
  border-radius: 8px;
  max-width: 700px;
  width: 90%;
  max-height: 80vh;
  overflow-y: auto;
  padding: 1.5rem;
}

.modal-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 1rem;
}

.modal-header h2 {
  margin: 0;
  font-size: 1rem;
  font-weight: 600;
  outline: none;
}

.modal-nav {
  display: flex;
  gap: 0.25rem;
  flex-shrink: 0;
}

.modal-nav button {
  padding: 0.25rem 0.5rem;
  cursor: pointer;
  border: 1px solid var(--border);
  background: var(--surface);
  border-radius: 4px;
}

.modal-nav button:disabled {
  opacity: 0.4;
  cursor: default;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 0.5rem;
  margin: 0 0 1rem;
  padding: 0;
}

.stats-grid > div {
  background: var(--surface-alt);
  border-radius: 4px;
  padding: 0.5rem;
}

.stats-grid dt {
  font-size: 0.7rem;
  text-transform: uppercase;
  opacity: 0.6;
  margin-bottom: 0.2rem;
}

.stats-grid dd {
  margin: 0;
  font-weight: 600;
  font-size: 0.9rem;
}

.exchange-table-wrapper {
  overflow-x: auto;
}

.exchange-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.85rem;
}

.exchange-table th,
.exchange-table td {
  text-align: left;
  padding: 0.35rem 0.5rem;
  border-bottom: 1px solid var(--border);
}

.exchange-table th {
  font-weight: 600;
  background: var(--surface-alt);
}

.oid-cell {
  font-family: monospace;
  font-size: 0.8rem;
}

.flag {
  display: inline-block;
  padding: 0.1rem 0.35rem;
  border-radius: 3px;
  font-size: 0.75rem;
  margin-right: 0.25rem;
}

.flag.timeout {
  background: var(--err-bg);
  color: var(--err-text);
}

.flag.violation {
  background: var(--warn-bg);
  color: var(--warn-text);
}

.flag.retry {
  background: var(--info-bg);
  color: var(--info-text);
}
</style>
