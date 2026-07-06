import { test, expect } from "@playwright/test";
import { fileURLToPath } from "node:url";
import path from "node:path";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const CANONICAL_DATA_PATH = path.resolve(
	__dirname,
	"./test-data/canonical.oidtrace.jsonl.gz",
);

async function openOidTree(page: import("@playwright/test").Page) {
	await page.goto("/");

	const fileInput = page.locator('input[type="file"]');
	await fileInput.setInputFiles(CANONICAL_DATA_PATH);

	await expect(page.locator('[data-phase="viewer"]')).toBeVisible({
		timeout: 10000,
	});

	await page.getByRole("button", { name: "OID Tree" }).click();
}

test("renders at least one row", async ({ page }) => {
	await openOidTree(page);

	await expect(page.locator("[data-trie-row]").first()).toBeVisible({
		timeout: 5000,
	});
});

test("toolbar count reads 5 exchanges", async ({ page }) => {
	await openOidTree(page);

	const count = page.locator(".oid-tree-count");
	await expect(count).toHaveText("5 exchanges");
});

test("anomalous nodes auto-expand", async ({ page }) => {
	await openOidTree(page);

	// At least one branch node should be expanded by default due to auto-expand
	const expandedNodes = page.locator('.trie-node[aria-expanded="true"]');
	await expect(expandedNodes.first()).toBeVisible({
		timeout: 5000,
	});
});

test("clicking a node toggles it", async ({ page }) => {
	await openOidTree(page);

	// Get the first trie node (branch node, not leaf)
	const firstNode = page.locator(".trie-node").first();

	// Get its initial expanded state
	const initialExpanded = await firstNode.getAttribute("aria-expanded");

	// Click to toggle
	await firstNode.click();

	// Get the new expanded state
	const newExpanded = await firstNode.getAttribute("aria-expanded");

	// They should be different
	expect(initialExpanded).not.toBe(newExpanded);
});

test("Collapse all button collapses all nodes", async ({ page }) => {
	await openOidTree(page);

	// Click the "Collapse all" button
	const collapseButton = page.locator(".oid-tree-collapse-btn");
	await collapseButton.click();

	// After collapsing, no trie-node should have aria-expanded="true"
	const expandedNodes = page.locator('.trie-node[aria-expanded="true"]');
	await expect(expandedNodes).toHaveCount(0, { timeout: 5000 });
});
