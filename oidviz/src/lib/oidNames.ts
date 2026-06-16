import type { OidString } from './model.ts';

// Sorted longest-prefix-first so the first match is always the most specific.
const OID_NAMES = [
  ['1.3.6.1.2.1.25.3.3', 'hrProcessorTable'],
  ['1.3.6.1.2.1.31.1.1', 'ifXTable'],
  ['1.3.6.1.2.1.2.2.1.16', 'ifOutOctets'],
  ['1.3.6.1.2.1.2.2.1.10', 'ifInOctets'],
  ['1.3.6.1.2.1.4.20.1', 'ipAddrEntry'],
  ['1.3.6.1.2.1.2.2.1.8', 'ifOperStatus'],
  ['1.3.6.1.2.1.2.2.1.7', 'ifAdminStatus'],
  ['1.3.6.1.2.1.2.2.1.6', 'ifPhysAddress'],
  ['1.3.6.1.2.1.2.2.1.5', 'ifSpeed'],
  ['1.3.6.1.2.1.2.2.1.3', 'ifType'],
  ['1.3.6.1.2.1.2.2.1.2', 'ifDescr'],
  ['1.3.6.1.2.1.2.2.1.1', 'ifIndex'],
  ['1.3.6.1.2.1.4.22', 'ipNetToMediaTable'],
  ['1.3.6.1.2.1.4.24', 'ipRouteTable'],
  ['1.3.6.1.2.1.4.20', 'ipAddrTable'],
  ['1.3.6.1.2.1.25.5', 'hrSWRunTable'],
  ['1.3.6.1.2.1.25.3', 'hrDevice'],
  ['1.3.6.1.2.1.25.2', 'hrStorage'],
  ['1.3.6.1.2.1.25.1', 'hrSystem'],
  ['1.3.6.1.2.1.31.1', 'ifMIBObjects'],
  ['1.3.6.1.2.1.2.2.1', 'ifEntry'],
  ['1.3.6.1.4.1.9.9', 'ciscoMgmt'],
  ['1.3.6.1.4.1.9.2', 'ciscoProducts'],
  ['1.3.6.1.2.1.1.6', 'sysLocation'],
  ['1.3.6.1.2.1.1.5', 'sysName'],
  ['1.3.6.1.2.1.1.4', 'sysContact'],
  ['1.3.6.1.2.1.1.3', 'sysUpTime'],
  ['1.3.6.1.2.1.1.2', 'sysObjectID'],
  ['1.3.6.1.2.1.1.1', 'sysDescr'],
  ['1.3.6.1.2.1.6.13', 'tcpConnTable'],
  ['1.3.6.1.6.3.18', 'snmpCommunityMIB'],
  ['1.3.6.1.6.3.15', 'snmpVacm'],
  ['1.3.6.1.6.3.1', 'snmpV2MIB'],
  ['1.3.6.1.4.1.2021', 'ucdSnmp'],
  ['1.3.6.1.2.1.4.1', 'ipForwarding'],
  ['1.3.6.1.4.1.9', 'cisco'],
  ['1.3.6.1.2.1.2.2', 'ifTable'],
  ['1.3.6.1.2.1.2.1', 'ifNumber'],
  ['1.3.6.1.2.1.31', 'ifMIB'],
  ['1.3.6.1.2.1.25', 'host'],
  ['1.3.6.1.2.1.17', 'dot1dBridge'],
  ['1.3.6.1.2.1.11', 'snmp'],
  ['1.3.6.1.2.1.1', 'system'],
  ['1.3.6.1.2.1.7', 'udp'],
  ['1.3.6.1.2.1.6', 'tcp'],
  ['1.3.6.1.2.1.4', 'ip'],
  ['1.3.6.1.2.1.2', 'interfaces'],
  ['1.3.6.1.4.1', 'enterprises'],
  ['1.3.6.1.2.1', 'mib-2'],
  ['1.3.6.1.6.3', 'snmpModules'],
  ['1.3.6.1.4', 'private'],
  ['1.3.6.1.2', 'mgmt'],
  ['1.3.6.1.6', 'snmpV2'],
  ['1.3.6.1', 'internet'],
] satisfies readonly (readonly [string, string])[];

export const lookupOidName = (oid: OidString): string | undefined => {
  for (const [prefix, name] of OID_NAMES) {
    if (oid === prefix || oid.startsWith(`${prefix}.`)) {
      return name;
    }
  }
};
