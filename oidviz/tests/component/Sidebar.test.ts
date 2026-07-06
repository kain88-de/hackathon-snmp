import { describe, expect, test, vi } from "vitest";
import { mount } from "@vue/test-utils";
import type { DOMWrapper } from "@vue/test-utils";
import { asOid } from "../../src/lib/model.ts";
import type {
	ActiveView,
	AppState,
	FacetState,
	ParseResult,
} from "../../src/lib/model.ts";
import type { Header } from "../../src/lib/types.gen.ts";
import Sidebar from "../../src/components/Sidebar.vue";
import { makeExchange, makeFacetState, makeParseResult } from "./helpers.ts";

const SYSDESCR_OID = "1.3.6.1.2.1.1.1.0";
const SYSOID_OID = "1.3.6.1.2.1.1.2.0";
const SYSUPTIME_OID = "1.3.6.1.2.1.1.3.0";

interface SidebarProps {
	appState: AppState;
	result: ParseResult | null;
	facetState: FacetState;
	activeView: ActiveView;
}

function mountSidebar(overrides: Partial<SidebarProps> = {}) {
	const props: SidebarProps = {
		appState: { phase: "landing" },
		result: null,
		facetState: makeFacetState(),
		activeView: "findings",
		...overrides,
	};
	return mount(Sidebar, { props });
}

type SidebarWrapper = ReturnType<typeof mountSidebar>;

// Header.settings only accepts a fully-formed object on override (ParseResult's
// header field is `Header`, not `Partial<Header>`), so tests that need a custom
// label/settings build a full header from this local factory instead of
// hand-rolling ParseResult from scratch.
function makeHeader(overrides: Partial<Header> = {}): Header {
	return {
		type: "header",
		format_version: 1,
		tool: "oidtrace 0.1.0",
		started_at: "2026-06-11T14:03:07Z",
		session: { id: "5e1f3a9c-6a86-4a0b-9b6e-2f6d6a9c1d42", run: 1, runs_total: 1 },
		snmp: { version: "2c" },
		settings: {
			bulk_size: 10,
			timeout_s: 2,
			retries: 1,
			start_oid: "1.3.6.1",
		},
		...overrides,
	};
}

// Scans .sidebar-section elements for one whose .sidebar-section-title text
// matches — the component has no data-testid hooks, and several sections
// (file, nav, facets) share the .sidebar-section class without a title.
function findSectionByTitle(
	wrapper: SidebarWrapper,
	title: string,
): DOMWrapper<Element> | undefined {
	return wrapper.findAll(".sidebar-section").find((section) => {
		const titleEl = section.find(".sidebar-section-title");
		return titleEl.exists() && titleEl.text() === title;
	});
}

function infoValue(section: DOMWrapper<Element>, key: string): DOMWrapper<Element> {
	const row = section.findAll(".info-row").find((r) => r.find(".info-key").text() === key);
	if (!row) {
		throw new Error(`info-row with key "${key}" not found`);
	}
	return row.find(".info-val");
}

describe("Sidebar", () => {
	describe("file section", () => {
		// appState.phase = "viewer" — the Open file control must only be
		// available once a trace is loaded, since re-opening from other
		// phases (landing/loading/error) is handled by the landing screen.
		test("Open file button and hidden input render in the viewer phase", () => {
			const wrapper = mountSidebar({
				appState: { phase: "viewer", result: makeParseResult() },
			});

			expect(wrapper.find(".sidebar-btn").exists()).toBe(true);
			expect(wrapper.find('input[type="file"]').exists()).toBe(true);
		});

		// appState.phase = "landing" — outside the viewer phase, the file
		// section (button + hidden input) must not render at all.
		test("Open file button is absent outside the viewer phase", () => {
			const wrapper = mountSidebar({ appState: { phase: "landing" } });

			expect(wrapper.find(".sidebar-btn").exists()).toBe(false);
			expect(wrapper.find('input[type="file"]').exists()).toBe(false);
		});

		// appState.phase = "viewer", spy on HTMLInputElement.prototype.click —
		// clicking the visible "Open file" button must delegate to the hidden
		// file input's click(), since the input itself is visually hidden.
		test("clicking Open file opens the hidden file picker", async () => {
			const wrapper = mountSidebar({
				appState: { phase: "viewer", result: makeParseResult() },
			});
			const clickSpy = vi.spyOn(HTMLInputElement.prototype, "click");

			await wrapper.find(".sidebar-btn").trigger("click");

			expect(clickSpy).toHaveBeenCalled();
			clickSpy.mockRestore();
		});
	});

	describe("Device section", () => {
		// result.systemInfo = { point: "start", values: { sysDescr: "Line one\nLine two", ... } }
		// — sysDescr must be truncated to its first line, and sysObjectID/sysUpTime
		// must render the raw values from the system_info record.
		test("renders system_info fields, truncating sysDescr to its first line", () => {
			const wrapper = mountSidebar({
				result: makeParseResult({
					systemInfo: {
						type: "system_info",
						at: 0,
						point: "start",
						values: {
							[SYSDESCR_OID]: "Line one\nLine two",
							[SYSOID_OID]: "1.3.6.1.4.1.9999.1",
							[SYSUPTIME_OID]: 12345,
						},
					},
				}),
			});

			const section = findSectionByTitle(wrapper, "Device");
			expect(section).toBeDefined();
			expect(infoValue(section!, "sysDescr").text()).toBe("Line one");
			expect(infoValue(section!, "sysObjectID").text()).toBe("1.3.6.1.4.1.9999.1");
			expect(infoValue(section!, "sysUpTime").text()).toBe("12345");
		});

		// makeParseResult()'s default systemInfo is null — with no system_info
		// record at all, the Device section (including its title) must not
		// render.
		test("is absent when there is no system_info", () => {
			const wrapper = mountSidebar({ result: makeParseResult() });

			expect(findSectionByTitle(wrapper, "Device")).toBeUndefined();
		});

		// result.systemInfo.point = "end" — a system_info record captured at the
		// end of the walk must not populate the Device section, which only
		// reflects the "start" snapshot.
		test("is absent when system_info point is not start", () => {
			const wrapper = mountSidebar({
				result: makeParseResult({
					systemInfo: { type: "system_info", at: 99, point: "end", values: {} },
				}),
			});

			expect(findSectionByTitle(wrapper, "Device")).toBeUndefined();
		});
	});

	describe("Walk info section", () => {
		// result.summary = { end_reason: "completed", oids_seen: 7, violation_counts: { ... } summing to 3 },
		// header.label = "test-walk", default header.snmp.version "2c" and
		// settings.start_oid "1.3.6.1", 2 exchanges — each Walk info field must
		// reflect the summary/header data rather than deriving from exchanges.
		test("renders label, snmp version, start OID, exchange count, oids seen, and end reason from the summary", () => {
			const wrapper = mountSidebar({
				result: makeParseResult({
					header: makeHeader({ label: "test-walk" }),
					exchanges: [makeExchange(), makeExchange({ seq: 2 })],
					summary: {
						type: "summary",
						at: 12,
						exchanges: 2,
						oids_seen: 7,
						end_reason: "completed",
						violation_counts: { "oid-not-increasing": 2, "duplicate-response": 1 },
					},
				}),
			});

			const section = findSectionByTitle(wrapper, "Walk info");
			expect(section).toBeDefined();
			expect(infoValue(section!, "Label").text()).toBe("test-walk");
			expect(infoValue(section!, "SNMP").text()).toBe("v2c");
			expect(infoValue(section!, "Start OID").text()).toBe("1.3.6.1");
			expect(infoValue(section!, "Exchanges").text()).toBe("2");
			expect(infoValue(section!, "OIDs seen").text()).toBe("7");
			expect(infoValue(section!, "End reason").text()).toBe("completed");
		});

		// result.summary.at = 45 (seconds) — durations under 60s must render as
		// a plain "Ns" seconds string.
		test("duration renders in seconds when under a minute", () => {
			const wrapper = mountSidebar({
				result: makeParseResult({
					summary: {
						type: "summary",
						at: 45,
						exchanges: 0,
						oids_seen: 0,
						end_reason: "completed",
						violation_counts: {},
					},
				}),
			});

			const section = findSectionByTitle(wrapper, "Walk info");
			expect(infoValue(section!, "Duration").text()).toBe("45.0s");
		});

		// result.summary.at = 125 (seconds = 2m 5s) — durations at/over 60s must
		// render as "Mm Ss" rather than a raw seconds count.
		test("duration renders in minutes and seconds when at least a minute", () => {
			const wrapper = mountSidebar({
				result: makeParseResult({
					summary: {
						type: "summary",
						at: 125,
						exchanges: 0,
						oids_seen: 0,
						end_reason: "completed",
						violation_counts: {},
					},
				}),
			});

			const section = findSectionByTitle(wrapper, "Walk info");
			expect(infoValue(section!, "Duration").text()).toBe("2m 5s");
		});

		// result.summary = null (default), 3 exchanges: violations [1, 0, 1] and
		// response OIDs with one OID repeated across exchanges — without a
		// summary, violations must sum the exchanges' violation arrays and OIDs
		// seen must count *distinct* response OIDs, not total occurrences.
		test("computes violations and oids-seen totals from exchanges when there is no summary", () => {
			const oidA = asOid("1.3.6.1.2.1.1.1.0");
			const oidB = asOid("1.3.6.1.2.1.1.2.0");
			const oidC = asOid("1.3.6.1.2.1.1.5.0");
			const wrapper = mountSidebar({
				result: makeParseResult({
					exchanges: [
						makeExchange({ seq: 1, violations: ["oid-not-increasing"], responseOids: [oidA] }),
						makeExchange({ seq: 2, violations: [], responseOids: [oidA, oidB] }),
						makeExchange({ seq: 3, violations: ["duplicate-response"], responseOids: [oidC] }),
					],
				}),
			});

			const section = findSectionByTitle(wrapper, "Walk info");
			expect(infoValue(section!, "Violations").text()).toBe("2");
			expect(infoValue(section!, "OIDs seen").text()).toBe("3");
		});

		// result.summary = null (default) — without a summary record there is no
		// wall-clock duration or end reason to report, so both must fall back
		// to an em dash.
		test("duration and end reason show a dash when there is no summary", () => {
			const wrapper = mountSidebar({ result: makeParseResult() });

			const section = findSectionByTitle(wrapper, "Walk info");
			expect(infoValue(section!, "Duration").text()).toBe("—");
			expect(infoValue(section!, "End reason").text()).toBe("—");
		});

		// result.summary.violation_counts sums to 0 — a zero violation count
		// must render with the "ok" style, not the "err" style.
		test("zero violations render with the ok style", () => {
			const wrapper = mountSidebar({
				result: makeParseResult({
					summary: {
						type: "summary",
						at: 1,
						exchanges: 0,
						oids_seen: 0,
						end_reason: "completed",
						violation_counts: {},
					},
				}),
			});

			const section = findSectionByTitle(wrapper, "Walk info");
			const violations = infoValue(section!, "Violations");
			expect(violations.text()).toBe("0");
			expect(violations.classes()).toContain("info-val--ok");
			expect(violations.classes()).not.toContain("info-val--err");
		});

		// result.summary.violation_counts sums to 1 (> 0) — a non-zero
		// violation count must render with the "err" style, not the "ok" style.
		test("a non-zero violation count renders with the error style", () => {
			const wrapper = mountSidebar({
				result: makeParseResult({
					summary: {
						type: "summary",
						at: 1,
						exchanges: 0,
						oids_seen: 0,
						end_reason: "completed",
						violation_counts: { "oid-not-increasing": 1 },
					},
				}),
			});

			const section = findSectionByTitle(wrapper, "Walk info");
			const violations = infoValue(section!, "Violations");
			expect(violations.text()).toBe("1");
			expect(violations.classes()).toContain("info-val--err");
			expect(violations.classes()).not.toContain("info-val--ok");
		});
	});

	describe("Walk config section", () => {
		// header.settings has resume_from and time_budget_s set — both optional
		// rows must render alongside the always-present bulk size/timeout/retries.
		test("renders resume_from and time_budget_s when present", () => {
			const wrapper = mountSidebar({
				result: makeParseResult({
					header: makeHeader({
						settings: {
							bulk_size: 10,
							timeout_s: 2,
							retries: 1,
							start_oid: "1.3.6.1",
							resume_from: "1.3.6.1.2.1.4.20",
							time_budget_s: 30,
						},
					}),
				}),
			});

			const section = findSectionByTitle(wrapper, "Walk config");
			expect(section).toBeDefined();
			expect(infoValue(section!, "Budget").text()).toBe("30s");
			expect(infoValue(section!, "Resume").text()).toBe("1.3.6.1.2.1.4.20");
		});

		// header.settings has no resume_from/time_budget_s (makeParseResult's
		// default) — the optional rows must be absent, while bulk size,
		// timeout, and retries — which have no presence guard — still render.
		test("omits resume and budget rows when absent, but keeps bulk size, timeout, and retries", () => {
			const wrapper = mountSidebar({ result: makeParseResult() });

			const section = findSectionByTitle(wrapper, "Walk config");
			expect(section).toBeDefined();
			expect(infoValue(section!, "Bulk size").text()).toBe("10");
			expect(infoValue(section!, "Timeout").text()).toBe("2s");
			expect(infoValue(section!, "Retries").text()).toBe("1");
			expect(
				section!.findAll(".info-row").find((r) => r.find(".info-key").text() === "Budget"),
			).toBeUndefined();
			expect(
				section!.findAll(".info-row").find((r) => r.find(".info-key").text() === "Resume"),
			).toBeUndefined();
		});
	});

	// result = null — Device, Walk info, and Walk config are all computed from
	// `result` and must all disappear together when there is no trace loaded.
	test("Device, Walk info, and Walk config sections are all absent when there is no result", () => {
		const wrapper = mountSidebar({ result: null });

		expect(findSectionByTitle(wrapper, "Device")).toBeUndefined();
		expect(findSectionByTitle(wrapper, "Walk info")).toBeUndefined();
		expect(findSectionByTitle(wrapper, "Walk config")).toBeUndefined();
	});

	describe("truncation warning", () => {
		// result.truncated = true — the truncation warning must be visible
		// whenever the parser had to cut the trace short.
		test("is visible when the result is truncated", () => {
			const wrapper = mountSidebar({ result: makeParseResult({ truncated: true }) });

			const warning = wrapper.find(".sidebar-truncation");
			expect(warning.classes()).toContain("sidebar-truncation--visible");
			expect(warning.text()).toContain("Warning: trace was truncated");
		});

		// result.truncated = false (makeParseResult's default) — an untruncated
		// result must not show the warning text or its visible styling.
		test("is hidden when the result is not truncated", () => {
			const wrapper = mountSidebar({ result: makeParseResult() });

			const warning = wrapper.find(".sidebar-truncation");
			expect(warning.classes()).not.toContain("sidebar-truncation--visible");
			expect(warning.text()).toBe("");
		});
	});

	describe("view navigation", () => {
		// activeView = "findings" (default) — clicking each of the three view
		// buttons in turn must emit view-change with that button's own
		// ActiveView value, not the currently active one.
		test("clicking each view button emits view-change with that view", async () => {
			const wrapper = mountSidebar({ activeView: "findings" });
			const buttons = wrapper.findAll(".sidebar-nav-btn");
			expect(buttons).toHaveLength(3);

			await buttons[0]!.trigger("click");
			await buttons[1]!.trigger("click");
			await buttons[2]!.trigger("click");

			const emitted = wrapper.emitted("view-change");
			expect(emitted).toEqual([["findings"], ["minimap"], ["oidtree"]]);
		});

		// activeView = "minimap" — only the button matching the current
		// activeView prop must carry aria-current="page", identifying it to
		// assistive tech as the current page section.
		test("the active view button has aria-current=page", () => {
			const wrapper = mountSidebar({ activeView: "minimap" });
			const buttons = wrapper.findAll(".sidebar-nav-btn");

			const current = buttons.filter((b) => b.attributes("aria-current") === "page");
			expect(current).toHaveLength(1);
			expect(current[0]!.text()).toBe("Minimap + Detail");
		});
	});

	describe("facet controls", () => {
		// facetState.perf = "any" (default) — each performance radio's @change
		// handler emits facet-change unconditionally with its own option
		// value, regardless of which radio started out checked.
		test("each performance radio emits facet-change with its perf value", async () => {
			const wrapper = mountSidebar();
			const radios = wrapper.findAll('input[name="perf"]');
			expect(radios).toHaveLength(4);

			for (const radio of radios) {
				await radio.trigger("change");
			}

			const emitted = wrapper.emitted("facet-change");
			expect(emitted).toEqual([
				[{ perf: "any" }],
				[{ perf: "fast" }],
				[{ perf: "slow" }],
				[{ perf: "timeout" }],
			]);
		});

		// facetState.corr = "any" (default) — each correctness radio emits
		// facet-change with its own corr value.
		test("each correctness radio emits facet-change with its corr value", async () => {
			const wrapper = mountSidebar();
			const radios = wrapper.findAll('input[name="corr"]');
			expect(radios).toHaveLength(2);

			await radios[0]!.trigger("change");
			await radios[1]!.trigger("change");

			const emitted = wrapper.emitted("facet-change");
			expect(emitted).toEqual([[{ corr: "any" }], [{ corr: "violations" }]]);
		});

		// facetState.retryOnly = false (default) — checking then unchecking the
		// retries-only checkbox must emit facet-change with the checkbox's own
		// checked state each time, proving the handler reads live DOM state
		// rather than a stale prop value.
		test("toggling the retries-only checkbox emits facet-change true then false", async () => {
			const wrapper = mountSidebar();
			const checkbox = wrapper.find('input[type="checkbox"]');

			await checkbox.setValue(true);
			await checkbox.setValue(false);

			const emitted = wrapper.emitted("facet-change");
			expect(emitted).toEqual([[{ retryOnly: true }], [{ retryOnly: false }]]);
		});

		// facetState.slowMs = 1000 (default, 1s shown in the input) — entering
		// "2" (seconds) in the slow-threshold input must convert to
		// milliseconds before emitting facet-change.
		test("entering a slow threshold in seconds emits facet-change in milliseconds", async () => {
			const wrapper = mountSidebar();
			const input = wrapper.find(".sidebar-number-input");

			await input.setValue("2");

			const emitted = wrapper.emitted("facet-change");
			expect(emitted).toEqual([[{ slowMs: 2000 }]]);
		});

		// entering "0" — guarded by `seconds > 0`, a zero threshold must not
		// emit facet-change at all.
		test("entering a zero slow threshold emits no facet-change", async () => {
			const wrapper = mountSidebar();
			const input = wrapper.find(".sidebar-number-input");

			await input.setValue("0");

			expect(wrapper.emitted("facet-change")).toBeUndefined();
		});

		// entering "abc" — guarded by `!isNaN`, a non-numeric threshold must
		// not emit facet-change at all.
		test("entering a non-numeric slow threshold emits no facet-change", async () => {
			const wrapper = mountSidebar();
			const input = wrapper.find(".sidebar-number-input");

			await input.setValue("abc");

			expect(wrapper.emitted("facet-change")).toBeUndefined();
		});
	});
});
