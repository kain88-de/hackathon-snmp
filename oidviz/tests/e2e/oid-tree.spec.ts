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

// canonical has 5 exchanges, so building the tree must produce at least one
// row (branch or leaf).
test("renders at least one row", async ({ page }) => {
	await openOidTree(page);

	await expect(page.locator("[data-trie-row]").first()).toBeVisible({
		timeout: 5000,
	});
});

// canonical has exactly 5 exchanges; the toolbar count must reflect the
// current match count.
test("toolbar count reads 5 exchanges", async ({ page }) => {
	await openOidTree(page);

	const count = page.locator(".oid-tree-count");
	await expect(count).toHaveText("5 exchanges");
});

// autoExpand() expands any node whose child count is at or below the
// auto-expand threshold; with only 5 exchanges the tree is shallow, so at
// least one branch node must end up expanded without a click.
test("anomalous nodes auto-expand", async ({ page }) => {
	await openOidTree(page);

	const expandedNodes = page.locator('.trie-node[aria-expanded="true"]');
	await expect(expandedNodes.first()).toBeVisible({
		timeout: 5000,
	});
});

// Auto-expand state is data-dependent, so read the node's actual
// aria-expanded value first rather than assuming a starting state; a click
// must flip it either way.
test("clicking a node toggles it", async ({ page }) => {
	await openOidTree(page);

	const firstNode = page.locator(".trie-node").first();

	const initialExpanded = await firstNode.getAttribute("aria-expanded");
	await firstNode.click();
	const newExpanded = await firstNode.getAttribute("aria-expanded");

	expect(initialExpanded).not.toBe(newExpanded);
});

// Regardless of how many nodes auto-expand initially, "Collapse all" must
// leave zero nodes expanded.
test("Collapse all button collapses all nodes", async ({ page }) => {
	await openOidTree(page);

	const collapseButton = page.locator(".oid-tree-collapse-btn");
	await collapseButton.click();

	const expandedNodes = page.locator('.trie-node[aria-expanded="true"]');
	await expect(expandedNodes).toHaveCount(0, { timeout: 5000 });
});
