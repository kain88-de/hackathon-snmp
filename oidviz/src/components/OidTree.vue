<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue';
import type {
  DomainExchange,
  FilterState,
  FlatRow,
  TrieNode,
} from '../lib/model';
import { Severity } from '../lib/model';

const props = defineProps<{
  flatRows: FlatRow[];
  filterState: FilterState;
  matchingCount: number;
}>();

const emit = defineEmits<{
  reflatten: [];
  'collapse-all': [];
}>();

const ROW_H = 22;
const OVERSCAN = 4;

const containerRef = ref<HTMLDivElement | null>(null);
const scrollTop = ref(0);
const containerHeight = ref(0);

const shownLeafCount = computed(
  () => props.flatRows.filter((r) => r.kind === 'leaf').length,
);

const visibleRows = computed(() => {
  const start = Math.max(0, Math.floor(scrollTop.value / ROW_H) - OVERSCAN);
  const end = Math.min(
    props.flatRows.length,
    Math.ceil((scrollTop.value + containerHeight.value) / ROW_H) + OVERSCAN,
  );
  return props.flatRows.slice(start, end).map((row, i) => ({
    row,
    index: start + i,
    top: (start + i) * ROW_H,
  }));
});

onMounted(() => {
  if (!containerRef.value) {
    return;
  }
  containerHeight.value = containerRef.value.clientHeight;
  const ro = new ResizeObserver((entries) => {
    containerHeight.value = entries[0]?.contentRect.height ?? 0;
  });
  ro.observe(containerRef.value);
  onUnmounted(() => ro.disconnect());
});

function toggleNode(node: TrieNode) {
  node.expanded = !node.expanded;
  emit('reflatten');
}

function rttClass(node: TrieNode): string {
  if (node.severity === Severity.Violation) {
    return 'rtt-err';
  }
  if (node.severity === Severity.Slow) {
    return 'rtt-warn';
  }
  return 'rtt-ok';
}

function exchangeRttClass(ex: DomainExchange): string {
  if (ex.violations.length > 0) {
    return 'rtt-err';
  }
  if (ex.rtt > props.filterState.slowMs) {
    return 'rtt-warn';
  }
  return 'rtt-ok';
}

const OID_MAX_DISPLAY_LEN = 30;
const OID_TAIL_LEN = -(OID_MAX_DISPLAY_LEN - 1); // -29

function truncateOid(oid: string): string {
  if (oid.length <= OID_MAX_DISPLAY_LEN) {
    return oid;
  }
  return `…${oid.slice(OID_TAIL_LEN)}`;
}
</script>

<template>
  <div class="oid-tree">
    <div class="toolbar">
      <span class="count-label">{{ props.matchingCount }} matching / {{ shownLeafCount }} shown</span>
      <button @click="emit('collapse-all')">Collapse all</button>
    </div>

    <div
      ref="containerRef"
      class="scroll-container"
      @scroll.passive="scrollTop = ($event.target as HTMLDivElement).scrollTop"
    >
      <div class="spacer" :style="{ height: `${props.flatRows.length * ROW_H}px` }">
        <template v-for="item in visibleRows" :key="item.index">
          <!-- Node row -->
          <div v-if="item.row.kind === 'node'"
            class="trie-row trie-node-row"
            :style="{ top: `${item.top}px`, paddingLeft: `${item.row.depth * 16 + 8}px` }"
            tabindex="0"
            role="button"
            :aria-expanded="String(item.row.node.expanded)"
            :aria-label="`OID node ${item.row.node.fullOid}`"
            @click="toggleNode(item.row.node)"
            @keydown.enter="toggleNode(item.row.node)"
          >
            <span class="caret" aria-hidden="true">{{
              (item.row.node.children.size > 0 || item.row.node.leaves.length > 0)
                ? (item.row.node.expanded ? '▾' : '▸')
                : ' '
            }}</span>
            <span class="arc-label">{{ item.row.node.arc }}</span>
            <span v-if="item.row.node.name" class="node-name muted">{{ item.row.node.name }}</span>
            <span class="node-stats">
              <span class="node-count">{{ item.row.node.stats.count }}</span>
              <span class="node-rtt" :class="rttClass(item.row.node)">{{ item.row.node.stats.maxRtt.toFixed(0) }}ms</span>
              <span v-if="item.row.node.stats.violationCount > 0" class="badge-err">{{ item.row.node.stats.violationCount }}v</span>
            </span>
          </div>

          <!-- Leaf row -->
          <div v-else
            class="trie-row trie-leaf-row"
            :style="{ top: `${item.top}px`, paddingLeft: `${item.row.depth * 16 + 8}px` }"
          >
            <span class="seq-label">#{{ item.row.exchange.seq }}</span>
            <span class="leaf-oid">{{ truncateOid(item.row.exchange.requestOid) }}</span>
            <span v-if="item.row.shared" class="shared-tag">(shared)</span>
            <span v-if="item.row.exchange.attemptCount > 1" class="leaf-attempts">{{ item.row.exchange.attemptCount }}×</span>
            <span class="leaf-rtt" :class="exchangeRttClass(item.row.exchange)">{{ item.row.exchange.rtt.toFixed(0) }}ms</span>
            <span v-if="item.row.exchange.violations.length > 0" class="badge-err">{{ item.row.exchange.violations.length }}v</span>
          </div>
        </template>
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
  font-family: var(--font-mono);
  font-size: 0.8rem;
}
.toolbar {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.4rem 0.75rem;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.toolbar button {
  padding: 0.2rem 0.5rem;
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text);
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.75rem;
}
.count-label {
  flex: 1;
  color: var(--text-muted);
  font-size: 0.75rem;
}
.scroll-container {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  position: relative;
}
.spacer {
  position: relative;
}
.trie-row {
  position: absolute;
  left: 0;
  right: 0;
  height: 22px;
  display: flex;
  align-items: center;
  gap: 0.4rem;
  cursor: pointer;
  white-space: nowrap;
  overflow: hidden;
}
.trie-row:hover { background: color-mix(in srgb, var(--primary) 8%, transparent); }
.trie-row:focus { outline: 2px solid var(--primary); outline-offset: -2px; }
.trie-leaf-row { cursor: default; }
.caret { width: 1em; text-align: center; color: var(--text-muted); }
.arc-label { color: var(--text); }
.muted { color: var(--text-muted); font-size: 0.75rem; }
.node-stats { display: flex; gap: 0.4rem; margin-left: auto; flex-shrink: 0; }
.seq-label { color: var(--text-muted); }
.leaf-oid { color: var(--text); flex: 1; overflow: hidden; text-overflow: ellipsis; }
.shared-tag { color: var(--text-muted); font-size: 0.7rem; }
.leaf-attempts { color: var(--warn); }
.badge-err { color: var(--err); font-size: 0.7rem; }
.rtt-ok { color: var(--ok); }
.rtt-warn { color: var(--warn); }
.rtt-err { color: var(--err); }
</style>
