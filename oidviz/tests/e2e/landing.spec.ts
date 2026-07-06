import { test, expect } from "@playwright/test";
import { fileURLToPath } from "node:url";
import path from "node:path";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const CANONICAL_DATA_PATH = path.resolve(
	__dirname,
	"./test-data/canonical.oidtrace.jsonl.gz",
);

const NOT_GZIP_DATA_PATH = path.resolve(
	__dirname,
	"./test-data/not-gzip.oidtrace.jsonl.gz",
);

const UNKNOWN_RECORD_TYPE_DATA_PATH = path.resolve(
	__dirname,
	"./test-data/unknown-record-type.oidtrace.jsonl.gz",
);

const TRUNCATED_DATA_PATH = path.resolve(
	__dirname,
	"./test-data/truncated.oidtrace.jsonl.gz",
);

const NO_SUMMARY_DATA_PATH = path.resolve(
	__dirname,
	"./test-data/no-summary.oidtrace.jsonl.gz",
);

// Landing screen (no file loaded yet) must expose the upload drop zone and
// load without console errors.
test("drop zone visible, no console errors", async ({ page }) => {
	const consoleErrors: string[] = [];
	page.on("console", (msg) => {
		if (msg.type() === "error") {
			consoleErrors.push(msg.text());
		}
	});

	await page.goto("/");

	const dropZone = page.getByRole("region", {
		name: "Drop zone for OID trace files",
	});
	await expect(dropZone).toBeVisible();

	expect(consoleErrors).toHaveLength(0);
});

// canonical is a complete, well-formed trace; uploading it must reach the
// viewer phase.
test("a well-formed trace reaches the viewer phase", async ({ page }) => {
	await page.goto("/");

	const fileInput = page.locator('input[type="file"]');
	await fileInput.setInputFiles(CANONICAL_DATA_PATH);

	await expect(page.locator('[data-phase="viewer"]')).toBeVisible({
		timeout: 10000,
	});
});

// not-gzip is plain text saved with a .gz extension, so decompression fails.
// The app must show the error phase and an accessible alert, not crash
// silently or hang.
test("a file that isn't actually gzip shows an error", async ({ page }) => {
	await page.goto("/");

	const fileInput = page.locator('input[type="file"]');
	await fileInput.setInputFiles(NOT_GZIP_DATA_PATH);

	await expect(page.locator('[data-phase="error"]')).toBeVisible({
		timeout: 10000,
	});

	await expect(page.getByRole("alert")).toBeVisible();
});

// unknown-record-type has a record with an unrecognized "type" between two
// valid exchanges. Per the format spec (§3, "unknown fields"), readers must
// ignore it and keep parsing, so the exchange count must still be 2.
test("an unrecognized record type is skipped without breaking the parse", async ({
	page,
}) => {
	await page.goto("/");

	const fileInput = page.locator('input[type="file"]');
	await fileInput.setInputFiles(UNKNOWN_RECORD_TYPE_DATA_PATH);

	await expect(page.locator('[data-phase="viewer"]')).toBeVisible({
		timeout: 10000,
	});

	// Verify Walk info "Exchanges" = 2
	const exchangesValue = page.locator(
		'.sidebar-section:has(.sidebar-section-title:has-text("Walk info")) .info-row:has(.info-key:has-text("Exchanges")) .info-val',
	);
	await expect(exchangesValue).toHaveText("2");
});

// truncated has a complete header + exchange 1, then exchange 2 cut off
// mid-record with no trailing newline (simulates a crash mid-write). The
// truncated-file fix must still reach the viewer, with a warning, rather
// than the error page.
test("truncated file → viewer phase with truncation warning", async ({
	page,
}) => {
	await page.goto("/");

	const fileInput = page.locator('input[type="file"]');
	await fileInput.setInputFiles(TRUNCATED_DATA_PATH);

	await expect(page.locator('[data-phase="viewer"]')).toBeVisible({
		timeout: 10000,
	});

	await expect(page.getByText("Warning: trace was truncated")).toBeVisible();
});

// no-summary has 2 exchanges and no summary record: exchange 1 has 1
// violation ("oid-not-increasing"), exchange 2 has none, and their response
// OIDs differ so there are 2 unique OIDs. The missing-summary-derivation fix
// must compute Violations/OIDs seen from the exchanges instead of falling
// back to 0/"—".
test("missing summary → totals derived from exchanges", async ({ page }) => {
	await page.goto("/");

	const fileInput = page.locator('input[type="file"]');
	await fileInput.setInputFiles(NO_SUMMARY_DATA_PATH);

	await expect(page.locator('[data-phase="viewer"]')).toBeVisible({
		timeout: 10000,
	});

	const violationsValue = page.locator(
		'.sidebar-section:has(.sidebar-section-title:has-text("Walk info")) .info-row:has(.info-key:has-text("Violations")) .info-val',
	);
	await expect(violationsValue).toHaveText("1");

	const oidsSeenValue = page.locator(
		'.sidebar-section:has(.sidebar-section-title:has-text("Walk info")) .info-row:has(.info-key:has-text("OIDs seen")) .info-val',
	);
	await expect(oidsSeenValue).toHaveText("2");
});
