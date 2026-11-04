/**
 * 배치 시뮬레이터 계산 로직 (순수 함수). Python과 같은 정의:
 * - 주행시간: src/accessibility.py drive_minutes 와 같은 규칙. 기준점마다 OSRM 실주행시간(drive, 초)이 있는 기관은 그 값,
 *   없는 기관(가까운 10곳 밖, 도로로 닿지 않음, 시뮬레이터로 추가한 가상 기관)은 직선거리(하버사인) × 시군구 우회계수(분/직선km)
 * - 기준점별 지표를 인구로 가중평균 후 소수 3자리 반올림
 * - 점수: notebooks/sigungu_clustering.ipynb 의 백분위 순위 평균. 단 시뮬레이션에서는 baseline 분포에 대한 백분위로 환산
 * - 등급: 기준선(baseline 상위 25%·40%) 고정
 */
export type FacilityGrade = 'G001' | 'G006' | 'G007' // 권역센터 / 지역센터 / 지역기관

export interface Facility {
  hpid: string; 기관명: string; 등급: FacilityGrade; 위도: number; 경도: number; 시군구코드: string | null
  주소?: string; 응급실전화?: string; 대표전화?: string  // 시뮬레이터로 추가한 가상 기관에는 없음
}
export interface CenterPoint { lat: number; lon: number; weight: number; 지점: string; drive?: Record<string, number> }
export type Centers = Record<string, CenterPoint[]>

export const ACCESS_KEYS = ['최근접_응급의료기관_분', '최근접_권역지역센터_분', '30분내_응급의료기관수'] as const
export type AccessKey = typeof ACCESS_KEYS[number]
export type AccessMetrics = Record<AccessKey, number>

export interface Baseline {
  지표: Record<AccessKey, number[]>
  방향: Record<AccessKey, 1 | -1>
  기준선: { 상위25: { 접근성: number; 복지: number }; 상위40: { 접근성: number; 복지: number } }
  기준분: number
  우회계수: Record<string, number>   // 시군구별 분/직선km
  코드: string[]
  접근성점수: number[]
  복지점수: number[]
}

export type SimGrade = '이중 취약' | '준 이중 취약' | ''

const R = 6371.0088
const RAD = Math.PI / 180
const CENTER_GRADES: FacilityGrade[] = ['G001', 'G006']

export function haversine(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const p1 = lat1 * RAD, p2 = lat2 * RAD
  const a = Math.sin((p2 - p1) / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(((lon2 - lon1) * RAD) / 2) ** 2
  return 2 * R * Math.asin(Math.sqrt(a))
}

const round3 = (v: number) => Math.round(v * 1000) / 1000

/** 기준점 -> 기관 주행시간(분). 실주행시간이 없으면 직선거리 × 우회계수 (approx = true) */
export function driveMinutes(p: CenterPoint, f: Facility, factor: number): { min: number; approx: boolean } {
  const sec = p.drive?.[f.hpid]
  return sec === undefined ? { min: haversine(p.lat, p.lon, f.위도, f.경도) * factor, approx: true } : { min: sec / 60, approx: false }
}

/** 기준점 한 곳의 지표. index: 기관 hpid -> facilities 위치 (여러 기준점에 같은 목록을 쓸 때 한 번 만들어 넘김) */
export function pointMetrics(p: CenterPoint, facilities: Facility[], factor: number, minutes: number,
  index = new Map(facilities.map((f, i) => [f.hpid, i]))): AccessMetrics {
  // driveMinutes 와 같은 식: 모두 직선거리 × 우회계수로 채우고, 실주행시간이 있는 기관(최대 20곳)만 덮어쓴다
  const t = facilities.map((f) => haversine(p.lat, p.lon, f.위도, f.경도) * factor)
  for (const h in p.drive) {
    const i = index.get(h)
    if (i !== undefined) t[i] = p.drive[h] / 60
  }
  let near = Infinity, ctr = Infinity, n = 0
  facilities.forEach((f, i) => {
    if (t[i] < near) near = t[i]
    if (t[i] < ctr && CENTER_GRADES.includes(f.등급)) ctr = t[i]
    if (t[i] <= minutes) n++
  })
  return { 최근접_응급의료기관_분: near, 최근접_권역지역센터_분: ctr, '30분내_응급의료기관수': n }
}

export interface NearFacility { f: Facility; min: number; km: number; approx: boolean }
/** 시군구 기준점(인구 가중치)에서 기관까지 주행시간의 가중평균이 짧은 순 n곳. approx: 근사값이 섞임 */
export function nearestFacilities(points: CenterPoint[], facilities: Facility[], factor: number, n = 3): NearFacility[] {
  const wsum = points.reduce((s, p) => s + p.weight, 0)
  return facilities
    .map((f) => {
      let min = 0, km = 0, approx = false
      for (const p of points) {
        const t = driveMinutes(p, f, factor)
        min += t.min * p.weight
        km += haversine(p.lat, p.lon, f.위도, f.경도) * p.weight
        approx ||= t.approx
      }
      return { f, min: min / wsum, km: km / wsum, approx }
    })
    .sort((a, b) => a.min - b.min)
    .slice(0, n)
}

/** 기준점 지표를 가중평균하고 소수 3자리로 반올림 (Python table.round(3)와 같게) */
export function aggregate(points: CenterPoint[], perPoint: AccessMetrics[]): AccessMetrics {
  const wsum = points.reduce((s, p) => s + p.weight, 0)
  const out = {} as AccessMetrics
  for (const k of ACCESS_KEYS) out[k] = round3(perPoint.reduce((s, m, i) => s + m[k] * points[i].weight, 0) / wsum)
  return out
}

/** 시군구별 접근성 지표 3개 */
export function computeAccess(facilities: Facility[], centers: Centers, baseline: Pick<Baseline, '우회계수' | '기준분'>): Record<string, AccessMetrics> {
  const out: Record<string, AccessMetrics> = {}
  const index = new Map(facilities.map((f, i) => [f.hpid, i]))
  for (const [code, points] of Object.entries(centers)) {
    out[code] = aggregate(points, points.map((p) => pointMetrics(p, facilities, baseline.우회계수[code], baseline.기준분, index)))
  }
  return out
}

/** baseline 분포 기준 백분위 (pandas rank(pct=True), 동률은 평균 순위). dir=-1이면 작을수록 취약 */
export function percentile(values: number[], v: number, dir: 1 | -1): number {
  const eps = 1e-9
  let less = 0, equal = 0
  for (const b of values) {
    const diff = dir * (b - v)
    if (diff < -eps) less++
    else if (diff <= eps) equal++
  }
  return ((less + (equal + 1) / 2) / values.length) * 100
}

/** 접근성 취약 점수: 3개 지표 백분위 평균 (0~100, 클수록 취약) */
export function scoreAgainstBaseline(m: AccessMetrics, baseline: Baseline): number {
  return ACCESS_KEYS.reduce((s, k) => s + percentile(baseline.지표[k], m[k], baseline.방향[k]), 0) / ACCESS_KEYS.length
}

/** scoreAgainstBaseline 과 같은 값을 이진 탐색으로 계산 (추천 위치처럼 수십만 번 부를 때) */
export function makeScorer(baseline: Baseline): (m: AccessMetrics) => number {
  const eps = 1e-9
  const sorted = ACCESS_KEYS.map((k) => baseline.지표[k].map((v) => v * baseline.방향[k]).sort((a, b) => a - b))
  const lowerBound = (arr: number[], x: number) => { // arr[i] >= x 인 첫 위치
    let lo = 0, hi = arr.length
    while (lo < hi) { const mid = (lo + hi) >> 1; if (arr[mid] < x) lo = mid + 1; else hi = mid }
    return lo
  }
  return (m) => ACCESS_KEYS.reduce((s, k, i) => {
    const v = m[k] * baseline.방향[k], arr = sorted[i]
    const less = lowerBound(arr, v - eps), equal = lowerBound(arr, v + eps + 1e-12) - less
    return s + ((less + (equal + 1) / 2) / arr.length) * 100
  }, 0) / ACCESS_KEYS.length
}

/** 등급: 두 점수 모두 상위 25% = 이중 취약, 한쪽 25% + 다른 쪽 40% = 준 이중 취약 (기준선 고정) */
export function classify(access: number, welfare: number, cuts: Baseline['기준선']): SimGrade {
  const aTop = access >= cuts.상위25.접근성, wTop = welfare >= cuts.상위25.복지
  if (aTop && wTop) return '이중 취약'
  if ((aTop && welfare >= cuts.상위40.복지) || (wTop && access >= cuts.상위40.접근성)) return '준 이중 취약'
  return ''
}

export interface SimRegion { code: string; metrics: AccessMetrics; 접근성점수: number; 복지점수: number; 등급: SimGrade }

/** 기관 목록 -> 시군구별 지표·점수·등급 */
export function simulate(facilities: Facility[], centers: Centers, baseline: Baseline): Record<string, SimRegion> {
  const metrics = computeAccess(facilities, centers, baseline)
  const out: Record<string, SimRegion> = {}
  baseline.코드.forEach((code, i) => {
    const m = metrics[code]
    const acc = scoreAgainstBaseline(m, baseline)
    const wel = baseline.복지점수[i]
    out[code] = { code, metrics: m, 접근성점수: acc, 복지점수: wel, 등급: classify(acc, wel, baseline.기준선) }
  })
  return out
}
