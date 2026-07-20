import { test, expect } from "@playwright/test";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { MT, RG, RH } from "../../src/lib/minimapDraw.ts";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const CANONICAL_DATA_PATH = path.resolve(
	__dirname,
	"./test-data/canonical.oidtrace.jsonl.gz",
);

// Real ~5000-exchange capture (also used by findings.spec.ts) — needed here
// as a window large enough to exceed the detail canvas's row capacity.
const TRACE_5K_DATA_PATH = path.resolve(
	__dirname,
	"../../../traceformat/examples/trace-5k.oidtrace.jsonl.gz",
);

async function openMinimapDetail(
	page: import("@playwright/test").Page,
	fixturePath: string = CANONICAL_DATA_PATH,
) {
	await page.goto("/");

	const fileInput = page.locator('input[type="file"]');
	await fileInput.setInputFiles(fixturePath);

	await expect(page.locator('[data-phase="viewer"]')).toBeVisible({
		timeout: 10000,
	});

	await page.getByRole("button", { name: "Minimap + Detail" }).click();
}

// The Minimap+Detail view renders two canvases (minimap overview + detail);
// both must have non-zero layout width once mounted — not fixture-dependent.
test("both canvases render with non-zero width", async ({ page }) => {
	await openMinimapDetail(page);

	const canvases = page.locator(".minimap-detail canvas");
	await expect(canvases).toHaveCount(2);

	const widths = await canvases.evaluateAll((els) =>
		els.map((el) => (el as HTMLElement).clientWidth),
	);
	for (const w of widths) {
		expect(w).toBeGreaterThan(0);
	}
});

// The colour legend is a fixed, data-independent list of the 5 exchange
// statuses in a fixed order — not fixture-dependent.
test("colour legend shows all 5 statuses in order", async ({ page }) => {
	await openMinimapDetail(page);

	const legendItems = page.locator(".legend-item");
	await expect(legendItems).toHaveCount(5);

	// Array form of toHaveText matches multiple elements positionally, one
	// regex per element in DOM order. toContainText with an array on the
	// .color-legend wrapper does NOT do a substring-per-item check.
	await expect(legendItems).toHaveText([
		/Timeout/,
		/Violation/,
		/Slow/,
		/Retry/,
		/Normal/,
	]);
});

// The minimap canvas gets tabindex="0" in onMounted so keyboard users can
// reach it — not fixture-dependent.
test("minimap canvas is keyboard-focusable", async ({ page }) => {
	await openMinimapDetail(page);

	const miniCanvas = page.locator(".minimap-canvas");
	await miniCanvas.focus();
	await expect(miniCanvas).toBeFocused();
});

// Canvas pixel/selection state isn't introspectable from Playwright without
// adding test-only instrumentation (out of scope); this only checks that a
// drag doesn't throw or log an error, not the resulting selection/window.
test("dragging on the minimap canvas produces no console errors", async ({
	page,
}) => {
	const consoleErrors: string[] = [];
	page.on("console", (msg) => {
		if (msg.type() === "error") {
			consoleErrors.push(msg.text());
		}
	});

	await openMinimapDetail(page);

	const miniCanvas = page.locator(".minimap-canvas");
	const box = await miniCanvas.boundingBox();
	if (!box) {
		throw new Error("minimap canvas has no bounding box");
	}

	const startX = box.x + box.width * 0.2;
	const endX = box.x + box.width * 0.6;
	const y = box.y + box.height / 2;

	await page.mouse.move(startX, y);
	await page.mouse.down();
	await page.mouse.move(endX, y);
	await page.mouse.up();

	await expect(miniCanvas).toBeVisible();
	expect(consoleErrors).toHaveLength(0);
});

// trace-5k is a real ~5000-exchange capture spanning ~89s (see
// findings.spec.ts). Selecting the minimap's full width puts every one of
// those exchanges in the detail window — far more than the ~2726 rows that
// fit under drawDetail's MAX_H canvas-height cap (minimapDraw.ts:256-261).
// Rows beyond that cap must not silently disappear off-canvas: this asserts
// a fix-agnostic contract rather than a specific rendering approach — every
// exchange in the window is reachable by scrolling, OR the UI says some
// were dropped. Sidebar.vue already has a warning for the (unrelated)
// file-truncation case ("Warning: trace was truncated") — reuse that
// wording convention as the detector for "the app told the user".
test("a very large selected window shows every exchange or warns some are hidden", async ({
	page,
}) => {
	await openMinimapDetail(page, TRACE_5K_DATA_PATH);

	const miniCanvas = page.locator(".minimap-canvas");
	const box = await miniCanvas.boundingBox();
	if (!box) {
		throw new Error("minimap canvas has no bounding box");
	}
	const y = box.y + box.height / 2;
	const leftX = box.x + 0.5;
	const rightX = box.x + box.width - 0.5;

	// Autofocus (on mount) may have placed the initial selection anywhere.
	// Click the right edge first so the selection is unambiguously away from
	// column 0, then drag left-to-right is guaranteed to be a fresh "create"
	// drag spanning the full width, not a pan/edge-resize of that window.
	await page.mouse.click(rightX, y);
	await page.mouse.move(leftX, y);
	await page.mouse.down();
	await page.mouse.move(rightX, y);
	await page.mouse.up();

	const { scrollHeight } = await page.evaluate(() => {
		const container = document.querySelector(".detail-section") as HTMLElement;
		return { scrollHeight: container.scrollHeight };
	});

	// How many rows the user can actually scroll to, using drawDetail's own
	// row-pitch formula (MT header + RH+RG pitch per row).
	const maxReachableRows = Math.floor((scrollHeight - MT) / (RH + RG));
	const KNOWN_EXCHANGE_COUNT = 5000;
	const allExchangesReachable = maxReachableRows >= KNOWN_EXCHANGE_COUNT;

	const warningVisible = await page
		.getByText(/truncat|clipped|hidden|not (all )?shown/i)
		.first()
		.isVisible()
		.catch(() => false);

	expect(allExchangesReachable || warningVisible).toBe(true);
});
