<script setup lang="ts">
import { computed, reactive } from 'vue';
import { categorise } from '../lib/findings.ts';
import type { DomainExchange, FacetState } from '../lib/model.ts';

const props = defineProps<{ exchanges: DomainExchange[]; facetState: FacetState }>();
const emit = defineEmits<{ 'focus-exchange': [seq: number] }>();

const findings = computed(() => categorise(props.exchanges, props.facetState.slowMs));

const expanded = reactive({ fast: false, slow: true, timeout: true });

const toggleSection = (key: 'slow' | 'timeout' | 'fast'): void => {
  expanded[key] = !expanded[key];
};
</script>

<template>
  <div class="findings-view">
    <!-- Slow section -->
    <section class="findings-section">
      <button
        type="button"
        class="section-header"
        @click="toggleSection('slow')"
        :aria-expanded="expanded.slow"
      >
        <span>Slow</span>
        <span class="count">({{ findings.slow.length }})</span>
        <span aria-hidden="true">{{ expanded.slow ? '▾' : '▸' }}</span>
      </button>
      <div v-if="expanded.slow" class="section-rows">
        <button
          v-for="ex in findings.slow"
          :key="ex.seq"
          type="button"
          class="exchange-row"
          @click="emit('focus-exchange', ex.seq)"
        >
          <span class="rtt">{{ ex.rtt.toFixed(0) }}ms</span>
          <span class="oid">{{ ex.requestOid }}</span>
          <span v-if="ex.violations.length > 0" class="badge badge-violation">V</span>
          <span v-if="ex.attemptCount > 1" class="badge badge-retry">R</span>
        </button>
      </div>
    </section>

    <!-- Timeout section -->
    <section class="findings-section">
      <button
        type="button"
        class="section-header"
        @click="toggleSection('timeout')"
        :aria-expanded="expanded.timeout"
      >
        <span>Timed Out</span>
        <span class="count">({{ findings.timeout.length }})</span>
        <span aria-hidden="true">{{ expanded.timeout ? '▾' : '▸' }}</span>
      </button>
      <div v-if="expanded.timeout" class="section-rows">
        <button
          v-for="ex in findings.timeout"
          :key="ex.seq"
          type="button"
          class="exchange-row"
          @click="emit('focus-exchange', ex.seq)"
        >
          <span class="rtt timeout">TIMEOUT</span>
          <span class="oid">{{ ex.requestOid }}</span>
          <span v-if="ex.violations.length > 0" class="badge badge-violation">V</span>
          <span v-if="ex.attemptCount > 1" class="badge badge-retry">R</span>
          <span class="badge badge-timeout">T</span>
        </button>
      </div>
    </section>

    <!-- Fast section (only when non-empty) -->
    <section v-if="findings.fast.length > 0" class="findings-section">
      <button
        type="button"
        class="section-header"
        @click="toggleSection('fast')"
        :aria-expanded="expanded.fast"
      >
        <span>Fast</span>
        <span class="count">({{ findings.fast.length }})</span>
        <span aria-hidden="true">{{ expanded.fast ? '▾' : '▸' }}</span>
      </button>
      <div v-if="expanded.fast" class="section-rows">
        <button
          v-for="ex in findings.fast"
          :key="ex.seq"
          type="button"
          class="exchange-row"
          @click="emit('focus-exchange', ex.seq)"
        >
          <span class="rtt">{{ ex.rtt.toFixed(0) }}ms</span>
          <span class="oid">{{ ex.requestOid }}</span>
          <span v-if="ex.violations.length > 0" class="badge badge-violation">V</span>
          <span v-if="ex.attemptCount > 1" class="badge badge-retry">R</span>
        </button>
      </div>
    </section>
  </div>
</template>

<style scoped>
.findings-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow-y: auto;
}

.findings-section {
  border-bottom: 1px solid var(--color-border);
}

.section-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  width: 100%;
  padding: 0.5rem 1rem;
  background: var(--color-surface);
  border: none;
  cursor: pointer;
  font-weight: 600;
  font-size: 0.875rem;
  color: var(--color-text);
  text-align: left;
}

.section-header:hover {
  background: var(--color-border);
}

.count {
  color: var(--color-text-muted);
  font-weight: 400;
}

.section-rows {
  display: flex;
  flex-direction: column;
}

.exchange-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  width: 100%;
  padding: 0.25rem 1rem;
  background: transparent;
  border: none;
  border-bottom: 1px solid var(--color-border);
  cursor: pointer;
  font-size: 0.8125rem;
  color: var(--color-text);
  text-align: left;
}

.exchange-row:hover {
  background: var(--color-surface);
}

.rtt {
  font-family: var(--font-mono);
  min-width: 5rem;
  font-size: 0.75rem;
  color: var(--color-text-muted);
}

.rtt.timeout {
  color: var(--dim-timeout);
  font-weight: 600;
}

.oid {
  font-family: var(--font-mono);
  font-size: 0.75rem;
  flex: 1;
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
  flex-shrink: 0;
}

.badge-violation {
  background: var(--dim-violation-bg);
  color: var(--dim-violation);
}

.badge-retry {
  background: var(--dim-retry-bg);
  color: var(--dim-retry);
}

.badge-timeout {
  background: var(--dim-timeout-bg);
  color: var(--dim-timeout);
}
</style>
