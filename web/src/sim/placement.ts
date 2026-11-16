/**
 * 기관 N곳 순차 최적 배치 (탐욕). 오프라인(web/scripts/placement.mjs)에서 계산해 placement_greedy.json 으로 저장하고,
 * 웹은 그 결과만 읽는다 (단계마다 후보 약 4,000곳을 평가해 브라우저에서 돌리기엔 무겁다).
 * - 후보: 시뮬레이터 추천과 같은 위치 (행정동·리 기준점 신설, 지역센터면 기존 지역기관 승격까지). recommend.evaluateAll
 * - 단계마다: 1) 이중 취약에서 벗어나는 시군구 수  2) 동률이면 최근접 주행시간이 줄어드는 인구 합  최대인 후보 1곳
 * - 고른 후보를 시나리오에 넣고 simulate(고정 baseline 기준선, 판정 로직 그대로)로 다시 계산한 뒤 다음 단계
 * - 시나리오 좌표는 공유 링크(toQuery, 소수 5자리)와 같게 반올림해 두어, 링크로 열면 같은 결과가 나온다
 */
import { simulate, type Baseline, type Centers, type Facility, type SimRegion } from './model'
import { evaluateAll, type CandidateKind, type Effect } from './recommend'
import { EMPTY, applyScenario, type Scenario } from './scenario'

export interface PlacementStep {
  kind: CandidateKind
  label: string        // 기준점 이름(면·동) 또는 승격할 기관명
  code: string         // 후보가 놓이는 시군구
  lat: number
  lon: number
  hpid?: string        // 승격 대상 기관
  escaped: string[]    // 이 단계에서 이중 취약을 벗어난 시군구 (simulate 결과)
  popImproved: number  // 고를 때 쓴 동률 기준: 최근접 주행시간이 줄어드는 인구 합
  double: number       // 이 단계까지 반영한 이중 취약 수
}
export interface Placement { kind: 'G007' | 'G006'; base: number; steps: PlacementStep[] }
/** placement_greedy.json (web/scripts/placement.mjs) */
export interface PlacementData { plans: Record<'G007' | 'G006', Placement>; 시군구별: Record<'G007' | 'G006', Record<string, RegionBest>> }

const round5 = (v: number) => Number(v.toFixed(5))
export const countDouble = (r: Record<string, SimRegion>) => Object.values(r).filter((x) => x.등급 === '이중 취약').length

/** 앞의 k 단계를 담은 시나리오: 신설은 추가, 승격은 기존 기관의 등급만 지역센터로 (시뮬레이터 추천 적용과 같다) */
export function planScenario(steps: Pick<PlacementStep, 'kind' | 'lat' | 'lon' | 'code' | 'hpid'>[]): Scenario {
  return steps.reduce<Scenario>((s, st) => (st.kind === 'upgrade'
    ? { ...s, upgraded: [...(s.upgraded ?? []), st.hpid!] }
    : { ...s, added: [...s.added, { grade: st.kind, lat: st.lat, lon: st.lon, code: st.code }] }), EMPTY)
}

export function greedyPlacement(
  base: Facility[], centers: Centers, baseline: Baseline, elderly: Record<string, number>, kind: 'G007' | 'G006', n = 5,
): Placement {
  let current = simulate(base, centers, baseline)
  const start = countDouble(current)
  const steps: PlacementStep[] = []
  const used = new Set<string>()  // 같은 자리에 두 번 놓지 않게
  const key = (c: { lat: number; lon: number; hpid?: string }) => c.hpid ?? `${round5(c.lat)},${round5(c.lon)}`
  for (let i = 0; i < n; i++) {
    const facilities = applyScenario(base, planScenario(steps))
    let best = null
    for (const e of evaluateAll(facilities, centers, baseline, current, elderly, kind)) {
      if (used.has(key(e.candidate))) continue
      if (!best || e.escaped.length > best.escaped.length
        || (e.escaped.length === best.escaped.length && e.popImproved > best.popImproved)) best = e  // 완전 동률이면 앞 후보 (결정적)
    }
    if (!best || (!best.escaped.length && best.popImproved <= 0)) break // 더 나아지는 후보가 없음
    const c = best.candidate
    used.add(key(c))
    const step = { kind: c.kind, label: c.label, code: c.code, lat: round5(c.lat), lon: round5(c.lon), ...(c.hpid ? { hpid: c.hpid } : {}) }
    const next = simulate(applyScenario(base, planScenario([...steps, step])), centers, baseline)
    const escaped = Object.keys(next).filter((code) => current[code].등급 === '이중 취약' && next[code].등급 !== '이중 취약')
    steps.push({ ...step, escaped, popImproved: Math.round(best.popImproved), double: countDouble(next) })
    current = next
  }
  return { kind, base: start, steps }
}

/** 시군구별 최적 1곳: 그 시군구 안 후보 중 순차 배치와 같은 기준(이중 취약 감소 수 -> 주행시간이 줄어드는 인구)으로 최선.
 *  지역 보고서·AI 브리핑의 "이 시군구에 1곳을 두면" 근거. 벗어나는 시군구는 simulate 로 확인한 값 (기관 추가 없는 상태 기준) */
export interface RegionBest { kind: CandidateKind; label: string; lat: number; lon: number; hpid?: string; escaped: string[]; popImproved: number }

export function bestPerRegion(
  base: Facility[], centers: Centers, baseline: Baseline, elderly: Record<string, number>, kind: 'G007' | 'G006',
): Record<string, RegionBest> {
  const current = simulate(base, centers, baseline)
  const best = new Map<string, Effect>()
  for (const e of evaluateAll(base, centers, baseline, current, elderly, kind)) {
    const b = best.get(e.candidate.code)
    if (!b || e.escaped.length > b.escaped.length || (e.escaped.length === b.escaped.length && e.popImproved > b.popImproved)) best.set(e.candidate.code, e)
  }
  const out: Record<string, RegionBest> = {}
  for (const [code, e] of [...best].sort(([a], [b]) => a.localeCompare(b))) {
    if (!e.escaped.length && e.popImproved <= 0) continue // 이 시군구 안에는 나아지는 후보가 없음
    const c = e.candidate
    const step = { kind: c.kind, label: c.label, code, lat: round5(c.lat), lon: round5(c.lon), ...(c.hpid ? { hpid: c.hpid } : {}) }
    const next = simulate(applyScenario(base, planScenario([step])), centers, baseline)
    const escaped = Object.keys(next).filter((k) => current[k].등급 === '이중 취약' && next[k].등급 !== '이중 취약')
    const { code: _, ...rest } = step // eslint-disable-line @typescript-eslint/no-unused-vars
    out[code] = { ...rest, escaped, popImproved: Math.round(e.popImproved) }
  }
  return out
}
