import { describe, expect, it } from 'bun:test'
import { lookupOidName } from '../../src/lib/oidNames'
import { asOid } from '../../src/lib/model'

describe('lookupOidName', () => {
  it('returns null for unknown OID', () => {
    expect(lookupOidName(asOid('9.9.9.9'))).toBeNull()
  })

  it('exact match', () => {
    expect(lookupOidName(asOid('1.3.6.1.2.1.1'))).toBe('system')
  })

  it('prefix match — OID under a known prefix', () => {
    // 1.3.6.1.2.1.1.5 = sysName (exact), but also under system prefix
    // 1.3.6.1.2.1.1.5.0 is an instance, not in the table
    expect(lookupOidName(asOid('1.3.6.1.2.1.1.5.0'))).toBe('sysName')
  })

  it('longest-prefix wins over shorter prefix', () => {
    // 1.3.6.1.2.1.2.2.1.1 should match ifIndex, not ifEntry, not ifTable, not interfaces
    expect(lookupOidName(asOid('1.3.6.1.2.1.2.2.1.1'))).toBe('ifIndex')
  })

  it('shorter prefix matches when no longer prefix exists', () => {
    // 1.3.6.1.2.1.2.2.1.99 - no exact match for arc 99, but should match ifEntry
    expect(lookupOidName(asOid('1.3.6.1.2.1.2.2.1.99'))).toBe('ifEntry')
  })
})
