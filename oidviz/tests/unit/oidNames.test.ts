import { describe, expect, it } from 'bun:test';
import { lookupOidName } from '../../src/lib/oidNames';
import { asOid } from '../../src/lib/model';

describe('lookupOidName', () => {
  it('returns the name for an exact prefix match', () => {
    expect(lookupOidName(asOid('1.3.6.1.2.1.1'))).toBe('system');
    expect(lookupOidName(asOid('1.3.6.1'))).toBe('internet');
  });

  it('returns the name when the OID starts with a known prefix followed by a dot', () => {
    expect(lookupOidName(asOid('1.3.6.1.2.1.1.5.0'))).toBe('sysName');
    expect(lookupOidName(asOid('1.3.6.1.2.1.2.2.1.8.3'))).toBe('ifOperStatus');
  });

  it('returns the longest matching prefix when multiple prefixes match', () => {
    // '1.3.6.1.2.1.2.2.1.1' (ifIndex) is longer than '1.3.6.1.2.1.2.2.1' (ifEntry)
    expect(lookupOidName(asOid('1.3.6.1.2.1.2.2.1.1.5'))).toBe('ifIndex');
    // '1.3.6.1.4.1.9.9' is longer than '1.3.6.1.4.1.9' and '1.3.6.1.4.1'
    expect(lookupOidName(asOid('1.3.6.1.4.1.9.9.1'))).toBe('ciscoMgmt');
  });

  it('returns null when no prefix matches', () => {
    expect(lookupOidName(asOid('1.2.3.4.5'))).toBeNull();
    expect(lookupOidName(asOid('2.5.4.3'))).toBeNull();
  });

  it('does not match on a partial arc (sibling prefix)', () => {
    // '1.3.6.1.20' must NOT match '1.3.6.1.2' (mgmt), but does match '1.3.6.1' (internet)
    expect(lookupOidName(asOid('1.3.6.1.20'))).toBe('internet');
    // '1.3.6.1.2.1.110' must NOT match '1.3.6.1.2.1.11' (snmp)
    expect(lookupOidName(asOid('1.3.6.1.2.1.110'))).toBe('mib-2');
  });
});
