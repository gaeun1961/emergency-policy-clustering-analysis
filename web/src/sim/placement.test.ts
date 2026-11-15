import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { simulate, type Baseline, type Centers, type Facility } from './model'
import { countDouble, planScenario, type Placement } from './placement'
import { evaluateAll } from './recommend'
import { applyScenario, fromQuery, toQuery } from './scenario'

const load = <T>(name: string): T => JSON.parse(readFileSync(new URL(`../../public/data/${name}`, import.meta.url), 'utf-8'))
const facilities = load<Facility[]>('facilities.json')
const centers = load<Centers>('centers.json')
const baseline = load<Baseline>('baseline.json')
const elderly = Object.fromEntries(load<{ 코드: string; '65세이상인구': number }[]>('sigungu_metrics.json').map((r) => [r.코드, r['65세이상인구']]))
const { plans, N } = load<{ plans: Record<'G007' | 'G006', Placement>; N: number }>('placement_greedy.json')
const base = simulate(facilities, centers, baseline)

describe('순차 배치 추천 (placement_greedy.json)', () => {
  it.each(['G007', 'G006'] as const)('%s: 이중 취약 수가 단계마다 줄거나 같고, 줄어든 만큼이 벗어난 시군구 수다', (kind) => {
    const p = plans[kind]
    expect(p.base).toBe(countDouble(base))
    expect(p.steps.length).toBeGreaterThan(0)
    expect(p.steps.length).toBeLessThanOrEqual(N)
    p.steps.forEach((s, i) => {
      const prev = i ? p.steps[i - 1].double : p.base
      expect(s.double).toBeLessThanOrEqual(prev)
      expect(prev - s.double).toBe(s.escaped.length)
    })
    // 같은 자리에 두 번 놓지 않는다
    expect(new Set(p.steps.map((s) => s.hpid ?? `${s.lat},${s.lon}`)).size).toBe(p.steps.length)
  })

  it.each(['G007', 'G006'] as const)('%s: 단계별 공유 링크(?sim=1&add=…)로 열면 같은 이중 취약 수가 나온다', (kind) => {
    const p = plans[kind]
    for (let k = 1; k <= p.steps.length; k++) {
      const q = toQuery(true, planScenario(p.steps.slice(0, k)))
      const { on, scenario } = fromQuery(q)
      expect(on).toBe(true)
      expect(countDouble(simulate(applyScenario(facilities, scenario), centers, baseline))).toBe(p.steps[k - 1].double)
    }
  }, 120_000)

  it('첫 단계는 전체 후보 중 이중 취약을 가장 많이 줄이고, 동률이면 주행시간이 줄어드는 인구가 가장 많은 곳이다 (지역센터)', () => {
    const effects = evaluateAll(facilities, centers, baseline, base, elderly, 'G006')
    const most = Math.max(...effects.map((e) => e.escaped.length))
    const pop = Math.max(...effects.filter((e) => e.escaped.length === most).map((e) => e.popImproved))
    const first = plans.G006.steps[0]
    expect(first.escaped.length).toBe(most)
    expect(first.popImproved).toBe(Math.round(pop))
  }, 60_000)

  it('승격 단계는 그 자리에 지역센터 추가 + 기존 기관 제거로 바뀐다', () => {
    const s = planScenario([{ kind: 'G007', lat: 35, lon: 127, code: '1' }, { kind: 'upgrade', lat: 36, lon: 128, code: '2', hpid: 'A1' }])
    expect(s.added.map((a) => a.grade)).toEqual(['G007', 'G006'])
    expect(s.removed).toEqual(['A1'])
  })
})
