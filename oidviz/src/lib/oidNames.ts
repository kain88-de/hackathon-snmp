import type { OidString } from "./model.ts";

const RAW_PREFIXES: [string, string][] = [
	["1.3.6.1.2.1.2.2.1", "Interface Table"],
	["1.3.6.1.2.1.1", "System MIB"],
	["1.3.6.1.2.1.2", "Interfaces MIB"],
	["1.3.6.1.2.1.4", "IP MIB"],
	["1.3.6.1.2.1.5", "ICMP MIB"],
	["1.3.6.1.2.1.6", "TCP MIB"],
	["1.3.6.1.2.1.7", "UDP MIB"],
	["1.3.6.1.2.1.11", "SNMP MIB"],
	["1.3.6.1.2.1.17", "Bridge MIB"],
	["1.3.6.1.2.1.25", "Host Resources MIB"],
	["1.3.6.1.2.1.31", "IF-MIB Extensions"],
	["1.3.6.1.2.1.47", "Entity MIB"],
	["1.3.6.1.2.1.55", "IPv6 MIB"],
	["1.3.6.1.2.1.77", "Application MIB"],
	["1.3.6.1.2.1.83", "Trap Destination MIB"],
	["1.3.6.1.2.1.99", "Entity Sensor MIB"],
	["1.3.6.1.2.1.105", "Power over Ethernet MIB"],
	["1.3.6.1.2.1.127", "ADSL2 MIB"],
	["1.3.6.1.2.1.167", "IP Traffic Stats MIB"],
	["1.3.6.1.4.1.9", "Cisco"],
	["1.3.6.1.4.1.11", "HP/Aruba"],
	["1.3.6.1.4.1.42", "Sun/Oracle"],
	["1.3.6.1.4.1.119", "NEC"],
	["1.3.6.1.4.1.1.1.1", "IBM"],
	["1.3.6.1.4.1.890", "Zyxel"],
	["1.3.6.1.4.1.1916", "Extreme Networks"],
	["1.3.6.1.4.1.1991", "Foundry/Brocade"],
	["1.3.6.1.4.1.2011", "Huawei"],
	["1.3.6.1.4.1.2021", "Net-SNMP (UCD)"],
	["1.3.6.1.4.1.2636", "Juniper"],
	["1.3.6.1.4.1.3076", "Altiga/Cisco VPN"],
	["1.3.6.1.4.1.3375", "F5 Networks"],
	["1.3.6.1.4.1.4526", "Netgear"],
	["1.3.6.1.4.1.4874", "Juniper Netscreen"],
	["1.3.6.1.4.1.5624", "Enterasys"],
	["1.3.6.1.4.1.8072", "Net-SNMP"],
	["1.3.6.1.4.1.14988", "MikroTik"],
	["1.3.6.1.4.1.25461", "Palo Alto"],
	["1.3.6.1.4.1.30065", "Arista"],
	["1.3.6.1.4.1", "Enterprises (private)"],
	["1.3.6.1.6.3.1.1", "SNMPv2 Objects"],
	["1.3.6.1.6.3.1", "SNMPv2 Framework"],
	["1.3.6.1.6.3.10", "SNMP Framework MIB"],
	["1.3.6.1.6.3.15", "SNMP USM MIB"],
	["1.3.6.1.6.3.16", "SNMP VACM MIB"],
	["1.3.6.1.6.3.18", "SNMP Community MIB"],
	["1.3.6.1.2", "MIB-II"],
	["1.3.6.1.4", "Private"],
	["1.3.6.1.5", "Security"],
	["1.3.6.1.6", "SNMPv2"],
	["1.3.6.1", "IETF"],
	["1.3.6", "Internet"],
	["1.3", "DoD Internet"],
];

// Sorted descending by prefix length at module init — most-specific match wins.
const SORTED_PREFIXES: [string, string][] = [...RAW_PREFIXES].sort(
	(a, b): number => b[0].length - a[0].length,
);

export function lookupOidName(oid: OidString): string | null {
	for (const [prefix, name] of SORTED_PREFIXES) {
		if (
			oid.startsWith(prefix) &&
			(oid.length === prefix.length || oid[prefix.length] === ".")
		) {
			return name;
		}
	}
	return null;
}
