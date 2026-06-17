import { onMounted, onUnmounted, ref, watch } from 'vue';
import type { DomainExchange, FacetState } from '../lib/model.ts';

export const MINI_H = 80;

const ML = 64;
const MT = 24;
const RH = 9;
const RG = 3;
const BH = 6;
const MAX_H = 32_767;
const DEFAULT_WINDOW = 200;
const EDGE_HIT = 6;
const HALF = 2;
const CANVAS_FALLBACK_W = 800;
const LABEL_MARGIN = 4;
const LABEL_OFFSET = 1;
const AXIS_OFFSET = 6;
const LEGEND_Y = 10;
const BAR_PADDING = 8;
const BAR_MIN_FILL = 2;
const WINDOW_MIN_SPAN = 1;
const WINDOW_MIN_W = 4;
const DRAG_THRESHOLD = 3;
const DETAIL_BOTTOM_PAD = 20;
const ZERO = 0;
const ONE = 1;
const TWO = 2;
const THREE = 3;
const BUCKET_COUNT = 50;
const SCORE_VIOLATION = 1e9;
const SCORE_RTT_MULT = 1000;
const KEY_ARROW_LEFT = 'ArrowLeft';
const KEY_ARROW_RIGHT = 'ArrowRight';

interface Colors {
  none: string;
  retry: string;
  slow: string;
  timeout: string;
  violation: string;
}

const getColors = (canvas: HTMLCanvasElement): Colors => {
  const style = getComputedStyle(canvas);
  return {
    none: style.getPropertyValue('--dim-none').trim(),
    retry: style.getPropertyValue('--dim-retry').trim(),
    slow: style.getPropertyValue('--dim-slow').trim(),
    timeout: style.getPropertyValue('--dim-timeout').trim(),
    violation: style.getPropertyValue('--dim-violation').trim(),
  };
};

const getColor = (ex: DomainExchange, slowMs: number, colors: Colors): string => {
  if (ex.isTimeout) {
    return colors.timeout;
  }
  if (ex.violations.length > ZERO) {
    return colors.violation;
  }
  if (ex.rtt > slowMs) {
    return colors.slow;
  }
  if (ex.attemptCount > ONE) {
    return colors.retry;
  }
  return colors.none;
};

const getMutedColor = (canvas: HTMLCanvasElement): string =>
  getComputedStyle(canvas).getPropertyValue('--color-text-muted').trim() || '#6c757d';

const maxRttOf = (exchanges: DomainExchange[]): number => {
  let maxRtt = ZERO;
  for (let idx = ZERO; idx < exchanges.length; idx += ONE) {
    const ex = exchanges[idx];
    if (ex && ex.rtt > maxRtt) {
      maxRtt = ex.rtt;
    }
  }
  return maxRtt;
};

interface UseMinimapDetailProps {
  exchanges: DomainExchange[];
  facetState: FacetState;
}

type EmitFn = (event: 'focus-exchange', seq: number) => void;

interface UseMinimapDetailReturn {
  containerRef: ReturnType<typeof ref<HTMLDivElement | null>>;
  detailRef: ReturnType<typeof ref<HTMLCanvasElement | null>>;
  minimapRef: ReturnType<typeof ref<HTMLCanvasElement | null>>;
  onKeyDown: (event: KeyboardEvent) => void;
  onMinimapClick: (event: MouseEvent) => void;
  onMinimapMouseDown: (event: MouseEvent) => void;
  onMinimapMouseMove: (event: MouseEvent) => void;
  onMinimapMouseUp: (event: MouseEvent) => void;
}

export const useMinimapDetail = (
  getProps: () => UseMinimapDetailProps,
  emit: EmitFn,
): UseMinimapDetailReturn => {
  const minimapRef = ref<HTMLCanvasElement | null>(null);
  const detailRef = ref<HTMLCanvasElement | null>(null);
  const containerRef = ref<HTMLDivElement | null>(null);
  const windowStart = ref(ZERO);
  const windowEnd = ref(DEFAULT_WINDOW);

  const drawMinimapBars = (ctx: CanvasRenderingContext2D, canvasW: number): void => {
    const { exchanges, facetState } = getProps();
    const total = exchanges.length;
    const miniCanvas = minimapRef.value;
    if (!miniCanvas) {
      return;
    }
    const colors = getColors(miniCanvas);
    for (let idx = ZERO; idx < total; idx += ONE) {
      const ex = exchanges[idx];
      if (ex) {
        const xPos = Math.floor((idx / total) * canvasW);
        const barW = Math.max(ONE, Math.ceil(canvasW / total));
        ctx.fillStyle = getColor(ex, facetState.slowMs, colors);
        ctx.fillRect(xPos, (MINI_H - BH) / HALF, barW, BH);
      }
    }
  };

  const drawMinimapWindow = (
    ctx: CanvasRenderingContext2D,
    canvas: HTMLCanvasElement,
    total: number,
    canvasW: number,
    canvasH: number,
  ): void => {
    const style = getComputedStyle(canvas);
    const x1 = Math.floor((Math.max(ZERO, windowStart.value) / total) * canvasW);
    const x2 = Math.floor((Math.min(total - ONE, windowEnd.value) / total) * canvasW);
    ctx.strokeStyle = style.getPropertyValue('--color-minimap-window-stroke').trim();
    ctx.lineWidth = TWO;
    ctx.strokeRect(x1, TWO, Math.max(WINDOW_MIN_W, x2 - x1), canvasH - LABEL_MARGIN);
    ctx.fillStyle = style.getPropertyValue('--color-minimap-window-fill').trim();
    ctx.fillRect(x1 + ONE, THREE, Math.max(TWO, x2 - x1 - ONE), canvasH - AXIS_OFFSET);
  };

  const drawMinimap = (): void => {
    const canvas = minimapRef.value;
    if (!canvas) {
      return;
    }
    const ctx = canvas.getContext('2d');
    if (!ctx) {
      return;
    }
    const { exchanges } = getProps();
    const total = exchanges.length;
    const canvasW = canvas.width;
    const canvasH = canvas.height;
    const bgStyle = getComputedStyle(canvas);
    ctx.clearRect(ZERO, ZERO, canvasW, canvasH);
    ctx.fillStyle = bgStyle.getPropertyValue('--color-surface').trim() || '#f8f9fa';
    ctx.fillRect(ZERO, ZERO, canvasW, canvasH);
    if (total === ZERO) {
      return;
    }
    drawMinimapBars(ctx, canvasW);
    drawMinimapWindow(ctx, canvas, total, canvasW, canvasH);
  };

  const drawDetailRow = (
    ctx: CanvasRenderingContext2D,
    ex: DomainExchange,
    rowIdx: number,
    canvasW: number,
    slowMs: number,
    colors: Colors,
    maxRttInWindow: number,
    mutedColor: string,
  ): void => {
    const yPos = MT + rowIdx * (RH + RG);
    ctx.fillStyle = mutedColor;
    ctx.textAlign = 'right';
    ctx.fillText(`${ex.sentAtMs.toFixed(ZERO)}ms`, ML - LABEL_MARGIN, yPos + RH - LABEL_OFFSET);
    const barW = canvasW - ML - BAR_PADDING;
    let rttFraction = ZERO;
    if (maxRttInWindow > ZERO) {
      rttFraction = ex.rtt / maxRttInWindow;
    }
    const fillW = Math.max(BAR_MIN_FILL, Math.floor(rttFraction * barW));
    ctx.fillStyle = getColor(ex, slowMs, colors);
    ctx.fillRect(ML, yPos, fillW, RH);
  };

  const drawDetailAxes = (
    ctx: CanvasRenderingContext2D,
    canvasW: number,
    firstEx: DomainExchange,
    lastEx: DomainExchange,
    maxRttInWindow: number,
    mutedColor: string,
  ): void => {
    ctx.fillStyle = mutedColor;
    if (lastEx.sentAtMs - firstEx.sentAtMs > ZERO) {
      ctx.textAlign = 'left';
      ctx.font = '9px system-ui, sans-serif';
      ctx.fillText(`+${firstEx.sentAtMs.toFixed(ZERO)}ms`, ML, MT - AXIS_OFFSET);
      ctx.textAlign = 'right';
      ctx.fillText(`+${lastEx.sentAtMs.toFixed(ZERO)}ms`, canvasW - LABEL_MARGIN, MT - AXIS_OFFSET);
    }
    if (maxRttInWindow > ZERO) {
      ctx.font = '9px system-ui, sans-serif';
      ctx.textAlign = 'right';
      ctx.fillText(`max ${maxRttInWindow.toFixed(ZERO)}ms RTT`, canvasW - LABEL_MARGIN, LEGEND_Y);
    }
  };

  const drawDetail = (): void => {
    const canvas = detailRef.value;
    if (!canvas) {
      return;
    }
    const ctx = canvas.getContext('2d');
    if (!ctx) {
      return;
    }
    const { exchanges, facetState } = getProps();
    const ws = Math.max(ZERO, windowStart.value);
    const we = Math.min(exchanges.length - ONE, windowEnd.value);
    const windowExchanges = exchanges.slice(ws, we + ONE);
    const rows = windowExchanges.length;
    const canvasW = canvas.width;
    const canvasH = canvas.height;
    const mutedColor = getMutedColor(canvas);
    const bgStyle = getComputedStyle(canvas);
    ctx.clearRect(ZERO, ZERO, canvasW, canvasH);
    ctx.fillStyle = bgStyle.getPropertyValue('--color-bg').trim() || '#ffffff';
    ctx.fillRect(ZERO, ZERO, canvasW, canvasH);
    if (rows === ZERO) {
      ctx.fillStyle = mutedColor;
      ctx.font = '13px system-ui, sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText('No exchanges in window', canvasW / HALF, canvasH / HALF);
      return;
    }
    ctx.font = '10px var(--font-mono, monospace)';
    const colors = getColors(canvas);
    const maxRttInWindow = maxRttOf(windowExchanges);
    for (let rowIdx = ZERO; rowIdx < rows; rowIdx += ONE) {
      const ex = windowExchanges[rowIdx];
      if (ex) {
        drawDetailRow(
          ctx,
          ex,
          rowIdx,
          canvasW,
          facetState.slowMs,
          colors,
          maxRttInWindow,
          mutedColor,
        );
      }
    }
    const firstEx = windowExchanges.at(ZERO);
    const lastEx = windowExchanges.at(-ONE);
    if (firstEx && lastEx) {
      drawDetailAxes(ctx, canvasW, firstEx, lastEx, maxRttInWindow, mutedColor);
    }
  };

  const updateDetailHeight = (): void => {
    const canvas = detailRef.value;
    if (!canvas) {
      return;
    }
    const { exchanges } = getProps();
    const ws = Math.max(ZERO, windowStart.value);
    const we = Math.min(exchanges.length - ONE, windowEnd.value);
    const rows = Math.max(ZERO, we - ws + ONE);
    const newH = Math.min(MAX_H, MT + rows * (RH + RG) + DETAIL_BOTTOM_PAD);
    if (canvas.height !== newH) {
      canvas.height = newH;
    }
  };

  const draw = (): void => {
    updateDetailHeight();
    drawMinimap();
    drawDetail();
  };

  const scoreBucket = (exchanges: DomainExchange[], start: number, end: number): number => {
    let score = ZERO;
    let maxRtt = ZERO;
    let count = ZERO;
    for (let idx = start; idx < end; idx += ONE) {
      const ex = exchanges[idx];
      if (ex) {
        count += ONE;
        if (ex.violations.length > ZERO || ex.isTimeout) {
          score += SCORE_VIOLATION;
        }
        if (ex.rtt > maxRtt) {
          maxRtt = ex.rtt;
        }
      }
    }
    return score + maxRtt * SCORE_RTT_MULT + count;
  };

  const autoFocus = (): void => {
    const { exchanges } = getProps();
    const total = exchanges.length;
    if (total === ZERO) {
      return;
    }
    const bucketSize = Math.ceil(total / BUCKET_COUNT);
    let bestScore = -ONE;
    let bestBucket = ZERO;
    for (let bucket = ZERO; bucket < BUCKET_COUNT; bucket += ONE) {
      const start = bucket * bucketSize;
      const score = scoreBucket(exchanges, start, Math.min(total, start + bucketSize));
      if (score > bestScore) {
        bestScore = score;
        bestBucket = bucket;
      }
    }
    const start = bestBucket * bucketSize;
    const halfWindow = Math.floor(DEFAULT_WINDOW / HALF);
    windowStart.value = Math.max(ZERO, start - halfWindow);
    windowEnd.value = Math.min(total - ONE, start + halfWindow);
  };

  type DragMode = 'creating' | 'none' | 'panning' | 'resizing-left' | 'resizing-right';
  let dragMode: DragMode = 'none';
  let dragStartX = ZERO;
  let dragStartWs = ZERO;
  let dragStartWe = ZERO;

  const xToIndex = (xPos: number, canvasW: number): number => {
    const total = getProps().exchanges.length;
    if (total === ZERO) {
      return ZERO;
    }
    return Math.round((xPos / canvasW) * (total - ONE));
  };

  const applyDragMove = (xPos: number, canvasW: number): void => {
    const total = getProps().exchanges.length;
    const delta = xToIndex(xPos, canvasW) - xToIndex(dragStartX, canvasW);
    if (dragMode === 'creating') {
      const idx = xToIndex(xPos, canvasW);
      const anchor = xToIndex(dragStartX, canvasW);
      windowStart.value = Math.min(anchor, idx);
      windowEnd.value = Math.max(anchor, idx);
    } else if (dragMode === 'panning') {
      const newWs = Math.max(ZERO, dragStartWs + delta);
      const span = dragStartWe - dragStartWs;
      const newWe = Math.min(total - ONE, newWs + span);
      windowStart.value = Math.max(ZERO, newWe - span);
      windowEnd.value = newWe;
    } else if (dragMode === 'resizing-left') {
      windowStart.value = Math.max(
        ZERO,
        Math.min(dragStartWe - WINDOW_MIN_SPAN, dragStartWs + delta),
      );
    } else if (dragMode === 'resizing-right') {
      windowEnd.value = Math.min(
        total - ONE,
        Math.max(dragStartWs + WINDOW_MIN_SPAN, dragStartWe + delta),
      );
    }
  };

  const onMinimapMouseDown = (event: MouseEvent): void => {
    const canvas = minimapRef.value;
    if (!canvas) {
      return;
    }
    const rect = canvas.getBoundingClientRect();
    const xPos = event.clientX - rect.left;
    const total = getProps().exchanges.length;
    if (total === ZERO) {
      return;
    }
    const canvasW = canvas.width;
    const ws = windowStart.value;
    const we = windowEnd.value;
    const x1 = (ws / total) * canvasW;
    const x2 = (we / total) * canvasW;
    dragStartX = xPos;
    dragStartWs = ws;
    dragStartWe = we;
    if (Math.abs(xPos - x1) <= EDGE_HIT) {
      dragMode = 'resizing-left';
    } else if (Math.abs(xPos - x2) <= EDGE_HIT) {
      dragMode = 'resizing-right';
    } else if (xPos >= x1 && xPos <= x2) {
      dragMode = 'panning';
    } else {
      dragMode = 'creating';
      const idx = xToIndex(xPos, canvasW);
      windowStart.value = idx;
      windowEnd.value = Math.min(total - ONE, idx + DEFAULT_WINDOW);
      draw();
    }
    event.preventDefault();
  };

  const onMinimapMouseMove = (event: MouseEvent): void => {
    const canvas = minimapRef.value;
    if (!canvas || dragMode === 'none') {
      return;
    }
    const rect = canvas.getBoundingClientRect();
    applyDragMove(event.clientX - rect.left, canvas.width);
    draw();
  };

  const onMinimapMouseUp = (_event: MouseEvent): void => {
    if (dragMode !== 'none') {
      dragMode = 'none';
      const mid = Math.floor((windowStart.value + windowEnd.value) / HALF);
      const ex = getProps().exchanges[mid];
      if (ex) {
        emit('focus-exchange', ex.seq);
      }
    }
  };

  const onMinimapClick = (event: MouseEvent): void => {
    const canvas = minimapRef.value;
    if (!canvas) {
      return;
    }
    const rect = canvas.getBoundingClientRect();
    const xPos = event.clientX - rect.left;
    if (Math.abs(xPos - dragStartX) > DRAG_THRESHOLD) {
      return;
    }
    const { exchanges } = getProps();
    const total = exchanges.length;
    if (total === ZERO) {
      return;
    }
    const idx = xToIndex(xPos, canvas.width);
    const halfW = Math.floor(DEFAULT_WINDOW / HALF);
    windowStart.value = Math.max(ZERO, idx - halfW);
    windowEnd.value = Math.min(total - ONE, idx + halfW);
    const ex = exchanges[idx];
    if (ex) {
      emit('focus-exchange', ex.seq);
    }
    draw();
  };

  const onKeyDown = (event: KeyboardEvent): void => {
    const total = getProps().exchanges.length;
    if (total === ZERO) {
      return;
    }
    const span = windowEnd.value - windowStart.value;
    if (event.key === KEY_ARROW_LEFT) {
      event.preventDefault();
      const newWs = Math.max(ZERO, windowStart.value - ONE);
      windowStart.value = newWs;
      windowEnd.value = Math.min(total - ONE, newWs + span);
      draw();
    } else if (event.key === KEY_ARROW_RIGHT) {
      event.preventDefault();
      const newWe = Math.min(total - ONE, windowEnd.value + ONE);
      windowEnd.value = newWe;
      windowStart.value = Math.max(ZERO, newWe - span);
      draw();
    }
  };

  let resizeObserver: ResizeObserver | null = null;
  let themeObserver: MutationObserver | null = null;

  const syncCanvasWidth = (): void => {
    const mini = minimapRef.value;
    const detail = detailRef.value;
    if (mini) {
      mini.width = mini.clientWidth || mini.offsetWidth || CANVAS_FALLBACK_W;
    }
    if (detail) {
      detail.width = detail.clientWidth || detail.offsetWidth || CANVAS_FALLBACK_W;
    }
  };

  onMounted(() => {
    const mini = minimapRef.value;
    if (!mini) {
      return;
    }
    syncCanvasWidth();
    mini.height = MINI_H;
    resizeObserver = new ResizeObserver(() => {
      syncCanvasWidth();
      draw();
    });
    resizeObserver.observe(mini);
    themeObserver = new MutationObserver(() => {
      drawMinimap();
      drawDetail();
    });
    themeObserver.observe(document.documentElement, { attributeFilter: ['data-theme'] });
    autoFocus();
    draw();
  });

  onUnmounted(() => {
    if (resizeObserver !== null) {
      resizeObserver.disconnect();
    }
    if (themeObserver !== null) {
      themeObserver.disconnect();
      themeObserver = null;
    }
  });

  watch(
    () => getProps().exchanges,
    () => {
      autoFocus();
      draw();
    },
  );
  watch(
    () => getProps().facetState,
    () => {
      draw();
    },
  );

  return {
    containerRef,
    detailRef,
    minimapRef,
    onKeyDown,
    onMinimapClick,
    onMinimapMouseDown,
    onMinimapMouseMove,
    onMinimapMouseUp,
  };
};
