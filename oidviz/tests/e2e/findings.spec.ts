import { test, expect } from "@playwright/test";
import { fileURLToPath } from "node:url";
import path from "node:path";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const CANONICAL_DATA_PATH = path.resolve(
	__dirname,
	"./test-data/canonical.oidtrace.jsonl.gz",
);

const TRACE_5K_DATA_PATH = path.resolve(
	__dirname,
	"../../../traceformat/examples/trace-5k.oidtrace.jsonl.gz",
);

async function loadCanonical(page: import("@playwright/test").Page) {
	await page.goto("/");

	const fileInput = page.locator('input[type="file"]');
	await fileInput.setInputFiles(CANONICAL_DATA_PATH);

	await expect(page.locator('[data-phase="viewer"]')).toBeVisible({
		timeout: 10000,
	});
}

test("Findings is the default view", async ({ page }) => {
	await loadCanonical(page);

	const findingsContainer = page.locator(".findings-container");
	await expect(findingsContainer).toBeVisible();
});

test("sections partition by outcome", async ({ page }) => {
	await loadCanonical(page);

	// Check that all three section headers are visible with correct counts
	await expect(
		page.locator('.section-header[data-label="Slow (1)"]'),
	).toBeVisible();
	await expect(
		page.locator('.section-header[data-label="Timed out (1)"]'),
	).toBeVisible();
	await expect(
		page.locator('.section-header[data-label="Fast (3)"]'),
	).toBeVisible();
});

test("sections expanded by default", async ({ page }) => {
	await loadCanonical(page);

	// All three section headers should have aria-expanded="true"
	const sectionHeaders = page.locator(".section-header");
	await expect(sectionHeaders).toHaveCount(3);

	for (let i = 0; i < 3; i++) {
		await expect(sectionHeaders.nth(i)).toHaveAttribute(
			"aria-expanded",
			"true",
		);
	}
});

test("collapsing a header hides its rows", async ({ page }) => {
	await loadCanonical(page);

	// Get the Slow section header and click it
	const slowHeader = page.locator('.section-header[data-label="Slow (1)"]');
	await slowHeader.click();

	// After clicking, aria-expanded should be false
	await expect(slowHeader).toHaveAttribute("aria-expanded", "false");

	// The row with seq 2 should not be visible
	const seq2Row = page.locator('.exchange-row[data-seq="2"]');
	await expect(seq2Row).not.toBeVisible();
});

test("violation badge", async ({ page }) => {
	await loadCanonical(page);

	// Find the row with seq 4 and check its violation badge
	const seq4Row = page.locator('.exchange-row[data-seq="4"]');
	const violationBadge = seq4Row.locator(".badge-violation");

	await expect(violationBadge).toHaveText("1 viol");
});

test("retry badge", async ({ page }) => {
	await loadCanonical(page);

	// Find the row with seq 5 and check its retry badge
	const seq5Row = page.locator('.exchange-row[data-seq="5"]');
	const retryBadge = seq5Row.locator(".badge-retry");

	await expect(retryBadge).toHaveText("×2");
});

test("large real trace loads cleanly", async ({ page }) => {
	const consoleErrors: string[] = [];
	page.on("console", (msg) => {
		if (msg.type() === "error") {
			consoleErrors.push(msg.text());
		}
	});

	await page.goto("/");

	const fileInput = page.locator('input[type="file"]');
	await fileInput.setInputFiles(TRACE_5K_DATA_PATH);

	await expect(page.locator('[data-phase="viewer"]')).toBeVisible({
		timeout: 10000,
	});

	// Check that at least 1 exchange row is visible
	const exchangeRows = page.locator(".exchange-row");
	const count = await exchangeRows.count();
	expect(count).toBeGreaterThanOrEqual(1);

	// Check no console errors
	expect(consoleErrors).toHaveLength(0);
});
