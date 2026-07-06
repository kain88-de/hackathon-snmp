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

// Any trace that reaches the viewer phase must render a "Controls" sidebar
// landmark with the three view-switch buttons — not fixture-dependent.
test("aside landmark + 3 view buttons", async ({ page }) => {
	await page.goto("/");

	const fileInput = page.locator('input[type="file"]');
	await fileInput.setInputFiles(CANONICAL_DATA_PATH);

	await expect(page.locator('[data-phase="viewer"]')).toBeVisible({
		timeout: 10000,
	});

	const sidebar = page.getByRole("complementary", { name: "Controls" });
	await expect(sidebar).toBeVisible();

	const findingsButton = page.getByRole("button", { name: "Findings" });
	await expect(findingsButton).toBeVisible();

	const minimapButton = page.getByRole("button", { name: "Minimap + Detail" });
	await expect(minimapButton).toBeVisible();

	const oidTreeButton = page.getByRole("button", { name: "OID Tree" });
	await expect(oidTreeButton).toBeVisible();
});

// canonical's system_info: sysDescr "Test Device R1\nBuild 42" (the embedded
// newline must render as first-line-only), sysObjectID 1.3.6.1.4.1.9999.1,
// sysUpTime 12345.
test("Device section shows the system_info values, sysDescr truncated to its first line", async ({
	page,
}) => {
	await page.goto("/");

	const fileInput = page.locator('input[type="file"]');
	await fileInput.setInputFiles(CANONICAL_DATA_PATH);

	await expect(page.locator('[data-phase="viewer"]')).toBeVisible({
		timeout: 10000,
	});

	const sysDescrValue = page.locator(
		'.sidebar-section:has(.sidebar-section-title:has-text("Device")) .info-row:has(.info-key:has-text("sysDescr")) .info-val',
	);
	await expect(sysDescrValue).toHaveText("Test Device R1");

	const sysObjectIDValue = page.locator(
		'.sidebar-section:has(.sidebar-section-title:has-text("Device")) .info-row:has(.info-key:has-text("sysObjectID")) .info-val',
	);
	await expect(sysObjectIDValue).toHaveText("1.3.6.1.4.1.9999.1");

	const sysUpTimeValue = page.locator(
		'.sidebar-section:has(.sidebar-section-title:has-text("Device")) .info-row:has(.info-key:has-text("sysUpTime")) .info-val',
	);
	await expect(sysUpTimeValue).toHaveText("12345");
});

// no-summary has no system_info record, so deviceInfo must be null and the
// whole Device section — including its title — must not render at all.
test("Device section is absent when the trace has no system_info", async ({
	page,
}) => {
	await page.goto("/");

	const fileInput = page.locator('input[type="file"]');
	await fileInput.setInputFiles(NO_SUMMARY_DATA_PATH);

	await expect(page.locator('[data-phase="viewer"]')).toBeVisible({
		timeout: 10000,
	});

	const deviceSectionTitle = page.locator(
		'.sidebar-section:has(.sidebar-section-title:has-text("Device"))',
	);
	await expect(deviceSectionTitle).not.toBeVisible();
});

// canonical's header/summary: label "test-walk", snmp v2c, start OID
// 1.3.6.1, 5 exchanges, end_reason "completed".
test("Walk info section shows the header and summary fields", async ({
	page,
}) => {
	await page.goto("/");

	const fileInput = page.locator('input[type="file"]');
	await fileInput.setInputFiles(CANONICAL_DATA_PATH);

	await expect(page.locator('[data-phase="viewer"]')).toBeVisible({
		timeout: 10000,
	});

	const labelValue = page.locator(
		'.sidebar-section:has(.sidebar-section-title:has-text("Walk info")) .info-row:has(.info-key:has-text("Label")) .info-val',
	);
	await expect(labelValue).toHaveText("test-walk");

	const snmpValue = page.locator(
		'.sidebar-section:has(.sidebar-section-title:has-text("Walk info")) .info-row:has(.info-key:has-text("SNMP")) .info-val',
	);
	await expect(snmpValue).toHaveText("v2c");

	const startOIDValue = page.locator(
		'.sidebar-section:has(.sidebar-section-title:has-text("Walk info")) .info-row:has(.info-key:has-text("Start OID")) .info-val',
	);
	await expect(startOIDValue).toHaveText("1.3.6.1");

	const exchangesValue = page.locator(
		'.sidebar-section:has(.sidebar-section-title:has-text("Walk info")) .info-row:has(.info-key:has-text("Exchanges")) .info-val',
	);
	await expect(exchangesValue).toHaveText("5");

	const endReasonValue = page.locator(
		'.sidebar-section:has(.sidebar-section-title:has-text("Walk info")) .info-row:has(.info-key:has-text("End reason")) .info-val',
	);
	await expect(endReasonValue).toHaveText("completed");
});

// canonical's summary has 1 violation total ("oid-not-increasing" × 1); a
// non-zero violation count must render in the "err" style, not "ok".
test("a non-zero violation count renders in the error style", async ({
	page,
}) => {
	await page.goto("/");

	const fileInput = page.locator('input[type="file"]');
	await fileInput.setInputFiles(CANONICAL_DATA_PATH);

	await expect(page.locator('[data-phase="viewer"]')).toBeVisible({
		timeout: 10000,
	});

	const violationsValue = page.locator(
		'.sidebar-section:has(.sidebar-section-title:has-text("Walk info")) .info-row:has(.info-key:has-text("Violations")) .info-val',
	);
	await expect(violationsValue).toHaveText("1");
	await expect(violationsValue).toHaveClass(/info-val--err/);
});

// canonical's header.settings: bulk_size 10, timeout_s 2, retries 1,
// time_budget_s 30, resume_from 1.3.6.1.2.1.4.20.
test("Walk config section shows the header's settings fields", async ({
	page,
}) => {
	await page.goto("/");

	const fileInput = page.locator('input[type="file"]');
	await fileInput.setInputFiles(CANONICAL_DATA_PATH);

	await expect(page.locator('[data-phase="viewer"]')).toBeVisible({
		timeout: 10000,
	});

	const bulkSizeValue = page.locator(
		'.sidebar-section:has(.sidebar-section-title:has-text("Walk config")) .info-row:has(.info-key:has-text("Bulk size")) .info-val',
	);
	await expect(bulkSizeValue).toHaveText("10");

	const timeoutValue = page.locator(
		'.sidebar-section:has(.sidebar-section-title:has-text("Walk config")) .info-row:has(.info-key:has-text("Timeout")) .info-val',
	);
	await expect(timeoutValue).toHaveText("2s");

	const retriesValue = page.locator(
		'.sidebar-section:has(.sidebar-section-title:has-text("Walk config")) .info-row:has(.info-key:has-text("Retries")) .info-val',
	);
	await expect(retriesValue).toHaveText("1");

	const budgetValue = page.locator(
		'.sidebar-section:has(.sidebar-section-title:has-text("Walk config")) .info-row:has(.info-key:has-text("Budget")) .info-val',
	);
	await expect(budgetValue).toHaveText("30s");

	const resumeValue = page.locator(
		'.sidebar-section:has(.sidebar-section-title:has-text("Walk config")) .info-row:has(.info-key:has-text("Resume")) .info-val',
	);
	await expect(resumeValue).toHaveText("1.3.6.1.2.1.4.20");
});
