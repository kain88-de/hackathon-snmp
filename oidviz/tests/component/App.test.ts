import { describe, expect, test, vi } from "vitest";
import { mount } from "@vue/test-utils";
import { nextTick } from "vue";
import App from "../../src/App.vue";
import LandingScreen from "../../src/components/LandingScreen.vue";
import { makeExchange, makeParseResult } from "./helpers.ts";

// Stands in for the real parser worker: App.vue only relies on
// addEventListener("message"/"error"), postMessage, and terminate, so a plain
// EventTarget subclass is enough to drive both success and stale-completion
// scenarios without a real Worker/module loader.
class MockWorker extends EventTarget {
	static instances: MockWorker[] = [];
	terminated = false;

	constructor(_url: string | URL, _options?: WorkerOptions) {
		super();
		MockWorker.instances.push(this);
	}

	postMessage(_message: unknown): void {}

	terminate(): void {
		this.terminated = true;
	}

	emitResult(data: ReturnType<typeof makeParseResult>): void {
		this.dispatchEvent(new MessageEvent("message", { data: { data, type: "result" } }));
	}
}

describe("App worker completion handling", () => {
	// Two file loads issued before either worker responds — the second load
	// must terminate and supersede the first, per the drop-zone one-worker-at-
	// a-time contract already implemented in onFileSelected.
	test("loading a second file terminates the first worker", async () => {
		vi.stubGlobal("Worker", MockWorker);
		MockWorker.instances = [];

		const wrapper = mount(App);
		const landing = wrapper.findComponent(LandingScreen);

		landing.vm.$emit("file-selected", new ArrayBuffer(1));
		await nextTick();
		landing.vm.$emit("file-selected", new ArrayBuffer(1));
		await nextTick();

		expect(MockWorker.instances).toHaveLength(2);
		expect(MockWorker.instances[0]!.terminated).toBe(true);

		vi.unstubAllGlobals();
	});

	// makeParseResult({ exchanges: [makeExchange(), makeExchange()] }) for the
	// second (current) load vs. a single-exchange result for the first
	// (superseded) load — the first worker's result arrives *after* the
	// second's, simulating the exact race in finding #18: an older worker
	// result must not overwrite the newer parse state once a load has been
	// superseded.
	test("a stale result from a superseded worker does not overwrite the newer parse state", async () => {
		vi.stubGlobal("Worker", MockWorker);
		MockWorker.instances = [];

		const wrapper = mount(App);
		const landing = wrapper.findComponent(LandingScreen);

		landing.vm.$emit("file-selected", new ArrayBuffer(1));
		await nextTick();
		landing.vm.$emit("file-selected", new ArrayBuffer(1));
		await nextTick();

		const [staleWorker, currentWorker] = MockWorker.instances;

		currentWorker!.emitResult(makeParseResult({ exchanges: [makeExchange(), makeExchange()] }));
		await nextTick();

		staleWorker!.emitResult(makeParseResult({ exchanges: [makeExchange()] }));
		await nextTick();

		const exchangesRow = wrapper
			.findAll(".info-row")
			.find((row) => row.find(".info-key").text() === "Exchanges");
		expect(exchangesRow).toBeDefined();
		expect(exchangesRow!.find(".info-val").text()).toBe("2");

		vi.unstubAllGlobals();
	});
});
