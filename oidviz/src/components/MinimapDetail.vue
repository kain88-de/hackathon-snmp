<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { matchesFilters } from '../lib/filters'
import type { DomainExchange, FilterState } from '../lib/model'

const MINI_H = 80
const ML = 64
const MT = 24
const RH = 9
const RG = 3
const BH = 6
const MAX_H = 32767

const props = defineProps<{
  exchanges: DomainExchange[]
  filterState: FilterState
}>()

const miniCanvasRef = ref<HTMLCanvasElement | null>(null)
const detailCanvasRef = ref<HTMLCanvasElement | null>(null)
const miniWrapRef = ref<HTMLDivElement | null>(null)

const winS = ref(0)
const winE = ref(0)

const tooltipStyle = ref({ display: 'none', left: '0px', top: '0px' })
const tooltipText = ref('')

const dragging = ref<null | { kind: 'pan' | 'create' | 'resize-left' | 'resize-right'; startX: number; startWinS: number; startWinE: number }>(null)

const maxT = computed(() => {
  if (props.exchanges.length === 0) return 1
  return props.exchanges.reduce((m, e) => Math.max(m, e.receivedAtMs), 0)
})

const filteredExchanges = computed(() =>
  props.exchanges.filter(ex => matchesFilters(ex, props.filterState))
)

interface MiniMapBucket {
  count: number
  maxRtt: number
  viol: boolean
  timeout: boolean
  retry: boolean
}

function buildBuckets(canvasWidth: number): MiniMapBucket[] {
  const buckets: MiniMapBucket[] = Array.from({ length: canvasWidth }, () => ({
    count: 0, maxRtt: 0, viol: false, timeout: false, retry: false,
  }))
  const mT = maxT.value
  for (const ex of filteredExchanges.value) {
    if (!isAnomalous(ex)) continue
    const col = Math.min(
      Math.floor((ex.sentAtMs / mT) * canvasWidth),
      canvasWidth - 1
    )
    const b = buckets[col]
    if (!b) continue
    b.count++
    b.maxRtt = Math.max(b.maxRtt, ex.rtt)
    if (ex.violations.length > 0) b.viol = true
    if (ex.isTimeout) b.timeout = true
    if (ex.attemptCount > 1) b.retry = true
  }
  return buckets
}

function isAnomalous(ex: DomainExchange): boolean {
  return ex.rtt > props.filterState.slowMs || ex.violations.length > 0 || ex.attemptCount > 1 || ex.isTimeout
}

function drawMini() {
  const canvas = miniCanvasRef.value
  if (!canvas) return
  const ctx = canvas.getContext('2d')
  if (!ctx) return
  const W = canvas.width
  const H = MINI_H

  ctx.clearRect(0, 0, W, H)

  const buckets = buildBuckets(W)
  const maxCount = buckets.reduce((m, b) => Math.max(m, b.count), 1)
  const barMaxH = H - 4

  buckets.forEach((b, col) => {
    if (b.count === 0) return
    const barH = Math.max(1, Math.round((b.count / maxCount) * barMaxH))
    ctx.fillStyle = b.timeout ? '#ef4444' : b.viol ? '#f59e0b' : b.retry ? '#93c5fd' : '#3b82f6'
    ctx.fillRect(col, H - barH, 1, barH)
  })

  const mT = maxT.value
  const selX = Math.floor((winS.value / mT) * W)
  const selW = Math.max(2, Math.floor(((winE.value - winS.value) / mT) * W))
  ctx.fillStyle = 'rgba(59,130,246,0.22)'
  ctx.fillRect(selX, 0, selW, H)
  ctx.strokeStyle = '#3b82f6'
  ctx.lineWidth = 1
  ctx.strokeRect(selX, 0, selW, H)
}

function drawDetail() {
  const canvas = detailCanvasRef.value
  if (!canvas) return
  const ctx = canvas.getContext('2d')
  if (!ctx) return

  const W = canvas.width
  const wS = winS.value
  const wE = winE.value
  const span = Math.max(wE - wS, 1)
  const mpp = span / (W - ML)

  const visible = props.exchanges.filter(
    ex => ex.sentAtMs < wE && ex.receivedAtMs > wS
  ).sort((a, b) => a.sentAtMs - b.sentAtMs)

  const rowCount = visible.length
  const detailH = Math.min(MAX_H, MT + rowCount * (RH + RG) + 20)
  if (canvas.height !== detailH) canvas.height = detailH

  ctx.clearRect(0, 0, W, detailH)

  const TICK_INTERVALS = [0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50, 100, 200, 500, 1000]
  const minTickPx = 60
  const tickIntervalMs = (TICK_INTERVALS.find(t => (t * 1000) / mpp >= minTickPx) ?? 1000) * 1000

  ctx.fillStyle = '#64748b'
  ctx.font = '10px monospace'
  ctx.textAlign = 'center'

  let tick = Math.ceil(wS / tickIntervalMs) * tickIntervalMs
  while (tick < wE) {
    const x = ML + (tick - wS) / mpp
    ctx.fillText(`${((tick) / 1000).toFixed(1)}s`, x, 12)
    ctx.strokeStyle = '#e2e8f0'
    ctx.lineWidth = 1
    ctx.beginPath()
    ctx.moveTo(x, MT - 4)
    ctx.lineTo(x, detailH)
    ctx.stroke()
    tick += tickIntervalMs
  }

  visible.forEach((ex, row) => {
    const y = MT + row * (RH + RG)
    const barX = ML + (ex.sentAtMs - wS) / mpp
    const barW = Math.max(2, ex.rtt / mpp)

    ctx.fillStyle = ex.isTimeout ? '#ef4444' : ex.violations.length > 0 ? '#f59e0b' : ex.rtt > props.filterState.slowMs ? '#3b82f6' : '#94a3b8'
    ctx.fillRect(barX, y + (RH - BH) / 2, barW, BH)

    ctx.fillStyle = '#64748b'
    ctx.textAlign = 'right'
    ctx.font = '9px monospace'
    ctx.fillText(String(ex.seq), ML - 2, y + RH - 1)

    if (ex.violations.length > 0) {
      ctx.fillStyle = '#f59e0b'
      ctx.textAlign = 'left'
      ctx.fillText('!', barX + barW + 2, y + RH - 1)
    }
  })
}

function initWindow() {
  const mT = maxT.value
  winS.value = 0
  winE.value = mT * 0.05
}

function autoFocus() {
  if (!miniCanvasRef.value) return
  const W = miniCanvasRef.value.width || 400
  const buckets = buildBuckets(W)
  let bestScore = -1
  let bestCol = 0
  buckets.forEach((b, col) => {
    const score = (b.viol ? 1e9 : 0) + b.maxRtt * 1000 + b.count
    if (score > bestScore) { bestScore = score; bestCol = col }
  })
  const mT = maxT.value
  const centerMs = (bestCol / W) * mT
  const halfSpan = mT * 0.025
  winS.value = Math.max(0, centerMs - halfSpan)
  winE.value = Math.min(mT, centerMs + halfSpan)
}

function getMiniMs(x: number): number {
  const canvas = miniCanvasRef.value
  if (!canvas) return 0
  return (x / canvas.width) * maxT.value
}

function onMiniClick(event: MouseEvent) {
  if (dragging.value) return
  const ms = getMiniMs(event.offsetX)
  const halfSpan = (winE.value - winS.value) / 2
  winS.value = Math.max(0, ms - halfSpan)
  winE.value = Math.min(maxT.value, ms + halfSpan)
}

function onMiniMousedown(event: MouseEvent) {
  const mT = maxT.value
  const canvas = miniCanvasRef.value
  if (!canvas) return
  const x = event.offsetX
  const W = canvas.width
  const selX = (winS.value / mT) * W
  const selE = (winE.value / mT) * W
  const EDGE = 4

  if (x >= selX - EDGE && x <= selX + EDGE) {
    dragging.value = { kind: 'resize-left', startX: x, startWinS: winS.value, startWinE: winE.value }
  } else if (x >= selE - EDGE && x <= selE + EDGE) {
    dragging.value = { kind: 'resize-right', startX: x, startWinS: winS.value, startWinE: winE.value }
  } else if (x >= selX && x <= selE) {
    dragging.value = { kind: 'pan', startX: x, startWinS: winS.value, startWinE: winE.value }
  } else {
    dragging.value = { kind: 'create', startX: x, startWinS: getMiniMs(x), startWinE: getMiniMs(x) }
  }
}

function onMiniMousemove(event: MouseEvent) {
  if (!dragging.value) return
  const mT = maxT.value
  const canvas = miniCanvasRef.value
  if (!canvas) return
  const dx = event.offsetX - dragging.value.startX
  const dms = (dx / canvas.width) * mT

  switch (dragging.value.kind) {
    case 'pan': {
      const span = dragging.value.startWinE - dragging.value.startWinS
      const clampedDms = Math.max(-dragging.value.startWinS, Math.min(mT - dragging.value.startWinE, dms))
      winS.value = dragging.value.startWinS + clampedDms
      winE.value = dragging.value.startWinS + clampedDms + span
      break
    }
    case 'create':
      winS.value = Math.min(getMiniMs(dragging.value.startX), getMiniMs(event.offsetX))
      winE.value = Math.max(getMiniMs(dragging.value.startX), getMiniMs(event.offsetX))
      break
    case 'resize-left':
      winS.value = Math.max(0, Math.min(dragging.value.startWinS + dms, winE.value - 1))
      break
    case 'resize-right':
      winE.value = Math.min(mT, Math.max(dragging.value.startWinE + dms, winS.value + 1))
      break
  }
}

function onMiniMouseup() {
  dragging.value = null
}

function onMiniKeydown(event: KeyboardEvent) {
  if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return
  event.preventDefault()
  const span = winE.value - winS.value
  const shift = span * 0.2
  const mT = maxT.value
  if (event.key === 'ArrowLeft') {
    winS.value = Math.max(0, winS.value - shift)
    winE.value = winS.value + span
  } else {
    winE.value = Math.min(mT, winE.value + shift)
    winS.value = winE.value - span
  }
}

function zoomToProblems() {
  autoFocus()
}

function resetWindow() {
  initWindow()
}

function redraw() {
  drawMini()
  drawDetail()
}

onMounted(() => {
  const miniWrap = miniWrapRef.value
  if (!miniWrap) return

  initWindow()

  const ro = new ResizeObserver(entries => {
    const width = entries[0]?.contentRect.width ?? 400
    const miniCanvas = miniCanvasRef.value
    if (miniCanvas && miniCanvas.width !== Math.floor(width)) {
      miniCanvas.width = Math.floor(width)
    }
    const detailCanvas = detailCanvasRef.value
    if (detailCanvas && detailCanvas.width !== Math.floor(width)) {
      detailCanvas.width = Math.floor(width)
    }
    redraw()
  })
  ro.observe(miniWrap)
  onUnmounted(() => ro.disconnect())
})

watch(
  [() => props.exchanges, () => props.filterState, winS, winE],
  () => redraw(),
  { deep: false }
)

watch(
  () => props.exchanges.length,
  (newLen, oldLen) => {
    if (newLen > 0 && oldLen === 0) {
      initWindow()
      setTimeout(() => {
        autoFocus()
        redraw()
      }, 50)
    }
  }
)

// Suppress unused variable warnings
void tooltipStyle
void tooltipText
</script>

<template>
  <div class="minimap-detail">
    <!-- Toolbar -->
    <div class="toolbar">
      <span class="window-label">
        {{ (winS / 1000).toFixed(2) }}s – {{ (winE / 1000).toFixed(2) }}s
      </span>
      <button @click="zoomToProblems">Zoom to problems</button>
      <button @click="resetWindow">Reset window</button>
    </div>

    <!-- Minimap canvas wrapper -->
    <div ref="miniWrapRef" class="mini-wrap">
      <canvas
        ref="miniCanvasRef"
        :height="MINI_H"
        class="mini-canvas"
        role="application"
        aria-label="Timeline minimap"
        tabindex="0"
        @mousedown="onMiniMousedown"
        @mousemove="onMiniMousemove"
        @mouseup="onMiniMouseup"
        @mouseleave="onMiniMouseup"
        @click="onMiniClick"
        @keydown="onMiniKeydown"
      />
    </div>

    <!-- Detail canvas -->
    <div class="detail-wrap">
      <canvas
        ref="detailCanvasRef"
        class="detail-canvas"
        role="application"
        aria-label="Exchange detail"
      />
    </div>

    <!-- Tooltip -->
    <div class="tooltip" :style="tooltipStyle" aria-hidden="true">{{ tooltipText }}</div>
  </div>
</template>

<style scoped>
.minimap-detail {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}
.toolbar {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.toolbar button {
  padding: 0.25rem 0.6rem;
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text);
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.8rem;
}
.window-label {
  font-family: var(--font-mono);
  font-size: 0.8rem;
  color: var(--text-muted);
  flex: 1;
}
.mini-wrap {
  flex-shrink: 0;
  position: relative;
}
.mini-canvas {
  display: block;
  width: 100%;
  cursor: crosshair;
}
.detail-wrap {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
}
.detail-canvas {
  display: block;
  width: 100%;
}
.tooltip {
  position: fixed;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 4px 8px;
  font-size: 0.75rem;
  pointer-events: none;
  z-index: 200;
}
</style>
