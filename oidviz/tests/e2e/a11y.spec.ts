import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const FIXTURE_PATH = path.resolve(
	__dirname,
	"../../../traceformat/examples/trace-5k.oidtrace.jsonl.gz",
);

// Gate on critical violations only; serious/moderate (e.g. colour-contrast on
// status dim tokens) are tracked but not blocking — fix as part of a palette pass.
function criticalViolations(
	results: Awaited<ReturnType<AxeBuilder["analyze"]>>,
) {
	return results.violations.filter((v) => v.impact === "critical");
}

test("a11y: landing page has no critical violations", async ({ page }) => {
	await page.goto("/");
	const results = await new AxeBuilder({ page }).analyze();
	expect(criticalViolations(results)).toEqual([]);
});

test("a11y: viewer (findings) has no critical violations", async ({ page }) => {
	await page.goto("/");
	const fileInput = page.locator('input[type="file"]');
	await fileInput.setInputFiles(FIXTURE_PATH);
	await expect(page.locator('[data-phase="viewer"]')).toBeVisible({
		timeout: 10000,
	});
	const results = await new AxeBuilder({ page }).analyze();
	expect(criticalViolations(results)).toEqual([]);
});
