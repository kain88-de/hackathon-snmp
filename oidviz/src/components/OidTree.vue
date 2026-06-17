<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue';
import type { FacetState, FlatRow, TrieNode } from '../lib/model.ts';

const props = defineProps<{ flatRows: FlatRow[]; facetState: FacetState; matchingCount: number }>();
const emit = defineEmits<{ reflatten: []; 'collapse-all': [] }>();

const ROW_HEIGHT = 28;
const BUFFER_ROWS = 5;
const ZERO = 0;
const INDENT_PX = 16;

const containerRef = ref<HTMLElement | null>(null);
const scrollTop = ref(ZERO);
const containerHeight = ref(ZERO);

const visibleStart = computed(() =>
  Math.max(ZERO, Math.floor(scrollTop.value / ROW_HEIGHT) - BUFFER_ROWS),
);
const visibleEnd = computed(() =>
  Math.min(
    props.flatRows.length,
    Math.ceil((scrollTop.value + containerHeight.value) / ROW_HEIGHT) + BUFFER_ROWS,
  ),
);

const visibleRows = computed(() =>
  props.flatRows.slice(visibleStart.value, visibleEnd.value).map((row, idx) => ({
    index: visibleStart.value + idx,
    row,
  })),
);

const totalHeight = computed(() => props.flatRows.length * ROW_HEIGHT);

const rowTop = (index: number): number => index * ROW_HEIGHT;

const rowKey = (row: FlatRow): string => {
  if (row.kind === 'node') {
    return row.node.fullOid;
  }
  return `${row.oid}-${row.exchange.seq}`;
};

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

const toggleNode = (node: TrieNode): void => {
  node.expanded = !node.expanded;
  emit('reflatten');
};
</script>

<template>
  <div class="oid-tree">
    <div class="oid-tree-controls">
      <button type="button" @click="emit('collapse-all')">Collapse all</button>
      <span>{{ matchingCount }} exchanges</span>
    </div>

    <div ref="containerRef" class="oid-tree-scroll" @scroll="onScroll">
      <div :style="{ height: totalHeight + 'px', position: 'relative' }">
        <div
          v-for="{ row, index } in visibleRows"
          :key="rowKey(row)"
          class="tree-row"
          :class="{ 'tree-row--node': row.kind === 'node', 'tree-row--leaf': row.kind === 'leaf' }"
          :style="{ position: 'absolute', top: rowTop(index) + 'px', width: '100%' }"
        >
          <template v-if="row.kind === 'node'">
            <button
              type="button"
              class="expand-btn"
              :style="{ marginLeft: row.depth * INDENT_PX + 'px' }"
              :aria-expanded="row.node.expanded"
              @click="toggleNode(row.node)"
            >{{ row.node.expanded ? '▾' : '▸' }}</button>
            <span class="arc-label">{{ row.node.arc }}</span>
            <span v-if="row.node.name" class="known-name">({{ row.node.name }})</span>
            <span class="stats">{{ row.node.stats.count }}</span>
            <span v-if="row.node.flags.slow" class="badge badge-slow">S</span>
            <span v-if="row.node.flags.violation" class="badge badge-violation">V</span>
            <span v-if="row.node.flags.retry" class="badge badge-retry">R</span>
          </template>

          <template v-else>
            <span :style="{ marginLeft: (row.depth + 1) * INDENT_PX + 'px' }" class="leaf-oid">{{ row.oid }}</span>
            <span class="rtt">{{ row.exchange.rtt.toFixed(0) }}ms</span>
            <span v-if="row.exchange.isTimeout" class="badge badge-timeout">T</span>
            <span v-if="row.exchange.violations.length > 0" class="badge badge-violation">V</span>
            <span v-if="row.exchange.attemptCount > 1" class="badge badge-retry">R</span>
          </template>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.oid-tree {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

.oid-tree-controls {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 0.5rem 1rem;
  border-bottom: 1px solid var(--color-border);
  flex-shrink: 0;
}

.oid-tree-controls button {
  padding: 0.25rem 0.5rem;
  font-size: 0.75rem;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 0.25rem;
  cursor: pointer;
  color: var(--color-text);
}

.oid-tree-controls button:hover {
  background: var(--color-border);
}

.oid-tree-controls span {
  font-size: 0.75rem;
  color: var(--color-text-muted);
}

.oid-tree-scroll {
  flex: 1;
  overflow-y: auto;
  position: relative;
}

.tree-row {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  height: 28px;
  padding: 0 0.5rem;
  font-size: 0.8125rem;
  font-family: var(--font-mono);
  white-space: nowrap;
  overflow: hidden;
}

.tree-row--node {
  color: var(--color-text);
}

.tree-row--leaf {
  color: var(--color-text-muted);
}

.expand-btn {
  flex-shrink: 0;
  background: transparent;
  border: none;
  cursor: pointer;
  font-size: 0.75rem;
  padding: 0 0.125rem;
  color: var(--color-text-muted);
  line-height: 1;
}

.arc-label {
  font-weight: 600;
  color: var(--color-text);
}

.known-name {
  color: var(--color-text-muted);
  font-size: 0.75rem;
}

.stats {
  color: var(--color-text-muted);
  font-size: 0.75rem;
  margin-left: 0.25rem;
}

.leaf-oid {
  color: var(--color-text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
}

.rtt {
  font-size: 0.75rem;
  color: var(--color-text-muted);
  flex-shrink: 0;
}

.badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0 0.25rem;
  height: 1.1rem;
  border-radius: 0.2rem;
  font-size: 0.625rem;
  font-weight: 700;
  flex-shrink: 0;
}

.badge-slow {
  background: var(--dim-slow-bg);
  color: var(--dim-slow);
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
