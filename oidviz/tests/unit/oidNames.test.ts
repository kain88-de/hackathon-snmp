import { describe, expect, test } from "vitest";
import { asOid } from "../../src/lib/model.ts";
import { lookupOidName } from "../../src/lib/oidNames.gen.ts";

describe("lookupOidName", () => {
	test("returns name and description for a known object OID", () => {
		expect(lookupOidName(asOid("1.3.6.1.2.1.1.1.0"))).toEqual({
			name: "sysDescr",
			description: "A textual description of the entity.",
		});
	});

	test("returns null for an unrecognized OID outside every compiled module", () => {
		expect(lookupOidName(asOid("9.9.9.9"))).toBeNull();
	});

	test("returns the most-specific (longest) prefix match", () => {
		// ifDescr (the column) is more specific than its parent table-row entry.
		expect(lookupOidName(asOid("1.3.6.1.2.1.2.2.1.2.1"))).toEqual({
			name: "ifDescr",
			description:
				"A textual string containing information about the interface.",
		});
	});

	test("does not match prefix at non-arc boundary (digit run)", () => {
		// 1.3.6.1.20 must NOT match prefix 1.3.6.1.2 ("mgmt").
		expect(lookupOidName(asOid("1.3.6.1.20"))).toEqual({
			name: "internet",
			description: null,
		});
	});

	test("matches exact OID that equals a prefix", () => {
		expect(lookupOidName(asOid("1.3.6.1.2.1.1"))).toEqual({
			name: "system",
			description: null,
		});
	});

	test("structural node with no DESCRIPTION clause has null description", () => {
		expect(lookupOidName(asOid("1.3.6.1.4.1"))).toEqual({
			name: "enterprises",
			description: null,
		});
	});

	test("dropped vendor OID resolves through its generic ancestor, not null", () => {
		// A Cisco OID is not in any compiled module, but resolves via enterprises.
		expect(lookupOidName(asOid("1.3.6.1.4.1.9.1.1"))).toEqual({
			name: "enterprises",
			description: null,
		});
	});
});
