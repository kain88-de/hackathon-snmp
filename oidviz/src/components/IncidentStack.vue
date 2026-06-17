<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue';
import type { DomainExchange, FacetState, Incident } from '../lib/model.ts';

const props = defineProps<{
  incidents: Incident[];
  facetState: FacetState;
  exchanges: DomainExchange[];
}>();
const emit = defineEmits<{ 'open-incident': [index: number] }>();

const ROW_HEIGHT = 40;
const BUFFER_ROWS = 5;
const ZERO = 0;
const NO_TIMEOUTS = 0;

const containerRef = ref<HTMLElement | null>(null);
const scrollTop = ref(ZERO);
const containerHeight = ref(ZERO);

const visibleStart = computed(() =>
  Math.max(ZERO, Math.floor(scrollTop.value / ROW_HEIGHT) - BUFFER_ROWS),
);
const visibleEnd = computed(() =>
  Math.min(
    props.incidents.length,
    Math.ceil((scrollTop.value + containerHeight.value) / ROW_HEIGHT) + BUFFER_ROWS,
  ),
);

const visibleIncidents = computed(() =>
  props.incidents.slice(visibleStart.value, visibleEnd.value).map((incident, idx) => ({
    incident,
    index: visibleStart.value + idx,
  })),
);

const totalHeight = computed(() => props.incidents.length * ROW_HEIGHT);
const offsetTop = computed(() => visibleStart.value * ROW_HEIGHT);

const onScroll = (event: Event): void => {
  const el = event.target as HTMLElement;
  scrollTop.value = el.scrollTop;
};

let resizeObserver: ResizeObserver | null = null;

onMounted(() => {
  if (containerRef.value) {
    containerHeight.value = containerRef.value.clientHeight;
    resizeObserver = new ResizeObserver((entries) => {
      const [entry] = entries;
      if (entry) {
        containerHeight.value = entry.contentRect.height;
      }
    });
    resizeObserver.observe(containerRef.value);
  }
});

onUnmounted(() => {
  if (resizeObserver) {
    resizeObserver.disconnect();
  }
});

const isSlowOnly = (incident: Incident): boolean =>
  incident.peakRtt > props.facetState.slowMs && incident.timeoutCount === NO_TIMEOUTS;
</script>

<template>
  <div class="incident-stack" ref="containerRef" @scroll="onScroll">
    <div class="incident-list-inner" :style="{ height: `${totalHeight}px` }">
      <div class="incident-rows-viewport" :style="{ transform: `translateY(${offsetTop}px)` }">
        <button
          v-for="{ incident, index } in visibleIncidents"
          :key="index"
          type="button"
          class="incident-row"
          :style="{ height: `${ROW_HEIGHT}px` }"
          @click="emit('open-incident', index)"
        >
          <span class="score">{{ incident.score.toFixed(1) }}</span>
          <span class="rtt">{{ incident.peakRtt.toFixed(0) }}ms</span>
          <span v-if="incident.timeoutCount > 0" class="chip chip-timeout">
            {{ incident.timeoutCount }}T
          </span>
          <span v-if="incident.violationTypes.size > 0" class="chip chip-violation">
            {{ incident.violationTypes.size }}V
          </span>
          <span v-if="incident.retryCount > 0" class="chip chip-retry">
            {{ incident.retryCount }}R
          </span>
          <span v-if="isSlowOnly(incident)" class="chip chip-slow">slow</span>
          <span class="region">{{ incident.region }}</span>
          <span class="member-count">{{ incident.members.length }}</span>
        </button>
      </div>
    </div>
    <div v-if="incidents.length === 0" class="empty-state">No incidents found</div>
  </div>
</template>

<style scoped>
.incident-stack {
  position: relative;
  height: 100%;
  overflow-y: auto;
}

.incident-list-inner {
  position: relative;
  width: 100%;
}

.incident-rows-viewport {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
}

.incident-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  width: 100%;
  padding: 0 1rem;
  background: transparent;
  border: none;
  border-bottom: 1px solid var(--color-border);
  cursor: pointer;
  font-size: 0.8125rem;
  color: var(--color-text);
  text-align: left;
  box-sizing: border-box;
}

.incident-row:hover {
  background: var(--color-surface);
}

.score {
  font-family: var(--font-mono);
  font-size: 0.75rem;
  min-width: 4rem;
  color: var(--color-text-muted);
}

.rtt {
  font-family: var(--font-mono);
  font-size: 0.75rem;
  min-width: 4.5rem;
  color: var(--color-text-muted);
}

.chip {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0 0.35rem;
  height: 1.25rem;
  border-radius: 0.25rem;
  font-size: 0.625rem;
  font-weight: 700;
  flex-shrink: 0;
}

.chip-timeout {
  background: var(--dim-timeout-bg);
  color: var(--dim-timeout);
}

.chip-violation {
  background: var(--dim-violation-bg);
  color: var(--dim-violation);
}

.chip-retry {
  background: var(--dim-retry-bg);
  color: var(--dim-retry);
}

.chip-slow {
  background: var(--dim-slow-bg);
  color: var(--dim-slow);
}

.region {
  font-family: var(--font-mono);
  font-size: 0.75rem;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--color-text);
}

.member-count {
  font-size: 0.75rem;
  color: var(--color-text-muted);
  flex-shrink: 0;
}

.empty-state {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  color: var(--color-text-muted);
  font-size: 0.875rem;
}
</style>
