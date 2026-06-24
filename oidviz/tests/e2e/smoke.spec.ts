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

test("sidebar: aside landmark present, all four view buttons visible", async ({
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

	// All four view buttons visible
	await expect(page.getByRole("button", { name: "Findings" })).toBeVisible();
	await expect(
		page.getByRole("button", { name: "Incident Stack" }),
	).toBeVisible();
	await expect(
		page.getByRole("button", { name: "Minimap + Detail" }),
	).toBeVisible();
	await expect(page.getByRole("button", { name: "OID Tree" })).toBeVisible();
});
