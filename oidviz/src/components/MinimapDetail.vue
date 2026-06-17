<script setup lang="ts">
// biome-ignore lint/correctness/noUnusedImports: used in <template>
import { MINI_H, useMinimapDetail } from '../composables/useMinimapDetail.ts';
import type { DomainExchange, FacetState } from '../lib/model.ts';

const props = defineProps<{ exchanges: DomainExchange[]; facetState: FacetState }>();
const emit = defineEmits<{ 'focus-exchange': [seq: number] }>();

const {
  minimapRef,
  detailRef,
  containerRef,
  onKeyDown,
  onMinimapMouseDown,
  onMinimapMouseMove,
  onMinimapMouseUp,
  onMinimapClick,
} = useMinimapDetail(() => props, emit);
</script>

<template>
  <div class="minimap-detail" ref="containerRef" tabindex="0" @keydown="onKeyDown">
    <div class="minimap-wrapper">
      <canvas
        ref="minimapRef"
        class="minimap-canvas"
        :height="MINI_H"
        @mousedown="onMinimapMouseDown"
        @mousemove="onMinimapMouseMove"
        @mouseup="onMinimapMouseUp"
        @click="onMinimapClick"
      />
    </div>
    <div class="detail-wrapper">
      <canvas ref="detailRef" class="detail-canvas" />
    </div>
    <div v-if="exchanges.length === 0" class="empty-state">Load a trace to see the timeline</div>
  </div>
</template>

<style scoped>
.minimap-detail {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
  outline: none;
  background: var(--color-bg);
}

.minimap-wrapper {
  flex-shrink: 0;
  border-bottom: 1px solid var(--color-border);
  position: relative;
}

.minimap-canvas {
  display: block;
  width: 100%;
  cursor: crosshair;
}

.detail-wrapper {
  flex: 1;
  overflow-y: auto;
  position: relative;
}

.detail-canvas {
  display: block;
  width: 100%;
}

.empty-state {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  color: var(--color-text-muted);
  font-size: 0.875rem;
  pointer-events: none;
}
</style>
