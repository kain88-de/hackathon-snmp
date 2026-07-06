import { test, expect } from "@playwright/test";
import { fileURLToPath } from "node:url";
import path from "node:path";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const CANONICAL_DATA_PATH = path.resolve(
	__dirname,
	"./test-data/canonical.oidtrace.jsonl.gz",
);

async function loadCanonical(page: import("@playwright/test").Page) {
	await page.goto("/");

	const fileInput = page.locator('input[type="file"]');
	await fileInput.setInputFiles(CANONICAL_DATA_PATH);

	await expect(page.locator('[data-phase="viewer"]')).toBeVisible({
		timeout: 10000,
	});
}

test("Performance = Slow → 1 row, seq 2", async ({ page }) => {
	await loadCanonical(page);

	await page.locator('input[name="perf"][value="slow"]').check();

	const rows = page.locator(".exchange-row");
	await expect(rows).toHaveCount(1);
	await expect(rows.first()).toHaveAttribute("data-seq", "2");
});

test("Performance = Timed out → 1 row, seq 3", async ({ page }) => {
	await loadCanonical(page);

	await page.locator('input[name="perf"][value="timeout"]').check();

	const rows = page.locator(".exchange-row");
	await expect(rows).toHaveCount(1);
	await expect(rows.first()).toHaveAttribute("data-seq", "3");
});

test("Correctness = Violations only → 1 row, seq 4", async ({ page }) => {
	await loadCanonical(page);

	await page.locator('input[name="corr"][value="violations"]').check();

	const rows = page.locator(".exchange-row");
	await expect(rows).toHaveCount(1);
	await expect(rows.first()).toHaveAttribute("data-seq", "4");
});

test("Retries only checked → 1 row, seq 5", async ({ page }) => {
	await loadCanonical(page);

	await page.locator(".sidebar-checkbox-label input[type='checkbox']").check();

	const rows = page.locator(".exchange-row");
	await expect(rows).toHaveCount(1);
	await expect(rows.first()).toHaveAttribute("data-seq", "5");
});

test("Slow AND Violations only together → 0 rows", async ({ page }) => {
	await loadCanonical(page);

	await page.locator('input[name="perf"][value="slow"]').check();
	await page.locator('input[name="corr"][value="violations"]').check();

	await expect(page.locator(".exchange-row")).toHaveCount(0);
});

test("Slow threshold set to 0.01s → Slow (4) section, no Fast section", async ({
	page,
}) => {
	await loadCanonical(page);

	const thresholdInput = page.locator("input.sidebar-number-input");
	await thresholdInput.fill("0.01");
	await thresholdInput.blur();

	await expect(
		page.locator('.section-header[data-label="Slow (4)"]'),
	).toBeVisible();
	await expect(page.locator('.section-header[data-label^="Fast"]')).toHaveCount(
		0,
	);
});
