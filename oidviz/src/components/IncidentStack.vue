<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { clusterMatchesFilters } from '../lib/filters'
import type { DomainExchange, FilterState, Incident } from '../lib/model'
import IncidentModal from './IncidentModal.vue'

const props = defineProps<{
  incidents: Incident[]
  filterState: FilterState
  exchanges: DomainExchange[]
}>()

const shownIncidents = computed(() =>
  props.incidents.filter(i => clusterMatchesFilters(i, props.filterState))
)

const containerRef = ref<HTMLDivElement | null>(null)
const scrollTop = ref(0)
const containerHeight = ref(0)
const ROW_H = 72

const visibleRows = computed(() => {
  const start = Math.max(0, Math.floor(scrollTop.value / ROW_H) - 2)
  const end = Math.min(
    shownIncidents.value.length,
    Math.ceil((scrollTop.value + containerHeight.value) / ROW_H) + 2
  )
  return shownIncidents.value.slice(start, end).map((incident, i) => ({
    incident,
    index: start + i,
    top: (start + i) * ROW_H,
  }))
})

onMounted(() => {
  if (!containerRef.value) return
  containerHeight.value = containerRef.value.clientHeight
  const ro = new ResizeObserver(entries => {
    containerHeight.value = entries[0]?.contentRect.height ?? 0
  })
  ro.observe(containerRef.value)
  onUnmounted(() => ro.disconnect())
})

function severityClass(incident: Incident): string {
  if (incident.timeoutCount > 0) return 'severity-err'
  if (incident.violationTypes.size > 0 || incident.peakRtt > props.filterState.slowMs) return 'severity-warn'
  return 'severity-info'
}

function severityIcon(incident: Incident): string {
  if (incident.timeoutCount > 0) return '✕'
  if (incident.violationTypes.size > 0 || incident.peakRtt > props.filterState.slowMs) return '⚠'
  return 'ℹ'
}

function incidentType(incident: Incident): string {
  if (incident.timeoutCount > 0) return 'timeout'
  if (incident.violationTypes.size > 0) return 'violation'
  if (incident.retryCount > 0) return 'retry'
  return 'slow'
}

function walkBarStyle(incident: Incident) {
  const total = props.exchanges.length
  if (total === 0) return {}
  const left = (incident.startIdx / total) * 100
  const width = ((incident.endIdx - incident.startIdx + 1) / total) * 100
  return {
    left: `${left}%`,
    width: `${Math.max(width, 0.5)}%`,
  }
}

const selectedIndex = ref<number | null>(null)
const lastFocusedRow = ref<HTMLElement | null>(null)

function openModal(index: number) {
  selectedIndex.value = index
  lastFocusedRow.value = document.activeElement as HTMLElement
}

function closeModal() {
  selectedIndex.value = null
  lastFocusedRow.value?.focus()
}

function navigateModal(delta: number) {
  if (selectedIndex.value === null) return
  const next = selectedIndex.value + delta
  if (next >= 0 && next < shownIncidents.value.length) {
    selectedIndex.value = next
  }
}
</script>

<template>
  <div class="incident-stack">
    <div class="toolbar">
      <span>{{ shownIncidents.length }} incident{{ shownIncidents.length !== 1 ? 's' : '' }}</span>
    </div>
    <div v-if="shownIncidents.length === 0" class="empty-state">
      No incidents match the current filters.
    </div>
    <div
      v-else
      ref="containerRef"
      class="scroll-container"
      @scroll.passive="scrollTop = ($event.target as HTMLDivElement).scrollTop"
    >
      <div class="spacer" :style="{ height: shownIncidents.length * ROW_H + 'px' }">
        <div
          v-for="{ incident, index, top } in visibleRows"
          :key="incident.startSeq"
          class="incident-row"
          :style="{ top: top + 'px' }"
          tabindex="0"
          role="button"
          :aria-label="`Incident ${index + 1}: ${incident.region}`"
          @click="openModal(index)"
          @keydown.enter="openModal(index)"
        >
          <div class="severity-chip" :class="severityClass(incident)">
            <span aria-hidden="true">{{ severityIcon(incident) }}</span>
          </div>
          <div class="row-content">
            <div class="row-title">{{ incident.region }} — {{ incidentType(incident) }}</div>
            <div class="row-subtitle">
              seq {{ incident.startSeq }}–{{ incident.endSeq }} · {{ incident.peakRtt.toFixed(0) }}ms peak
              · {{ incident.members.length }} exchange{{ incident.members.length !== 1 ? 's' : '' }}
              <template v-if="incident.retryCount > 0"> · {{ incident.retryCount }} retr{{ incident.retryCount !== 1 ? 'ies' : 'y' }}</template>
            </div>
            <div class="walk-bar-track">
              <div class="walk-bar-fill" :style="walkBarStyle(incident)"></div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <IncidentModal
      v-if="selectedIndex !== null"
      :incident="shownIncidents[selectedIndex]"
      :exchanges="exchanges"
      :index="selectedIndex"
      :total="shownIncidents.length"
      @close="closeModal"
      @navigate="navigateModal"
    />
  </div>
</template>

<style scoped>
.incident-stack {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

.toolbar {
  padding: 0.5rem 1rem;
  font-size: 0.85rem;
  opacity: 0.7;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.empty-state {
  padding: 2rem;
  text-align: center;
  opacity: 0.5;
}

.scroll-container {
  flex: 1;
  overflow-y: auto;
  position: relative;
}

.spacer {
  position: relative;
}

.incident-row {
  position: absolute;
  left: 0;
  right: 0;
  height: 72px;
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0 1rem;
  cursor: pointer;
  border-bottom: 1px solid var(--border);
  box-sizing: border-box;
}

.incident-row:hover,
.incident-row:focus {
  background: var(--surface-alt);
  outline: none;
}

.severity-chip {
  width: 48px;
  height: 48px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1rem;
  flex-shrink: 0;
}

.severity-err {
  background: var(--err-bg);
  color: var(--err-text);
}

.severity-warn {
  background: var(--warn-bg);
  color: var(--warn-text);
}

.severity-info {
  background: var(--info-bg);
  color: var(--info-text);
}

.row-content {
  flex: 1;
  min-width: 0;
}

.row-title {
  font-weight: 600;
  font-size: 0.9rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.row-subtitle {
  font-size: 0.78rem;
  opacity: 0.6;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-top: 0.15rem;
}

.walk-bar-track {
  position: relative;
  height: 4px;
  background: var(--border);
  border-radius: 2px;
  margin-top: 0.35rem;
}

.walk-bar-fill {
  position: absolute;
  top: 0;
  height: 100%;
  background: var(--primary);
  border-radius: 2px;
}
</style>
