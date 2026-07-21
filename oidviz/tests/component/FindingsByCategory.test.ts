import { describe, expect, test } from "vitest";
import { mount } from "@vue/test-utils";
import FindingsByCategory from "../../src/components/FindingsByCategory.vue";
import { asOid } from "../../src/lib/model.ts";
import { makeExchange, makeFacetState } from "./helpers.ts";

describe("FindingsByCategory", () => {
	// makeExchange creates exchanges with default rtt: 100, isTimeout: false,
	// violations: [], attemptCount: 1. makeFacetState defaults to slowMs: 1000.
	// We'll use slowMs: 500 to categorise clearly: exchanges with rtt <= 500 are
	// fast, rtt > 500 are slow, isTimeout: true are timeout. This test verifies
	// that section headers correctly count and label each category.
	test("section headers reflect categorised counts", () => {
		const exchanges = [
			makeExchange({ seq: 1, rtt: 600 }), // slow
			makeExchange({ seq: 2, rtt: 700 }), // slow
			makeExchange({ seq: 3, rtt: 300 }), // fast
			makeExchange({ seq: 4, isTimeout: true }), // timeout
		];
		const facetState = makeFacetState({ slowMs: 500 });

		const wrapper = mount(FindingsByCategory, {
			props: { exchanges, facetState },
		});

		const headers = wrapper.findAll(".section-header");
		// Should have: slow header, timeout header, fast header = 3 headers
		expect(headers).toHaveLength(3);

		// Headers should be in order: slow, timeout, fast
		expect(headers[0]!.attributes("data-label")).toBe("Slow (2)");
		expect(headers[1]!.attributes("data-label")).toBe("Timed out (1)");
		expect(headers[2]!.attributes("data-label")).toBe("Fast (1)");
	});

	// makeExchange defaults to rtt: 100, isTimeout: false. With slowMs: 500,
	// all default exchanges are fast (rtt <= 500). Case 1: only timeout
	// exchanges → Fast header absent. Case 2: mix with some fast → Fast header
	// present. This proves the component conditionally renders the Fast section
	// only when there are fast exchanges, not just always.
	test("Fast section only appears when there are fast exchanges", () => {
		// Case 1: No fast exchanges (only timeout)
		const exchanges1 = [
			makeExchange({ seq: 1, isTimeout: true }),
			makeExchange({ seq: 2, isTimeout: true }),
		];
		const facetState = makeFacetState({ slowMs: 500 });

		const wrapper1 = mount(FindingsByCategory, {
			props: { exchanges: exchanges1, facetState },
		});

		let headers = wrapper1.findAll(".section-header");
		expect(headers).toHaveLength(2); // Only slow and timeout headers
		const labels1 = headers.map((h) => h.attributes("data-label"));
		expect(labels1).toContain("Slow (0)");
		expect(labels1).toContain("Timed out (2)");
		expect(labels1).not.toContain("Fast");

		// Case 2: Mix with some fast exchanges
		const exchanges2 = [
			makeExchange({ seq: 1, isTimeout: true }),
			makeExchange({ seq: 2, rtt: 300 }), // fast
		];

		const wrapper2 = mount(FindingsByCategory, {
			props: { exchanges: exchanges2, facetState },
		});

		headers = wrapper2.findAll(".section-header");
		expect(headers).toHaveLength(3); // Slow, timeout, and fast headers
		const labels2 = headers.map((h) => h.attributes("data-label"));
		expect(labels2).toContain("Fast (1)");
	});

	// Any non-empty exchange set. When mounted with at least one exchange, all
	// section headers must have aria-expanded="true" initially, proving sections
	// default to expanded state for visibility.
	test("sections default expanded", () => {
		const exchanges = [
			makeExchange({ seq: 1, rtt: 600 }),
			makeExchange({ seq: 2, isTimeout: true }),
		];
		const facetState = makeFacetState({ slowMs: 500 });

		const wrapper = mount(FindingsByCategory, {
			props: { exchanges, facetState },
		});

		const headers = wrapper.findAll(".section-header");
		for (const header of headers) {
			expect(header.attributes("aria-expanded")).toBe("true");
		}
	});

	// makeFacetState defaults to slowMs: 1000. Create one slow exchange (rtt: 1500)
	// and one timeout. Click the Slow header button. The aria-expanded must flip
	// to "false", and the slow section's rows must no longer render in the DOM,
	// proving click-to-toggle works.
	test("clicking a header toggles it", async () => {
		const exchanges = [
			makeExchange({ seq: 1, rtt: 1500 }), // slow
			makeExchange({ seq: 2, isTimeout: true }), // timeout
		];
		const facetState = makeFacetState(); // slowMs: 1000

		const wrapper = mount(FindingsByCategory, {
			props: { exchanges, facetState },
		});

		const headers = wrapper.findAll(".section-header");
		const slowHeader = headers[0]!;

		// Initially expanded
		expect(slowHeader.attributes("aria-expanded")).toBe("true");

		// Before click, one slow row should exist
		let rows = wrapper.findAll(".exchange-row");
		const slowRowsBefore = rows.filter((r) => r.attributes("data-seq") === "1");
		expect(slowRowsBefore).toHaveLength(1);

		// Click the slow header
		await slowHeader.trigger("click");

		// After click, aria-expanded should be false
		expect(slowHeader.attributes("aria-expanded")).toBe("false");

		// After click, the slow row should no longer render
		rows = wrapper.findAll(".exchange-row");
		const slowRowsAfter = rows.filter((r) => r.attributes("data-seq") === "1");
		expect(slowRowsAfter).toHaveLength(0);
	});

	// makeExchange defaults to violations: []. Create an exchange with
	// violations: ["oid-not-increasing", "duplicate-response"] (2 violations).
	// The row's .badge-violation element must show the specific violation
	// names, joined — a bare count ("2 viol") doesn't say whether it was
	// oid-not-increasing, malformed-ber, or something else entirely, which is
	// the actual finding an operator needs. The title attribute repeats the
	// same list, as a fallback for when the visible text is CSS-truncated.
	test("exchange with a violation shows a badge naming the specific violations", () => {
		const exchanges = [
			makeExchange({
				seq: 1,
				rtt: 300,
				violations: ["oid-not-increasing", "duplicate-response"],
			}),
		];
		const facetState = makeFacetState({ slowMs: 500 });

		const wrapper = mount(FindingsByCategory, {
			props: { exchanges, facetState },
		});

		const row = wrapper.find(".exchange-row");
		expect(row.exists()).toBe(true);

		const badge = row.find(".badge-violation");
		expect(badge.exists()).toBe(true);
		expect(badge.text()).toBe("oid-not-increasing, duplicate-response");
		expect(badge.attributes("title")).toBe(
			"oid-not-increasing, duplicate-response",
		);
	});

	// makeExchange defaults to attemptCount: 1. Create an exchange with
	// attemptCount: 3. The row must render a .badge-retry element with text
	// "×3". By using 3 retries, we distinguish from exchanges with retries
	// (count: 1) — if the component rendered a badge for any attemptCount > 1
	// without showing the count, it would show "×1", not "×3".
	test("exchange with retries shows a retry-count badge", () => {
		const exchanges = [
			makeExchange({ seq: 1, rtt: 300, attemptCount: 3 }),
		];
		const facetState = makeFacetState({ slowMs: 500 });

		const wrapper = mount(FindingsByCategory, {
			props: { exchanges, facetState },
		});

		const row = wrapper.find(".exchange-row");
		expect(row.exists()).toBe(true);

		const badge = row.find(".badge-retry");
		expect(badge.exists()).toBe(true);
		expect(badge.text()).toBe("×3");
	});

	// Any exchange row. The row must render as a real <button> element so it
	// is reachable by Tab and announced as interactive by screen readers,
	// rather than an inert <div> that only responds to a mouse click.
	test("an exchange row renders as a real button for keyboard and screen-reader access", () => {
		const exchanges = [makeExchange({ seq: 1, rtt: 300 })];
		const facetState = makeFacetState({ slowMs: 500 });

		const wrapper = mount(FindingsByCategory, {
			props: { exchanges, facetState },
		});

		const row = wrapper.find(".exchange-row");
		expect(row.element.tagName).toBe("BUTTON");
	});

	// Any exchange row. When the user clicks the row, the component must emit
	// focus-exchange with that exchange's seq number. Use a fast exchange
	// (rtt: 300, slowMs: 500) to avoid special formatting, focusing the test
	// on the emit behavior.
	test("clicking an exchange row emits focus-exchange with the seq", async () => {
		const exchanges = [makeExchange({ seq: 42, rtt: 300 })];
		const facetState = makeFacetState({ slowMs: 500 });

		const wrapper = mount(FindingsByCategory, {
			props: { exchanges, facetState },
		});

		const row = wrapper.find(".exchange-row");
		await row.trigger("click");

		const emitted = wrapper.emitted("focus-exchange");
		expect(emitted).toBeDefined();
		expect(emitted).toHaveLength(1);
		expect(emitted![0]).toEqual([42]);
	});

	// Uses the same slowMs: 1000 boundary values as tests/unit/utils.test.ts's
	// rttCssClass suite: rtt: 1000 (exactly at slowMs, seq 1) must be dim-fast
	// — proving the component wires up rttCssClass's strict `>` comparison
	// rather than `>=`; rtt: 1500 (seq 2) must be dim-slow; isTimeout: true
	// (seq 3) must be dim-timeout regardless of rtt.
	test("row rtt element has correct class matching exchange status", () => {
		const exchanges = [
			makeExchange({ seq: 1, rtt: 1000 }), // at slowMs boundary -> fast
			makeExchange({ seq: 2, rtt: 1500 }), // above slowMs -> slow
			makeExchange({ seq: 3, isTimeout: true }), // timeout
		];
		const facetState = makeFacetState({ slowMs: 1000 });

		const wrapper = mount(FindingsByCategory, {
			props: { exchanges, facetState },
		});

		const rows = wrapper.findAll(".exchange-row");
		expect(rows).toHaveLength(3);

		// Fast row (seq: 1)
		const fastRow = rows.find((r) => r.attributes("data-seq") === "1");
		expect(fastRow).toBeDefined();
		const fastRtt = fastRow!.find(".rtt");
		expect(fastRtt.classes()).toContain("dim-fast");

		// Slow row (seq: 2)
		const slowRow = rows.find((r) => r.attributes("data-seq") === "2");
		expect(slowRow).toBeDefined();
		const slowRtt = slowRow!.find(".rtt");
		expect(slowRtt.classes()).toContain("dim-slow");

		// Timeout row (seq: 3)
		const timeoutRow = rows.find((r) => r.attributes("data-seq") === "3");
		expect(timeoutRow).toBeDefined();
		const timeoutRtt = timeoutRow!.find(".rtt");
		expect(timeoutRtt.classes()).toContain("dim-timeout");
	});

	// requestOid sysDescr.0 (1.3.6.1.2.1.1.1.0), a real compiled OID — the row
	// must show its resolved name as a label and its description as the OID's
	// tooltip (not the OID text itself, which is already visible), so an
	// operator scanning a slow/timeout section can tell what spec object a row
	// is about without switching to the OID Tree view.
	test("a row with a recognized requestOid shows its name and description", () => {
		const exchanges = [
			makeExchange({ seq: 1, rtt: 300, requestOid: asOid("1.3.6.1.2.1.1.1.0") }),
		];
		const facetState = makeFacetState({ slowMs: 500 });

		const wrapper = mount(FindingsByCategory, {
			props: { exchanges, facetState },
		});

		const row = wrapper.find(".exchange-row");
		expect(row.find(".oid-name").text()).toBe("sysDescr");
		expect(row.find(".oid").attributes("title")).toBe(
			"A textual description of the entity.",
		);
	});

	// requestOid 9.9.9.9, genuinely unrecognized — no compiled entry exists
	// under it at all. The row must show no name label and no title on the OID
	// span, matching how a missing value is omitted elsewhere (e.g. the Fast
	// header) rather than shown empty or as literal "null".
	test("a row with an unrecognized requestOid shows no name label or tooltip", () => {
		const exchanges = [
			makeExchange({ seq: 1, rtt: 300, requestOid: asOid("9.9.9.9") }),
		];
		const facetState = makeFacetState({ slowMs: 500 });

		const wrapper = mount(FindingsByCategory, {
			props: { exchanges, facetState },
		});

		const row = wrapper.find(".exchange-row");
		expect(row.find(".oid-name").exists()).toBe(false);
		expect(row.find(".oid").attributes("title")).toBeUndefined();
	});
});
