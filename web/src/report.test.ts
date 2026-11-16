import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { bestSentence, planStep } from './report'
import { simulate, type Baseline, type Centers, type Facility } from './sim/model'
import { planScenario, type PlacementData } from './sim/placement'
import { applyScenario } from './sim/scenario'

const load = <T>(name: string): T => JSON.parse(readFileSync(new URL(`../public/data/${name}`, import.meta.url), 'utf-8'))
const data = load<PlacementData>('placement_greedy.json')

describe('지역 보고서 (#70)', () => {
  const names: Record<string, string> = { A: '가군', B: '나군' }
  it('배치 효과 문장: 벗어나는 시군구가 있을 때, 없을 때, 후보가 없을 때, 승격', () => {
    expect(bestSentence({ kind: 'G006', label: '갑면', lat: 0, lon: 0, escaped: ['A', 'B'], popImproved: 12345 }, 'G006', (c) => names[c]))
      .toBe('갑면에 지역응급의료센터 1곳을 두면 가군, 나군 2곳이 이중 취약에서 벗어나고, 주변 시군구를 포함해 12,345명의 최근접 응급의료기관·센터 주행시간이 줄어든다.')
    expect(bestSentence({ kind: 'G007', label: '을면', lat: 0, lon: 0, escaped: [], popImproved: 10 }, 'G007', (c) => c))
      .toContain('이중 취약에서 벗어나는 시군구는 없지만')
    expect(bestSentence(undefined, 'G006', (c) => c)).toBe('시군구 안에 지역응급의료센터 1곳을 두어도 나아지는 후보가 없다.')
    expect(bestSentence({ kind: 'upgrade', label: '병원', lat: 0, lon: 0, hpid: 'X', escaped: [], popImproved: 1 }, 'G006', (c) => c)).toMatch(/^병원을\(를\) 지역응급의료센터로 승격하면/)
  })

  it('순차 배치에서 벗어나는 단계', () => {
    const first = data.plans.G006.steps[0].escaped[0]
    expect(planStep(data.plans.G006, first)).toBe(1)
    expect(planStep(data.plans.G006, '00000')).toBeNull()
    expect(planStep(undefined, first)).toBeNull()
  })

  it('시군구별 1곳: 후보가 그 시군구 안에 있고, 적어 둔 효과가 다시 계산한 값과 같다 (표본 6곳)', () => {
    const facilities = load<Facility[]>('facilities.json'), centers = load<Centers>('centers.json'), baseline = load<Baseline>('baseline.json')
    const base = simulate(facilities, centers, baseline)
    for (const kind of ['G006', 'G007'] as const) {
      const entries = Object.entries(data.시군구별[kind])
      expect(entries.length).toBeGreaterThan(200)
      const sample = [...entries.filter(([, b]) => b.escaped.length).slice(0, 2), entries[0]]
      for (const [code, b] of sample) {
        const next = simulate(applyScenario(facilities, planScenario([{ ...b, code }])), centers, baseline)
        const escaped = Object.keys(next).filter((k) => base[k].등급 === '이중 취약' && next[k].등급 !== '이중 취약')
        expect(escaped).toEqual(b.escaped)
        if (b.kind !== 'upgrade') expect(centers[code].some((p) => Math.abs(p.lat - b.lat) < 1e-4 && Math.abs(p.lon - b.lon) < 1e-4)).toBe(true)
      }
    }
  }, 60_000)
})
