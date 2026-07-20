import { onMounted, onUnmounted, ref } from "vue";
import type { Ref } from "vue";

const DEFAULT_CONTAINER_HEIGHT = 600;

export interface VirtualScrollState {
	containerEl: Ref<HTMLElement | null>;
	containerHeight: Ref<number>;
	onScroll: (e: Event) => void;
	scrollTop: Ref<number>;
}

export function useVirtualScroll(): VirtualScrollState {
	const scrollTop = ref(0);
	const containerHeight = ref(DEFAULT_CONTAINER_HEIGHT);
	const containerEl = ref<HTMLElement | null>(null);

	function measure(): void {
		if (containerEl.value !== null) {
			containerHeight.value =
				containerEl.value.clientHeight || DEFAULT_CONTAINER_HEIGHT;
		}
	}

	let resizeObserver: ResizeObserver | null = null;

	onMounted((): void => {
		measure();
		if (containerEl.value !== null) {
			resizeObserver = new ResizeObserver(measure);
			resizeObserver.observe(containerEl.value);
		}
	});

	onUnmounted((): void => {
		resizeObserver?.disconnect();
	});

	function onScroll(e: Event): void {
		scrollTop.value = (e.target as HTMLElement).scrollTop;
	}

	return { containerEl, containerHeight, onScroll, scrollTop };
}
