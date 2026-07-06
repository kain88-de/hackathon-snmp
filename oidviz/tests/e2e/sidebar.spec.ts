import { test, expect } from "@playwright/test";
import { fileURLToPath } from "node:url";
import path from "node:path";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const CANONICAL_DATA_PATH = path.resolve(
	__dirname,
	"./test-data/canonical.oidtrace.jsonl.gz",
);

const NO_SUMMARY_DATA_PATH = path.resolve(
	__dirname,
	"./test-data/no-summary.oidtrace.jsonl.gz",
);

test("aside landmark + 3 view buttons", async ({ page }) => {
	await page.goto("/");

	const fileInput = page.locator('input[type="file"]');
	await fileInput.setInputFiles(CANONICAL_DATA_PATH);

	await expect(page.locator('[data-phase="viewer"]')).toBeVisible({
		timeout: 10000,
	});

	// Verify complementary landmark (sidebar) with name "Controls"
	const sidebar = page.getByRole("complementary", { name: "Controls" });
	await expect(sidebar).toBeVisible();

	// Verify 3 view buttons
	const findingsButton = page.getByRole("button", { name: "Findings" });
	await expect(findingsButton).toBeVisible();

	const minimapButton = page.getByRole("button", { name: "Minimap + Detail" });
	await expect(minimapButton).toBeVisible();

	const oidTreeButton = page.getByRole("button", { name: "OID Tree" });
	await expect(oidTreeButton).toBeVisible();
});

test("Device section fields", async ({ page }) => {
	await page.goto("/");

	const fileInput = page.locator('input[type="file"]');
	await fileInput.setInputFiles(CANONICAL_DATA_PATH);

	await expect(page.locator('[data-phase="viewer"]')).toBeVisible({
		timeout: 10000,
	});

	// Verify sysDescr = "Test Device R1" (first line only)
	const sysDescrValue = page.locator(
		'.sidebar-section:has(.sidebar-section-title:has-text("Device")) .info-row:has(.info-key:has-text("sysDescr")) .info-val',
	);
	await expect(sysDescrValue).toHaveText("Test Device R1");

	// Verify sysObjectID = "1.3.6.1.4.1.9999.1"
	const sysObjectIDValue = page.locator(
		'.sidebar-section:has(.sidebar-section-title:has-text("Device")) .info-row:has(.info-key:has-text("sysObjectID")) .info-val',
	);
	await expect(sysObjectIDValue).toHaveText("1.3.6.1.4.1.9999.1");

	// Verify sysUpTime = "12345"
	const sysUpTimeValue = page.locator(
		'.sidebar-section:has(.sidebar-section-title:has-text("Device")) .info-row:has(.info-key:has-text("sysUpTime")) .info-val',
	);
	await expect(sysUpTimeValue).toHaveText("12345");
});

test("Device section hidden", async ({ page }) => {
	await page.goto("/");

	const fileInput = page.locator('input[type="file"]');
	await fileInput.setInputFiles(NO_SUMMARY_DATA_PATH);

	await expect(page.locator('[data-phase="viewer"]')).toBeVisible({
		timeout: 10000,
	});

	// Verify Device section title doesn't exist (since no system_info record)
	const deviceSectionTitle = page.locator(
		'.sidebar-section:has(.sidebar-section-title:has-text("Device"))',
	);
	await expect(deviceSectionTitle).not.toBeVisible();
});

test("Walk info fields", async ({ page }) => {
	await page.goto("/");

	const fileInput = page.locator('input[type="file"]');
	await fileInput.setInputFiles(CANONICAL_DATA_PATH);

	await expect(page.locator('[data-phase="viewer"]')).toBeVisible({
		timeout: 10000,
	});

	// Verify Label = "test-walk"
	const labelValue = page.locator(
		'.sidebar-section:has(.sidebar-section-title:has-text("Walk info")) .info-row:has(.info-key:has-text("Label")) .info-val',
	);
	await expect(labelValue).toHaveText("test-walk");

	// Verify SNMP = "v2c"
	const snmpValue = page.locator(
		'.sidebar-section:has(.sidebar-section-title:has-text("Walk info")) .info-row:has(.info-key:has-text("SNMP")) .info-val',
	);
	await expect(snmpValue).toHaveText("v2c");

	// Verify Start OID = "1.3.6.1"
	const startOIDValue = page.locator(
		'.sidebar-section:has(.sidebar-section-title:has-text("Walk info")) .info-row:has(.info-key:has-text("Start OID")) .info-val',
	);
	await expect(startOIDValue).toHaveText("1.3.6.1");

	// Verify Exchanges = "5"
	const exchangesValue = page.locator(
		'.sidebar-section:has(.sidebar-section-title:has-text("Walk info")) .info-row:has(.info-key:has-text("Exchanges")) .info-val',
	);
	await expect(exchangesValue).toHaveText("5");

	// Verify End reason = "completed"
	const endReasonValue = page.locator(
		'.sidebar-section:has(.sidebar-section-title:has-text("Walk info")) .info-row:has(.info-key:has-text("End reason")) .info-val',
	);
	await expect(endReasonValue).toHaveText("completed");
});

test("Walk info violations styling", async ({ page }) => {
	await page.goto("/");

	const fileInput = page.locator('input[type="file"]');
	await fileInput.setInputFiles(CANONICAL_DATA_PATH);

	await expect(page.locator('[data-phase="viewer"]')).toBeVisible({
		timeout: 10000,
	});

	// Verify Violations = "1"
	const violationsValue = page.locator(
		'.sidebar-section:has(.sidebar-section-title:has-text("Walk info")) .info-row:has(.info-key:has-text("Violations")) .info-val',
	);
	await expect(violationsValue).toHaveText("1");

	// Verify it has class "info-val--err"
	await expect(violationsValue).toHaveClass(/info-val--err/);
});

test("Walk config fields", async ({ page }) => {
	await page.goto("/");

	const fileInput = page.locator('input[type="file"]');
	await fileInput.setInputFiles(CANONICAL_DATA_PATH);

	await expect(page.locator('[data-phase="viewer"]')).toBeVisible({
		timeout: 10000,
	});

	// Verify Bulk size = "10"
	const bulkSizeValue = page.locator(
		'.sidebar-section:has(.sidebar-section-title:has-text("Walk config")) .info-row:has(.info-key:has-text("Bulk size")) .info-val',
	);
	await expect(bulkSizeValue).toHaveText("10");

	// Verify Timeout = "2s"
	const timeoutValue = page.locator(
		'.sidebar-section:has(.sidebar-section-title:has-text("Walk config")) .info-row:has(.info-key:has-text("Timeout")) .info-val',
	);
	await expect(timeoutValue).toHaveText("2s");

	// Verify Retries = "1"
	const retriesValue = page.locator(
		'.sidebar-section:has(.sidebar-section-title:has-text("Walk config")) .info-row:has(.info-key:has-text("Retries")) .info-val',
	);
	await expect(retriesValue).toHaveText("1");

	// Verify Budget = "30s"
	const budgetValue = page.locator(
		'.sidebar-section:has(.sidebar-section-title:has-text("Walk config")) .info-row:has(.info-key:has-text("Budget")) .info-val',
	);
	await expect(budgetValue).toHaveText("30s");

	// Verify Resume = "1.3.6.1.2.1.4.20"
	const resumeValue = page.locator(
		'.sidebar-section:has(.sidebar-section-title:has-text("Walk config")) .info-row:has(.info-key:has-text("Resume")) .info-val',
	);
	await expect(resumeValue).toHaveText("1.3.6.1.2.1.4.20");
});
