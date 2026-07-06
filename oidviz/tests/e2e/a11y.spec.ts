import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const TEST_DATA_PATH = path.resolve(
	__dirname,
	"test-data/canonical.oidtrace.jsonl.gz",
);

test("a11y: landing page has no violations", async ({ page }) => {
	await page.goto("/");
	const results = await new AxeBuilder({ page }).analyze();
	expect(results.violations).toEqual([]);
});

test("a11y: viewer (findings) has no violations", async ({ page }) => {
	await page.goto("/");
	const fileInput = page.locator('input[type="file"]');
	await fileInput.setInputFiles(TEST_DATA_PATH);
	await expect(page.locator('[data-phase="viewer"]')).toBeVisible({
		timeout: 10000,
	});
	const results = await new AxeBuilder({ page }).analyze();
	expect(results.violations).toEqual([]);
});
