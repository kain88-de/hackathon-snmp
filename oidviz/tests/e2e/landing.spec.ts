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

test("valid file → viewer phase", async ({ page }) => {
	await page.goto("/");

	const fileInput = page.locator('input[type="file"]');
	await fileInput.setInputFiles(CANONICAL_DATA_PATH);

	await expect(page.locator('[data-phase="viewer"]')).toBeVisible({
		timeout: 10000,
	});
});

test("invalid gzip → error", async ({ page }) => {
	await page.goto("/");

	const fileInput = page.locator('input[type="file"]');
	await fileInput.setInputFiles(NOT_GZIP_DATA_PATH);

	await expect(page.locator('[data-phase="error"]')).toBeVisible({
		timeout: 10000,
	});

	await expect(page.getByRole("alert")).toBeVisible();
});

test("unknown record skipped", async ({ page }) => {
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
