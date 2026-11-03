/**
 * 추천 위치: 기관 1곳을 더한다면 어디가 가장 효과적인가
 * 후보: 기준점 259개 위치에 지역기관(G007) 또는 지역센터(G006) 신설 + 기존 지역기관의 지역센터 승격
 * 순위: 1) 이중 취약에서 벗어나는 시군구 수  2) 65세 이상 인구 가중 최근접 거리 감소량(응급의료기관 + 센터, 인·km)
 * 기관 하나를 더하면 기준점별 최솟값·개수만 바뀌므로, 현재 기준점 지표에서 증분으로 계산한다
 */
import {
  aggregate, classify, haversine, makeScorer, pointMetrics,
  type AccessMetrics, type Baseline, type Centers, type Facility, type SimGrade, type SimRegion,
} from './model'

export type CandidateKind = 'G007' | 'G006' | 'upgrade'
export interface Candidate {
  kind: CandidateKind
  lat: number
  lon: number
  code: string            // 후보가 놓이는 시군구
  label: string           // 기준점 이름 또는 승격할 기관명
  hpid?: string           // 승격이면 대상 기관
}
export interface Effect {
  candidate: Candidate
  escaped: string[]       // 이중 취약에서 벗어나는 시군구 코드
  newGrades: Record<string, SimGrade>
  elderlyKm: number       // 65세 이상 인구 × 거리 감소(km) 합
  nearImproved: { elderly: number; kmAvg: number }  // 최근접 응급의료기관 거리가 줄어든 시군구의 65세 이상 인구, 평균 감소
  ctrImproved: { elderly: number; kmAvg: number }   // 최근접 센터 거리
}

/** reachE/reachC: 이 거리 밖의 후보는 이 기준점에 영향이 없음 (최근접 거리·반경 중 큰 값) */
interface PointState { code: string; idx: number; lat: number; lon: number; m: AccessMetrics; reachE: number; reachC: number }
// 거르기용 하한: 실제 거리는 항상 이 값으로 잰 위도·경도 차이 거리보다 길다 (경도는 최북단 38.7° 기준으로 가장 짧게)
const KM_PER_LAT = 111.19
const KM_PER_LON = 111.19 * Math.cos((38.7 * Math.PI) / 180)

export function recommend(
  facilities: Facility[], centers: Centers, baseline: Baseline, current: Record<string, SimRegion>,
  elderly: Record<string, number>, kind: 'G007' | 'G006', top = 5,
): Effect[] {
  const score = makeScorer(baseline)
  const welfare = Object.fromEntries(baseline.코드.map((c, i) => [c, baseline.복지점수[i]]))
  const points: PointState[] = Object.entries(centers).flatMap(([code, ps]) =>
    ps.map((p, idx) => {
      const m = pointMetrics(p.lat, p.lon, facilities, baseline.반경km)
      return { code, idx, lat: p.lat, lon: p.lon, m, reachE: Math.max(m.최근접_응급의료기관_km, baseline.반경km), reachC: m.최근접_권역지역센터_km }
    }))
  const byCode = new Map<string, PointState[]>()
  for (const p of points) byCode.set(p.code, [...(byCode.get(p.code) ?? []), p])

  const candidates: Candidate[] = points.map((p) => ({
    kind, lat: p.lat, lon: p.lon, code: p.code, label: centers[p.code][p.idx].지점.split(' ').at(-1)!, // '경상남도 함안군 대산면' -> '대산면'
  }))
  if (kind === 'G006') {
    for (const f of facilities) {
      if (f.등급 === 'G007' && f.시군구코드) candidates.push({ kind: 'upgrade', lat: f.위도, lon: f.경도, code: f.시군구코드, label: f.기관명, hpid: f.hpid })
    }
  }

  const effects = candidates.map((c) => evaluate(c, points, byCode, centers, baseline, current, welfare, elderly, score))
    .filter((e) => e.escaped.length || e.elderlyKm > 0)
    .sort((a, b) => b.escaped.length - a.escaped.length || b.elderlyKm - a.elderlyKm)
  // 같은 시군구의 비슷한 후보(군청 신설, 그 군 병원 승격)가 목록을 채우지 않도록 시군구당 최고 1개
  const seen = new Set<string>()
  return effects.filter((e) => !seen.has(e.candidate.code) && seen.add(e.candidate.code)).slice(0, top)
}

function evaluate(
  c: Candidate, points: PointState[], byCode: Map<string, PointState[]>, centers: Centers, baseline: Baseline,
  current: Record<string, SimRegion>, welfare: Record<string, number>, elderly: Record<string, number>,
  score: (m: AccessMetrics) => number,
): Effect {
  const addsEmergency = c.kind !== 'upgrade'          // 승격은 이미 응급의료기관이라 최근접·반경 개수는 그대로
  const addsCenter = c.kind !== 'G007'
  const changed = new Map<string, Map<number, AccessMetrics>>()
  for (const p of points) {
    // 빠른 거르기: 위경도 차이로 잰 거리(실제 거리의 하한)가 영향 범위보다 멀면 하버사인 계산 생략 (여유 5%)
    const reach = Math.max(addsEmergency ? p.reachE : 0, addsCenter ? p.reachC : 0) * 1.05
    if (Math.abs(p.lat - c.lat) * KM_PER_LAT > reach || Math.abs(p.lon - c.lon) * KM_PER_LON > reach) continue
    const d = haversine(p.lat, p.lon, c.lat, c.lon)
    const near = addsEmergency && d < p.m.최근접_응급의료기관_km
    const ctr = addsCenter && d < p.m.최근접_권역지역센터_km
    const inR = addsEmergency && d <= baseline.반경km
    if (!near && !ctr && !inR) continue
    const m = { ...p.m }
    if (near) m.최근접_응급의료기관_km = d
    if (ctr) m.최근접_권역지역센터_km = d
    if (inR) m.반경30km_응급의료기관수 += 1
    if (!changed.has(p.code)) changed.set(p.code, new Map())
    changed.get(p.code)!.set(p.idx, m)
  }

  const escaped: string[] = []
  const newGrades: Record<string, SimGrade> = {}
  let elderlyKm = 0
  const near = { elderly: 0, km: 0 }, ctr = { elderly: 0, km: 0 }
  for (const [code, upd] of changed) {
    const ps = byCode.get(code)!
    const m = aggregate(centers[code], ps.map((p) => upd.get(p.idx) ?? p.m))
    const before = current[code]
    const grade = classify(score(m), welfare[code], baseline.기준선)
    newGrades[code] = grade
    if (before.등급 === '이중 취약' && grade !== '이중 취약') escaped.push(code)
    const e = elderly[code] ?? 0
    const dNear = before.metrics.최근접_응급의료기관_km - m.최근접_응급의료기관_km
    const dCtr = before.metrics.최근접_권역지역센터_km - m.최근접_권역지역센터_km
    if (dNear > 0) { near.elderly += e; near.km += e * dNear }
    if (dCtr > 0) { ctr.elderly += e; ctr.km += e * dCtr }
    elderlyKm += e * (Math.max(dNear, 0) + Math.max(dCtr, 0))
  }
  return {
    candidate: c, escaped, newGrades, elderlyKm,
    nearImproved: { elderly: near.elderly, kmAvg: near.elderly ? near.km / near.elderly : 0 },
    ctrImproved: { elderly: ctr.elderly, kmAvg: ctr.elderly ? ctr.km / ctr.elderly : 0 },
  }
}
