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

// canonical seq 2 (1500ms) is the only exchange slower than the default
// 1000ms threshold.
test("Performance=Slow filter shows only the exchange slower than the threshold", async ({
	page,
}) => {
	await loadCanonical(page);

	await page.locator('input[name="perf"][value="slow"]').check();

	const rows = page.locator(".exchange-row");
	await expect(rows).toHaveCount(1);
	await expect(rows.first()).toHaveAttribute("data-seq", "2");
});

// canonical seq 3 is the only exchange with no response at all (a timeout).
test("Performance=Timed-out filter shows only the exchange with no response", async ({
	page,
}) => {
	await loadCanonical(page);

	await page.locator('input[name="perf"][value="timeout"]').check();

	const rows = page.locator(".exchange-row");
	await expect(rows).toHaveCount(1);
	await expect(rows.first()).toHaveAttribute("data-seq", "3");
});

// canonical seq 4 is the only exchange with a violation
// ("oid-not-increasing").
test("Correctness=Violations-only filter shows only the exchange with a violation", async ({
	page,
}) => {
	await loadCanonical(page);

	await page.locator('input[name="corr"][value="violations"]').check();

	const rows = page.locator(".exchange-row");
	await expect(rows).toHaveCount(1);
	await expect(rows.first()).toHaveAttribute("data-seq", "4");
});

// canonical seq 5 is the only exchange with more than one attempt (its
// first attempt timed out, then a retry got the response).
test("Retries-only filter shows only the exchange that needed a retry", async ({
	page,
}) => {
	await loadCanonical(page);

	await page.locator(".sidebar-checkbox-label input[type='checkbox']").check();

	const rows = page.locator(".exchange-row");
	await expect(rows).toHaveCount(1);
	await expect(rows.first()).toHaveAttribute("data-seq", "5");
});

// canonical seq 2 is slow but has no violation, and seq 4 has a violation
// but isn't slow. No exchange satisfies both facets, so combining them must
// AND (0 rows) rather than OR (which would show both, 2 rows).
test("combining Slow and Violations-only filters ANDs them, not ORs them", async ({
	page,
}) => {
	await loadCanonical(page);

	await page.locator('input[name="perf"][value="slow"]').check();
	await page.locator('input[name="corr"][value="violations"]').check();

	await expect(page.locator(".exchange-row")).toHaveCount(0);
});

// Lowering the slow threshold to 10ms makes seq 1 (50ms), 2 (1500ms), 4
// (20ms) and 5 (50ms) all count as slow — only seq 3 (a timeout, no rtt) is
// excluded — so the Fast section must disappear entirely.
test("lowering the slow threshold reclassifies fast exchanges as slow", async ({
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
