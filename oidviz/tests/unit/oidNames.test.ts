import { describe, expect, test } from "bun:test";
import { asOid } from "../../src/lib/model.ts";
import { lookupOidName } from "../../src/lib/oidNames.ts";

describe("lookupOidName", () => {
	test("returns correct name for a known OID", () => {
		expect(lookupOidName(asOid("1.3.6.1.2.1.1.1.0"))).toBe("System MIB");
	});

	test("returns null for an unknown OID", () => {
		expect(lookupOidName(asOid("9.9.9.9"))).toBeNull();
	});

	test("returns the most-specific (longest) prefix match", () => {
		// 1.3.6.1.2.1.2.2.1 (Interface Table) is more specific than 1.3.6.1.2.1.2 (Interfaces MIB)
		expect(lookupOidName(asOid("1.3.6.1.2.1.2.2.1.10.1"))).toBe(
			"Interface Table",
		);
	});

	test("does not match prefix at non-arc boundary (digit run)", () => {
		// 1.3.6.1.20 must NOT match prefix 1.3.6.1.2
		expect(lookupOidName(asOid("1.3.6.1.20"))).toBe("IETF");
	});

	test("matches exact OID that equals a prefix", () => {
		expect(lookupOidName(asOid("1.3.6.1.2.1.1"))).toBe("System MIB");
	});

	test("returns enterprise name for vendor OID", () => {
		expect(lookupOidName(asOid("1.3.6.1.4.1.9.1.1"))).toBe("Cisco");
	});
});
