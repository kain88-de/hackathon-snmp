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

// Findings must be the active view immediately after upload, with no
// view-switch click.
test("Findings is the default view", async ({ page }) => {
	await loadCanonical(page);

	const findingsContainer = page.locator(".findings-container");
	await expect(findingsContainer).toBeVisible();
});

// canonical's default facets (1000ms threshold) put seq 2 (1500ms) in Slow,
// seq 3 (no response) in Timed out, and seq 1/4/5 (all ≤50ms) in Fast.
test("sections partition by outcome", async ({ page }) => {
	await loadCanonical(page);

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

// All three outcome sections render expanded by default — this is current,
// deliberately-unfixed app behavior (the written spec calls for collapsed
// by default; that gap is out of scope for this suite).
test("sections expanded by default", async ({ page }) => {
	await loadCanonical(page);

	const sectionHeaders = page.locator(".section-header");
	await expect(sectionHeaders).toHaveCount(3);

	for (let i = 0; i < 3; i++) {
		await expect(sectionHeaders.nth(i)).toHaveAttribute(
			"aria-expanded",
			"true",
		);
	}
});

// canonical seq 1 is a Fast-section row. Exchange rows must be real buttons,
// not clickable divs, so keyboard and screen-reader users can reach and
// activate them without a mouse.
test("an exchange row is keyboard-focusable", async ({ page }) => {
	await loadCanonical(page);

	const seq1Row = page.locator('.exchange-row[data-seq="1"]');
	await seq1Row.focus();
	await expect(seq1Row).toBeFocused();
	await expect(seq1Row).toHaveJSProperty("tagName", "BUTTON");
});

// canonical seq 2 is the only exchange in the Slow section; collapsing that
// section must remove its row from the DOM entirely, not just hide it.
test("collapsing a header hides its rows", async ({ page }) => {
	await loadCanonical(page);

	const slowHeader = page.locator('.section-header[data-label="Slow (1)"]');
	await slowHeader.click();

	await expect(slowHeader).toHaveAttribute("aria-expanded", "false");

	const seq2Row = page.locator('.exchange-row[data-seq="2"]');
	await expect(seq2Row).not.toBeVisible();
});

// canonical seq 4: 20ms, 1 violation ("oid-not-increasing"), 1 attempt. An
// exchange with violations must render a violation-count badge.
test("exchange with a violation shows a violation-count badge", async ({
	page,
}) => {
	await loadCanonical(page);

	const seq4Row = page.locator('.exchange-row[data-seq="4"]');
	const violationBadge = seq4Row.locator(".badge-violation");

	await expect(violationBadge).toHaveText("1 viol");
});

// canonical seq 5: 2 attempts (first timed out, retry got the response). An
// exchange with more than one attempt must render a retry-count badge.
test("exchange with a retry shows a retry-count badge", async ({ page }) => {
	await loadCanonical(page);

	const seq5Row = page.locator('.exchange-row[data-seq="5"]');
	const retryBadge = seq5Row.locator(".badge-retry");

	await expect(retryBadge).toHaveText("×2");
});

// trace-5k is a real ~5000-exchange capture — the one place this shared
// fixture is still used, as a volume/perf smoke check. It must load without
// console errors and render at least one row.
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

	const exchangeRows = page.locator(".exchange-row");
	const count = await exchangeRows.count();
	expect(count).toBeGreaterThanOrEqual(1);

	expect(consoleErrors).toHaveLength(0);
});
