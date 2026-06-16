<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue';
import type { DomainExchange, Incident } from '../lib/model.ts';

const props = defineProps<{
  incident: Incident;
  exchanges: DomainExchange[];
  index: number;
  total: number;
}>();
const emit = defineEmits<{ close: []; navigate: [delta: number] }>();

const FIRST_INDEX = 0;
const PREV_DELTA = -1;
const NEXT_DELTA = 1;
const LAST_OFFSET = 1;

const dialogTitleId = computed(() => `incident-dialog-title-${props.index}`);
const titleRef = ref<HTMLHeadingElement | null>(null);

const memberExchanges = computed(() =>
  props.incident.members
    .map((idx) => props.exchanges[idx])
    .filter((ex): ex is DomainExchange => ex !== null && typeof ex === 'object'),
);

const onKeydown = (event: KeyboardEvent): void => {
  if (event.key === 'Escape') {
    emit('close');
  } else if (event.key === 'ArrowLeft' && props.index > FIRST_INDEX) {
    emit('navigate', PREV_DELTA);
  } else if (event.key === 'ArrowRight' && props.index < props.total - LAST_OFFSET) {
    emit('navigate', NEXT_DELTA);
  }
};

onMounted(() => {
  if (titleRef.value) {
    titleRef.value.focus();
  }
  document.addEventListener('keydown', onKeydown);
});

onUnmounted(() => {
  document.removeEventListener('keydown', onKeydown);
});
</script>

<template>
  <Teleport to="body">
    <div class="modal-overlay" @click.self="emit('close')">
      <div
        role="dialog"
        aria-modal="true"
        :aria-labelledby="dialogTitleId"
        class="modal-panel"
      >
        <h2 ref="titleRef" tabindex="-1" :id="dialogTitleId" class="modal-title">
          Incident {{ index + 1 }} / {{ total }} — {{ incident.region }}
        </h2>

        <div class="modal-nav">
          <button type="button" :disabled="index === 0" @click="emit('navigate', -1)">← Prev</button>
          <span>{{ index + 1 }} / {{ total }}</span>
          <button type="button" :disabled="index === total - 1" @click="emit('navigate', 1)">Next →</button>
          <button type="button" @click="emit('close')" aria-label="Close modal" class="close-btn">✕</button>
        </div>

        <div class="incident-stats">
          <span>Score: {{ incident.score.toFixed(1) }}</span>
          <span>Peak RTT: {{ incident.peakRtt.toFixed(0) }}ms</span>
          <span v-if="incident.timeoutCount > 0">Timeouts: {{ incident.timeoutCount }}</span>
          <span v-if="incident.retryCount > 0">Retries: {{ incident.retryCount }}</span>
        </div>

        <div class="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>Seq</th>
                <th>RTT</th>
                <th>OID</th>
                <th>Badges</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="ex in memberExchanges" :key="ex.seq">
                <td>{{ ex.seq }}</td>
                <td>{{ ex.rtt.toFixed(0) }}ms</td>
                <td class="oid-cell">{{ ex.requestOid }}</td>
                <td>
                  <span v-if="ex.isTimeout" class="badge badge-timeout">T</span>
                  <span v-if="ex.violations.length > 0" class="badge badge-violation">V</span>
                  <span v-if="ex.attemptCount > 1" class="badge badge-retry">R</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-panel {
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  border-radius: 0.5rem;
  width: min(90vw, 720px);
  max-height: 80vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.modal-title {
  padding: 1rem 1.25rem 0.75rem;
  font-size: 1rem;
  font-weight: 600;
  color: var(--color-text);
  border-bottom: 1px solid var(--color-border);
  outline: none;
}

.modal-nav {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 1.25rem;
  border-bottom: 1px solid var(--color-border);
  font-size: 0.8125rem;
}

.modal-nav button {
  padding: 0.25rem 0.75rem;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 0.25rem;
  cursor: pointer;
  font-size: 0.8125rem;
  color: var(--color-text);
}

.modal-nav button:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.modal-nav button:not(:disabled):hover {
  background: var(--color-border);
}

.close-btn {
  margin-left: auto;
}

.incident-stats {
  display: flex;
  gap: 1rem;
  padding: 0.5rem 1.25rem;
  font-size: 0.8125rem;
  color: var(--color-text-muted);
  border-bottom: 1px solid var(--color-border);
  flex-wrap: wrap;
}

.table-wrapper {
  overflow-y: auto;
  flex: 1;
}

table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.8125rem;
}

thead th {
  position: sticky;
  top: 0;
  background: var(--color-surface);
  padding: 0.4rem 1rem;
  text-align: left;
  font-weight: 600;
  font-size: 0.75rem;
  color: var(--color-text-muted);
  border-bottom: 1px solid var(--color-border);
}

tbody tr {
  border-bottom: 1px solid var(--color-border);
}

tbody tr:hover {
  background: var(--color-surface);
}

tbody td {
  padding: 0.35rem 1rem;
  color: var(--color-text);
  font-family: var(--font-mono);
  font-size: 0.75rem;
}

.oid-cell {
  max-width: 300px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 1.25rem;
  height: 1.25rem;
  border-radius: 0.25rem;
  font-size: 0.625rem;
  font-weight: 700;
  margin-right: 0.2rem;
}

.badge-timeout {
  background: var(--dim-timeout-bg);
  color: var(--dim-timeout);
}

.badge-violation {
  background: var(--dim-violation-bg);
  color: var(--dim-violation);
}

.badge-retry {
  background: var(--dim-retry-bg);
  color: var(--dim-retry);
}
</style>
