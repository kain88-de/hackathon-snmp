import type { DomainExchange, Incident, OidString } from './model'

const REGION_PREFIXES: ReadonlyArray<readonly [string, string]> = [
  // Longer prefixes must come before shorter ones sharing the same root
  ['1.3.6.1.2.1.2.2.1', 'ifTable'],
  ['1.3.6.1.2.1.1.',    'system'],
  ['1.3.6.1.2.1.2.',    'interfaces'],
  ['1.3.6.1.2.1.4.',    'ip'],
  ['1.3.6.1.2.1.6.',    'tcp'],
  ['1.3.6.1.2.1.11.',   'snmp'],
  ['1.3.6.1.2.1.25.',   'hrSystem'],
  ['1.3.6.1.4.1.',      'enterprises'],
]

const GAP_WINDOW = 8

function getRegion(oid: OidString): string {
  for (const [prefix, name] of REGION_PREFIXES) {
    if (oid.startsWith(prefix)) return name
  }
  return oid.split('.').slice(0, 8).join('.')
}

function dominantRegion(members: number[], exchanges: ReadonlyArray<DomainExchange>): string {
  const counts = new Map<string, number>()
  let best = ''
  let bestCount = 0
  for (const i of members) {
    const ex = exchanges[i]
    if (ex === undefined) continue
    const r = getRegion(ex.requestOid)
    const c = (counts.get(r) ?? 0) + 1
    counts.set(r, c)
    if (c > bestCount) {
      bestCount = c
      best = r
    }
  }
  return best
}

function computeScore(c: Incident): number {
  return (
    100 * c.timeoutCount +
    50 * c.violationTypes.size +
    10 * c.retryCount +
    Math.log10(Math.max(c.peakRtt, 1)) * 5 +
    c.members.length * 0.1
  )
}

function buildCluster(members: number[], exchanges: ReadonlyArray<DomainExchange>): Incident {
  // members is always non-empty when called
  const startIdx = members[0] as number
  const endIdx = members[members.length - 1] as number
  const startEx = exchanges[startIdx] as DomainExchange
  const endEx = exchanges[endIdx] as DomainExchange
  const peakRtt = Math.max(...members.map(i => (exchanges[i] as DomainExchange).rtt))
  const retryCount = members.reduce((sum, i) => sum + ((exchanges[i] as DomainExchange).attemptCount - 1), 0)
  const timeoutCount = members.filter(i => (exchanges[i] as DomainExchange).isTimeout).length
  const violationTypes = new Set(members.flatMap(i => (exchanges[i] as DomainExchange).violations))
  const region = dominantRegion(members, exchanges)

  const incident: Incident = {
    startIdx,
    endIdx,
    startSeq: startEx.seq,
    endSeq: endEx.seq,
    members,
    peakRtt,
    retryCount,
    timeoutCount,
    violationTypes,
    region,
    score: 0,
  }
  incident.score = computeScore(incident)
  return incident
}

export function buildIncidents(exchanges: ReadonlyArray<DomainExchange>, slowMs: number): Incident[] {
  if (exchanges.length === 0) return []

  // Build anomaly boolean array in O(n)
  const anomalous = exchanges.map(ex =>
    ex.rtt > slowMs || ex.violations.length > 0 || ex.attemptCount > 1 || ex.isTimeout
  )

  const incidents: Incident[] = []

  // Gap-window clustering
  let clusterMembers: number[] | null = null
  let lastMemberIdx = -1

  for (let i = 0; i < exchanges.length; i++) {
    if (!anomalous[i]) continue

    if (clusterMembers === null) {
      // Start first cluster
      clusterMembers = [i]
      lastMemberIdx = i
    } else {
      const gap = i - lastMemberIdx - 1
      const exI = exchanges[i] as DomainExchange
      const exLast = exchanges[lastMemberIdx] as DomainExchange
      const sameRegion = getRegion(exI.requestOid) === getRegion(exLast.requestOid)

      if (gap <= GAP_WINDOW || sameRegion) {
        // Extend current cluster
        clusterMembers.push(i)
        lastMemberIdx = i
      } else {
        // Close current cluster, start a new one
        incidents.push(buildCluster(clusterMembers, exchanges))
        clusterMembers = [i]
        lastMemberIdx = i
      }
    }
  }

  // Close final cluster if open
  if (clusterMembers !== null) {
    incidents.push(buildCluster(clusterMembers, exchanges))
  }

  // Sort by score descending
  incidents.sort((a, b) => b.score - a.score)

  return incidents
}
