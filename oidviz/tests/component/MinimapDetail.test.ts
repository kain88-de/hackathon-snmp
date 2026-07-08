import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import type { MockInstance } from "vitest";
import { mount } from "@vue/test-utils";
import { nextTick } from "vue";
import { MAX_H, MT, RG, RH } from "../../src/lib/minimapDraw.ts";
import { asOid } from "../../src/lib/model.ts";
import type { DomainExchange, FacetState } from "../../src/lib/model.ts";
import MinimapDetail from "../../src/components/MinimapDetail.vue";
import { makeExchange, makeFacetState } from "./helpers.ts";

// happy-dom has no canvas support: getContext("2d") natively returns null,
// which makes drawMinimap() return 0 and leaves the component's totalCols
// stuck at 0 — disabling ALL minimap hover/click/drag/keyboard logic and
// forcing the detail window to always be the full exchange list. Stubbing a
// minimal 2D context unblocks that interaction logic: totalCols becomes the
// canvas's real width. Nothing about drawn pixels is asserted here (that is
// tests/unit/minimapDraw.test.ts's job) — the stub only records no-op calls.
function makeFake2dContext(): CanvasRenderingContext2D {
	return {
		fillRect: vi.fn(),
		strokeRect: vi.fn(),
		fillText: vi.fn(),
		fillStyle: "",
		strokeStyle: "",
		lineWidth: 0,
		font: "",
		textAlign: "left",
		textBaseline: "top",
	} as unknown as CanvasRenderingContext2D;
}

// Coordinate model under happy-dom: there is no layout engine, so
// clientWidth is 0 and redraw()'s resize guard never fires — the canvases
// keep the HTML default width of 300, meaning totalCols === 300. All
// getBoundingClientRect() rects are zero-origin, so a MouseEvent's clientX
// IS the minimap column and clientY IS the detail-canvas y coordinate.

// With 300 columns, sentAtMs values chosen as integers in [0, 299] map to
// exactly that column index: col = floor((t - minT) / range * (cols - 1))
// with minT = 0 and range = 299.
function makeHoverSet(): DomainExchange[] {
	return [
		makeExchange({ seq: 1, sentAtMs: 0 }),
		makeExchange({ seq: 2, sentAtMs: 100, rtt: 2000 }),
		makeExchange({ seq: 3, sentAtMs: 100 }),
		makeExchange({ seq: 4, sentAtMs: 299 }),
	];
}

function mountMinimap(
	exchanges: DomainExchange[],
	facetState: FacetState = makeFacetState(),
) {
	return mount(MinimapDetail, { props: { exchanges, facetState } });
}

function dispatchMouse(
	el: Element,
	type: string,
	clientX: number,
	clientY = 30,
): void {
	el.dispatchEvent(new MouseEvent(type, { clientX, clientY }));
}

// y coordinate that lands inside detail row `i` (rows start at MT, each
// RH + RG tall).
function detailRowY(i: number): number {
	return MT + i * (RH + RG) + 4;
}

describe("MinimapDetail", () => {
	let ctxSpy: MockInstance;

	beforeEach(() => {
		ctxSpy = vi
			.spyOn(HTMLCanvasElement.prototype, "getContext")
			.mockImplementation(() => makeFake2dContext());
	});

	afterEach(() => {
		vi.restoreAllMocks();
	});

	describe("rendering", () => {
		// a single default makeExchange() — with any non-empty exchange list
		// the component must render both canvases plus the five-entry colour
		// legend in worst-to-best severity order, since the legend is the only
		// key for reading the (canvas-drawn, unlabelled) colour coding.
		test("renders the minimap, the detail canvas, and the severity legend", () => {
			const wrapper = mountMinimap([makeExchange()]);

			expect(wrapper.find(".minimap-canvas").exists()).toBe(true);
			expect(wrapper.find(".detail-canvas").exists()).toBe(true);

			const legendItems = wrapper.findAll(".legend-item");
			expect(legendItems.map((item) => item.text())).toEqual([
				"Timeout",
				"Violation",
				"Slow",
				"Retry",
				"Normal",
			]);
		});

		// non-empty exchanges with getContext mocked back to null (happy-dom's
		// real behavior) — mount runs redraw() and runAutoFocus() against a
		// null 2D context, and the component must tolerate that without
		// throwing rather than assuming a context always exists.
		test("mounting with data survives an unavailable 2D context", () => {
			ctxSpy.mockReturnValue(null);

			expect(() => mountMinimap(makeHoverSet())).not.toThrow();
		});
	});

	describe("minimap interaction", () => {
		// makeHoverSet(): exactly 2 of the 4 exchanges sit at sentAtMs 100
		// (= column 100), one of them slow (rtt 2000 > slowMs 1000), the other
		// normal — hovering column 100 must report the per-bucket count "2"
		// (not the total 4), the WORST status in the bucket ("Slow", not the
		// other exchange's "Normal"), and the column's time offset
		// (100/300 * 299 ≈ +100ms).
		test("hovering a minimap column shows that bucket's count, worst status, and time offset", () => {
			const wrapper = mountMinimap(makeHoverSet());
			const mini = wrapper.find(".minimap-canvas");

			dispatchMouse(mini.element, "mousemove", 100);

			const tooltip = wrapper.find(".canvas-tooltip");
			expect((tooltip.element as HTMLElement).style.display).toBe("block");
			expect(tooltip.text()).toContain("2 exchanges");
			expect(tooltip.text()).toContain("Status: Slow");
			expect(tooltip.text()).toContain("+100ms");
		});

		// makeHoverSet(), hover a populated column then dispatch mouseleave —
		// the tooltip must not linger once the pointer leaves the minimap.
		test("leaving the minimap hides the tooltip", () => {
			const wrapper = mountMinimap(makeHoverSet());
			const mini = wrapper.find(".minimap-canvas");

			dispatchMouse(mini.element, "mousemove", 100);
			mini.element.dispatchEvent(new MouseEvent("mouseleave"));

			const tooltip = wrapper.find(".canvas-tooltip");
			expect((tooltip.element as HTMLElement).style.display).toBe("none");
		});

		// makeHoverSet(): the slow exchange makes column 100 the auto-focus
		// winner, so the initial selection is [85, 115) and column 200 is far
		// outside it (hover cursor: crosshair). A click (mousedown + mouseup
		// at the same column) at 200 must re-center a full-width window
		// [185, 215) there: a subsequent hover at 200 then sits deep inside
		// the selection, giving the "grab" pan cursor. If re-centering were
		// broken, the cursor would stay "crosshair" (selection unchanged) or
		// read "ew-resize" (selection left as the 1-column [200, 201) that
		// mousedown creates) — only a real re-center produces "grab".
		test("a click without dragging re-centers the selection window on the clicked column", () => {
			const wrapper = mountMinimap(makeHoverSet());
			const mini = wrapper.find(".minimap-canvas");
			const miniEl = mini.element as HTMLElement;

			dispatchMouse(mini.element, "mousemove", 200);
			expect(miniEl.style.cursor).toBe("crosshair");

			dispatchMouse(mini.element, "mousedown", 200);
			dispatchMouse(mini.element, "mouseup", 200);

			dispatchMouse(mini.element, "mousemove", 200);
			expect(miniEl.style.cursor).toBe("grab");
		});

		// makeHoverSet(), then a drag from column 140 to 190 (both outside
		// the auto-focus window [85, 115)) creating the selection [140, 191)
		// — subsequent hovers must show cursors matching position relative to
		// THAT selection: crosshair outside, grab in the interior, ew-resize
		// within 6 columns of either edge. If the drag had not moved the
		// selection, columns 143/165/188 would all sit outside [85, 115) and
		// uniformly read "crosshair".
		test("after dragging a selection, the cursor distinguishes outside, pan, and resize zones", () => {
			const wrapper = mountMinimap(makeHoverSet());
			const mini = wrapper.find(".minimap-canvas");
			const miniEl = mini.element as HTMLElement;

			dispatchMouse(mini.element, "mousedown", 140);
			dispatchMouse(mini.element, "mousemove", 190);
			dispatchMouse(mini.element, "mouseup", 190);

			dispatchMouse(mini.element, "mousemove", 50);
			expect(miniEl.style.cursor).toBe("crosshair");

			dispatchMouse(mini.element, "mousemove", 165);
			expect(miniEl.style.cursor).toBe("grab");

			dispatchMouse(mini.element, "mousemove", 143);
			expect(miniEl.style.cursor).toBe("ew-resize");

			dispatchMouse(mini.element, "mousemove", 188);
			expect(miniEl.style.cursor).toBe("ew-resize");
		});

		// makeHoverSet(): auto-focus selects [85, 115), width 30, so an arrow
		// key shifts by round(30 * 0.2) = 6 columns. Column 82 starts outside
		// the selection (crosshair); after ArrowLeft the selection is
		// [79, 109) and 82 is within 6 columns of its left edge (ew-resize);
		// ArrowRight shifts back to [85, 115), putting 82 outside again
		// (crosshair). A broken keyboard handler would leave the cursor at 82
		// "crosshair" throughout.
		test("arrow keys shift the selection window left and right", () => {
			const wrapper = mountMinimap(makeHoverSet());
			const mini = wrapper.find(".minimap-canvas");
			const miniEl = mini.element as HTMLElement;

			dispatchMouse(mini.element, "mousemove", 82);
			expect(miniEl.style.cursor).toBe("crosshair");

			mini.element.dispatchEvent(
				new KeyboardEvent("keydown", { key: "ArrowLeft", cancelable: true }),
			);
			dispatchMouse(mini.element, "mousemove", 82);
			expect(miniEl.style.cursor).toBe("ew-resize");

			mini.element.dispatchEvent(
				new KeyboardEvent("keydown", { key: "ArrowRight", cancelable: true }),
			);
			dispatchMouse(mini.element, "mousemove", 82);
			expect(miniEl.style.cursor).toBe("crosshair");
		});

		// three equal-rtt exchanges (seq 10/20/30 at sentAtMs 0/150/299):
		// auto-focus picks column 0 (first best bucket), window [0, 15) —
		// only seq 10 falls in that time range, so detail row 0 is seq 10.
		// Dragging the minimap to [140, 161) re-windows the detail view to
		// the ~[139.5, 160.5]ms range, where row 0 is seq 20. Clicking detail
		// row 0 before and after the drag must therefore emit different seqs
		// — this fails both if the drag doesn't move the selection AND if the
		// detail view ignores the selection window (full list keeps seq 10 at
		// row 0 either way).
		test("dragging a new selection changes which exchanges the detail view shows", () => {
			const wrapper = mountMinimap([
				makeExchange({ seq: 10, sentAtMs: 0 }),
				makeExchange({ seq: 20, sentAtMs: 150 }),
				makeExchange({ seq: 30, sentAtMs: 299 }),
			]);
			const mini = wrapper.find(".minimap-canvas");
			const detail = wrapper.find(".detail-canvas");

			dispatchMouse(detail.element, "click", 50, detailRowY(0));

			dispatchMouse(mini.element, "mousedown", 140);
			dispatchMouse(mini.element, "mousemove", 160);
			dispatchMouse(mini.element, "mouseup", 160);

			dispatchMouse(detail.element, "click", 50, detailRowY(0));

			expect(wrapper.emitted("focus-exchange")).toEqual([[10], [20]]);
		});
	});

	describe("detail interaction", () => {
		// a single exchange with a 17-char requestOid, rtt 123.4 — hovering
		// its detail row must show the OID untruncated (no "…" for OIDs of 40
		// chars or fewer), the RTT formatted to one decimal ("123.4ms" proves
		// neither rounding to "123ms" nor full precision), and the status;
		// mouseleave must then hide the tooltip.
		test("hovering a detail row shows the full OID, RTT, and status", () => {
			const wrapper = mountMinimap([
				makeExchange({
					requestOid: asOid("1.3.6.1.2.1.1.1.0"),
					rtt: 123.4,
					sentAtMs: 0,
				}),
			]);
			const detail = wrapper.find(".detail-canvas");
			const tooltip = wrapper.find(".canvas-tooltip");

			dispatchMouse(detail.element, "mousemove", 50, detailRowY(0));
			expect((tooltip.element as HTMLElement).style.display).toBe("block");
			expect(tooltip.text()).toContain("1.3.6.1.2.1.1.1.0");
			expect(tooltip.text()).not.toContain("…");
			expect(tooltip.text()).toContain("RTT: 123.4ms");
			expect(tooltip.text()).toContain("Status: Normal");

			detail.element.dispatchEvent(new MouseEvent("mouseleave"));
			expect((tooltip.element as HTMLElement).style.display).toBe("none");
		});

		// a single exchange whose requestOid is 50 chars — the detail tooltip
		// must truncate OIDs over 40 chars to their first 40 chars plus "…"
		// so long OIDs cannot blow up the fixed-position tooltip, while still
		// showing RTT and status.
		test("the detail tooltip truncates OIDs longer than 40 characters", () => {
			const longOid = "1.3.6.1.4.1.99999.1.2.3.4.5.6.7.8.9.10.11.12.13.14";
			const wrapper = mountMinimap([
				makeExchange({ requestOid: asOid(longOid), sentAtMs: 0 }),
			]);
			const detail = wrapper.find(".detail-canvas");

			dispatchMouse(detail.element, "mousemove", 50, detailRowY(0));

			const tooltip = wrapper.find(".canvas-tooltip");
			expect(tooltip.text()).toContain(`${longOid.slice(0, 40)}…`);
			expect(tooltip.text()).not.toContain(longOid);
			expect(tooltip.text()).toContain("RTT: 100.0ms");
			expect(tooltip.text()).toContain("Status: Normal");
		});

		// two exchanges (seq 7 then seq 8) at the same sentAtMs, both inside
		// the auto-focused window, rendering as detail rows 0 and 1 in array
		// order — clicking inside ROW 1 must emit focus-exchange with seq 8,
		// proving the row-index-to-exchange mapping (a click mapped to the
		// wrong row would emit 7).
		test("clicking a detail row focuses that row's exchange", () => {
			const wrapper = mountMinimap([
				makeExchange({ seq: 7, sentAtMs: 0 }),
				makeExchange({ seq: 8, sentAtMs: 0 }),
			]);
			const detail = wrapper.find(".detail-canvas");

			dispatchMouse(detail.element, "click", 50, detailRowY(1));

			expect(wrapper.emitted("focus-exchange")).toEqual([[8]]);
		});

		// two exchanges → two detail rows; a click at row index 10 (far below
		// the last row) and one above the header margin must both emit
		// nothing, since neither maps to an exchange.
		test("clicking outside the detail rows focuses nothing", () => {
			const wrapper = mountMinimap([
				makeExchange({ seq: 7, sentAtMs: 0 }),
				makeExchange({ seq: 8, sentAtMs: 0 }),
			]);
			const detail = wrapper.find(".detail-canvas");

			dispatchMouse(detail.element, "click", 50, detailRowY(10));
			dispatchMouse(detail.element, "click", 50, MT - 10);

			expect(wrapper.emitted("focus-exchange")).toBeUndefined();
		});
	});

	describe("truncation warning", () => {
		// makeHoverSet(): 4 rows, far under drawDetail's MAX_H row cap — the
		// truncation warning must stay hidden so ordinary traces never show it.
		test("a small window does not render a truncation warning", async () => {
			const wrapper = mountMinimap(makeHoverSet());
			await nextTick();

			const warning = wrapper.find(".detail-truncation");
			expect(warning.classes()).not.toContain("detail-truncation--visible");
		});

		// 3000 exchanges all sharing makeExchange()'s default sentAtMs: 0 — they
		// collapse into a single minimap bucket, so auto-focus's window around
		// that bucket still contains the entire list (findings.md #4's repro
		// needs every row in the detail window, not just a narrow slice of it).
		// drawDetail's real row-counting logic runs here (the fake 2D context
		// is a no-op spy, not a stub that short-circuits the loop), so the
		// hidden count below is the actual MAX_H-vs-row-pitch arithmetic, not a
		// guess: only floor((MAX_H - MT - RH) / (RH + RG)) + 1 rows fit before
		// a row's own height would cross MAX_H.
		test("a window with more rows than the canvas can show renders a truncation warning naming the hidden count", async () => {
			const rows = 3000;
			const exchanges = Array.from({ length: rows }, (_, i) =>
				makeExchange({ seq: i + 1 }),
			);
			const maxVisibleRows = Math.floor((MAX_H - MT - RH) / (RH + RG)) + 1;
			const expectedHidden = rows - maxVisibleRows;

			const wrapper = mountMinimap(exchanges);
			await nextTick();

			const warning = wrapper.find(".detail-truncation");
			expect(warning.classes()).toContain("detail-truncation--visible");
			expect(warning.text()).toContain(`${expectedHidden} exchanges hidden`);
		});
	});
});
