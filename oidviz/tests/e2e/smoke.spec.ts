import { test, expect } from "@playwright/test";
import { fileURLToPath } from "node:url";
import path from "node:path";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const FIXTURE_PATH = path.resolve(
	__dirname,
	"../../../traceformat/examples/trace-5k.oidtrace.jsonl.gz",
);

test("landing page: drop zone visible, no console errors", async ({ page }) => {
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

test("file upload: transitions to viewer phase", async ({ page }) => {
	await page.goto("/");

	const fileInput = page.locator('input[type="file"]');
	await fileInput.setInputFiles(FIXTURE_PATH);

	await expect(page.locator('[data-phase="viewer"]')).toBeVisible({
		timeout: 10000,
	});
});

test("findings view: shows rows after file upload", async ({ page }) => {
	await page.goto("/");

	const fileInput = page.locator('input[type="file"]');
	await fileInput.setInputFiles(FIXTURE_PATH);

	await expect(page.locator('[data-phase="viewer"]')).toBeVisible({
		timeout: 10000,
	});

	// Findings view is the default active view; at least one exchange row should be visible
	await expect(page.locator(".exchange-row").first()).toBeVisible({
		timeout: 5000,
	});
});

test("sidebar: aside landmark present, all three view buttons visible", async ({
	page,
}) => {
	await page.goto("/");

	// Upload a file so we're in viewer phase where sidebar is rendered
	const fileInput = page.locator('input[type="file"]');
	await fileInput.setInputFiles(FIXTURE_PATH);
	await expect(page.locator('[data-phase="viewer"]')).toBeVisible({
		timeout: 10000,
	});

	// Aside landmark present
	const sidebar = page.getByRole("complementary", { name: "Controls" });
	await expect(sidebar).toBeVisible();

	// All three view buttons visible
	await expect(page.getByRole("button", { name: "Findings" })).toBeVisible();
	await expect(
		page.getByRole("button", { name: "Minimap + Detail" }),
	).toBeVisible();
	await expect(page.getByRole("button", { name: "OID Tree" })).toBeVisible();
});

test("minimap view: both canvases have non-zero clientWidth", async ({
	page,
}) => {
	await page.goto("/");

	const fileInput = page.locator('input[type="file"]');
	await fileInput.setInputFiles(FIXTURE_PATH);

	await expect(page.locator('[data-phase="viewer"]')).toBeVisible({
		timeout: 10000,
	});

	// Switch to Minimap + Detail view
	await page.getByRole("button", { name: "Minimap + Detail" }).click();

	// Both canvas elements should have non-zero clientWidth
	const canvases = page.locator(".minimap-detail canvas");
	await expect(canvases).toHaveCount(2, { timeout: 3000 });

	const widths = await canvases.evaluateAll((els) =>
		els.map((el) => (el as HTMLElement).clientWidth),
	);
	for (const w of widths) {
		expect(w).toBeGreaterThan(0);
	}
});

test("oid tree: at least one trie row visible", async ({ page }) => {
	await page.goto("/");

	const fileInput = page.locator('input[type="file"]');
	await fileInput.setInputFiles(FIXTURE_PATH);

	await expect(page.locator('[data-phase="viewer"]')).toBeVisible({
		timeout: 10000,
	});

	// Switch to OID Tree view
	await page.getByRole("button", { name: "OID Tree" }).click();

	// At least one trie row should be visible
	await expect(page.locator('[data-trie-row]').first()).toBeVisible({
		timeout: 5000,
	});
});

