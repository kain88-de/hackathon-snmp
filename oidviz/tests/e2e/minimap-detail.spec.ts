import { test, expect } from "@playwright/test";
import { fileURLToPath } from "node:url";
import path from "node:path";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const CANONICAL_DATA_PATH = path.resolve(
	__dirname,
	"./test-data/canonical.oidtrace.jsonl.gz",
);

async function openMinimapDetail(page: import("@playwright/test").Page) {
	await page.goto("/");

	const fileInput = page.locator('input[type="file"]');
	await fileInput.setInputFiles(CANONICAL_DATA_PATH);

	await expect(page.locator('[data-phase="viewer"]')).toBeVisible({
		timeout: 10000,
	});

	await page.getByRole("button", { name: "Minimap + Detail" }).click();
}

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

test("minimap canvas is keyboard-focusable", async ({ page }) => {
	await openMinimapDetail(page);

	const miniCanvas = page.locator(".minimap-canvas");
	await miniCanvas.focus();
	await expect(miniCanvas).toBeFocused();
});

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
