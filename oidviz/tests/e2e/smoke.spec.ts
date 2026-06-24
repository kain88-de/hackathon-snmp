import { test, expect } from "@playwright/test";

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
