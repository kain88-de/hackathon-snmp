import { describe, expect, test, vi } from "vitest";
import { mount } from "@vue/test-utils";
import type { AppState } from "../../src/lib/model.ts";
import LandingScreen from "../../src/components/LandingScreen.vue";

describe("LandingScreen", () => {
	// appState = { phase: "landing" } — The component must show the drop zone
	// when in landing phase, and hide loading overlays/error banners since
	// they are phase-specific.
	test("landing phase shows the drop zone", () => {
		const appState: AppState = { phase: "landing" };
		const wrapper = mount(LandingScreen, { props: { appState } });

		const dropZone = wrapper.find('[role="region"][aria-label="Drop zone for OID trace files"]');
		expect(dropZone.exists()).toBe(true);
		expect(dropZone.isVisible()).toBe(true);

		const loadingOverlay = wrapper.find('[role="status"]');
		expect(loadingOverlay.exists()).toBe(false);

		const errorBanner = wrapper.find('[role="alert"]');
		expect(errorBanner.exists()).toBe(false);
	});

	// appState = { phase: "loading" } — The component must show the loading
	// overlay and hide the drop zone entirely when loading, since they are
	// mutually exclusive in the v-if/v-else structure.
	test("loading phase shows the overlay", () => {
		const appState: AppState = { phase: "loading" };
		const wrapper = mount(LandingScreen, { props: { appState } });

		const loadingOverlay = wrapper.find('[role="status"][aria-label="Loading trace file"]');
		expect(loadingOverlay.exists()).toBe(true);
		expect(loadingOverlay.isVisible()).toBe(true);

		const dropZone = wrapper.find('[role="region"][aria-label="Drop zone for OID trace files"]');
		expect(dropZone.exists()).toBe(false);
	});

	// appState = { phase: "error", message: "boom" } — The error phase must
	// render an error banner while keeping the drop zone visible, proving
	// errors are recoverable (user can try again without reloading).
	test("error phase shows the drop zone and an error banner", () => {
		const appState: AppState = { phase: "error", message: "boom" };
		const wrapper = mount(LandingScreen, { props: { appState } });

		const errorBanner = wrapper.find('[role="alert"]');
		expect(errorBanner.exists()).toBe(true);
		expect(errorBanner.isVisible()).toBe(true);
		expect(errorBanner.text()).toBe("boom");

		const dropZone = wrapper.find('[role="region"][aria-label="Drop zone for OID trace files"]');
		expect(dropZone.exists()).toBe(true);
		expect(dropZone.isVisible()).toBe(true);
	});

	// appState = { phase: "landing" }, spy on HTMLInputElement.prototype.click
	// — Pressing Enter on the drop zone must delegate to the hidden file input's
	// click() method, proving keyboard accessibility to the file picker.
	test("Enter on the drop zone opens the file picker", () => {
		const appState: AppState = { phase: "landing" };
		const wrapper = mount(LandingScreen, { props: { appState } });

		const clickSpy = vi.spyOn(HTMLInputElement.prototype, "click");

		const dropZone = wrapper.find('[role="region"]');
		const keyboardEvent = new KeyboardEvent("keydown", {
			key: "Enter",
			bubbles: true,
		});
		dropZone.element.dispatchEvent(keyboardEvent);

		expect(clickSpy).toHaveBeenCalled();
		clickSpy.mockRestore();
	});

	// appState = { phase: "landing" }, spy on HTMLInputElement.prototype.click
	// — Pressing Space on the drop zone must delegate to the file input's
	// click(), providing keyboard accessibility via spacebar as documented
	// in the drop zone UI text.
	test("Space on the drop zone opens the file picker", () => {
		const appState: AppState = { phase: "landing" };
		const wrapper = mount(LandingScreen, { props: { appState } });

		const clickSpy = vi.spyOn(HTMLInputElement.prototype, "click");

		const dropZone = wrapper.find('[role="region"]');
		const keyboardEvent = new KeyboardEvent("keydown", {
			key: " ",
			bubbles: true,
		});
		dropZone.element.dispatchEvent(keyboardEvent);

		expect(clickSpy).toHaveBeenCalled();
		clickSpy.mockRestore();
	});

	// appState = { phase: "landing" }, a synthetic File with known text content
	// dropped onto the drop zone — The component must read the File's
	// arrayBuffer() and emit file-selected with the parsed buffer, proving
	// drag-drop file transfer works end-to-end.
	test("dropping a file emits file-selected", async () => {
		const appState: AppState = { phase: "landing" };
		const wrapper = mount(LandingScreen, { props: { appState } });

		const fileContent = "test-file-content";
		const file = new File([fileContent], "test.oidtrace.jsonl.gz", {
			type: "application/gzip",
		});

		const dropZone = wrapper.find('[role="region"]');

		// Manually create and dispatch drop event with proper dataTransfer
		const dropEvent = new DragEvent("drop", {
			bubbles: true,
			cancelable: true,
		});

		// Mock the dataTransfer property
		Object.defineProperty(dropEvent, "dataTransfer", {
			value: {
				files: {
					item: (index: number) => (index === 0 ? file : null),
				},
				items: {
					add: () => {},
				},
			},
		});

		dropZone.element.dispatchEvent(dropEvent);

		// Wait for the async readFile/arrayBuffer to complete
		await wrapper.vm.$nextTick();
		await new Promise((resolve) => setTimeout(resolve, 50));

		const emittedRaw = wrapper.emitted("file-selected");
		expect(emittedRaw).toBeDefined();
		const emitted = emittedRaw as any;
		expect(emitted).toHaveLength(1);

		const emittedBuffer: ArrayBuffer = emitted[0][0];
		const decoded = new TextDecoder().decode(emittedBuffer);
		expect(decoded).toBe(fileContent);
	});

	// appState = { phase: "landing" }, a File-like object whose arrayBuffer()
	// rejects with a known error message — The component must catch the
	// rejection and emit file-error with the error message, proving graceful
	// error handling for unreadable files.
	test("a file read failure emits file-error", async () => {
		const appState: AppState = { phase: "landing" };
		const wrapper = mount(LandingScreen, { props: { appState } });

		const errorMessage = "Permission denied";
		const failingFile = {
			arrayBuffer: () =>
				Promise.reject(new Error(errorMessage)),
		} as unknown as File;

		const dropZone = wrapper.find('[role="region"]');

		// Manually create and dispatch drop event with a failing file
		const dropEvent = new DragEvent("drop", {
			bubbles: true,
			cancelable: true,
		});

		// Mock the dataTransfer property with the failing file
		Object.defineProperty(dropEvent, "dataTransfer", {
			value: {
				files: {
					item: (index: number) => (index === 0 ? failingFile : null),
				},
				items: {
					add: () => {},
				},
			},
		});

		dropZone.element.dispatchEvent(dropEvent);

		// Wait for the async rejection to be caught and emit
		await wrapper.vm.$nextTick();
		await new Promise((resolve) => setTimeout(resolve, 50));

		const emittedRaw = wrapper.emitted("file-error");
		expect(emittedRaw).toBeDefined();
		const emitted = emittedRaw as any;
		expect(emitted).toHaveLength(1);

		expect(emitted[0][0]).toBe(errorMessage);
	});

	// appState = { phase: "landing" } — Dragging a file over the drop zone must
	// add the drag-over class for visual feedback, and dragleave must remove it,
	// proving the drag state toggles rather than sticking permanently.
	test("dragover adds the drag-over class, dragleave removes it", async () => {
		const appState: AppState = { phase: "landing" };
		const wrapper = mount(LandingScreen, { props: { appState } });

		const dropZone = wrapper.find('[role="region"]');
		expect(dropZone.classes()).not.toContain("drag-over");

		dropZone.element.dispatchEvent(
			new DragEvent("dragover", { bubbles: true, cancelable: true }),
		);
		await wrapper.vm.$nextTick();
		expect(dropZone.classes()).toContain("drag-over");

		dropZone.element.dispatchEvent(new DragEvent("dragleave", { bubbles: true }));
		await wrapper.vm.$nextTick();
		expect(dropZone.classes()).not.toContain("drag-over");
	});

	// appState = { phase: "landing" }, a synthetic File selected via the hidden
	// native <input type="file"> (not drag-drop) — The input's change handler
	// must read the same way as onDrop and emit file-selected, proving the
	// file-picker path (opened via click/keyboard) works independently of drag-drop.
	test("selecting a file via the native file input emits file-selected", async () => {
		const appState: AppState = { phase: "landing" };
		const wrapper = mount(LandingScreen, { props: { appState } });

		const fileContent = "picked-file-content";
		const file = new File([fileContent], "picked.oidtrace.jsonl.gz", {
			type: "application/gzip",
		});

		const fileInput = wrapper.find('input[type="file"]');
		Object.defineProperty(fileInput.element, "files", {
			value: {
				item: (index: number) => (index === 0 ? file : null),
			},
			configurable: true,
		});

		await fileInput.trigger("change");
		await new Promise((resolve) => setTimeout(resolve, 50));

		const emittedRaw = wrapper.emitted("file-selected");
		expect(emittedRaw).toBeDefined();
		const emitted = emittedRaw as any;
		expect(emitted).toHaveLength(1);

		const emittedBuffer: ArrayBuffer = emitted[0][0];
		const decoded = new TextDecoder().decode(emittedBuffer);
		expect(decoded).toBe(fileContent);
	});
});
