import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import type { Region } from '../data'
import { ACCESS_KEYS, haversine, simulate, type Baseline, type Centers, type Facility } from './model'

const load = <T>(name: string): T => JSON.parse(readFileSync(new URL(`../../public/data/${name}`, import.meta.url), 'utf-8'))
const facilities = load<Facility[]>('facilities.json')
const centers = load<Centers>('centers.json')
const baseline = load<Baseline>('baseline.json')
const regions = load<Region[]>('sigungu_metrics.json')
const sim = simulate(facilities, centers, baseline)
const FIELD = { 최근접_응급의료기관_km: '최근접_응급의료기관_km', 최근접_권역지역센터_km: '최근접_권역지역센터_km', 반경30km_응급의료기관수: '반경30km_기관수' } as const

describe('수정 없는 상태 = Python 결과 (sigungu_metrics.json)', () => {
  it('입력 규모', () => {
    expect(facilities).toHaveLength(416)
    expect(Object.keys(centers)).toHaveLength(229)
    expect(regions).toHaveLength(229)
  })

  it('하버사인: 위도 0.1도 ≈ 11.12km (Python 테스트와 같은 값)', () => {
    expect(haversine(36.0, 128.0, 36.1, 128.0)).toBeCloseTo(11.12, 2)
  })

  for (const k of ACCESS_KEYS) {
    it(`${k}: 229곳 오차 0.01 이내`, () => {
      const bad = regions.filter((r) => Math.abs(sim[r.코드].metrics[k] - r[FIELD[k]]) >= 0.01)
      expect(bad.map((r) => [r.시군구, sim[r.코드].metrics[k], r[FIELD[k]]])).toEqual([])
    })
  }

  it('접근성점수: baseline 전체 정밀도 점수와 일치 (1e-9)', () => {
    const bad = baseline.코드.filter((c, i) => Math.abs(sim[c].접근성점수 - baseline.접근성점수[i]) > 1e-9)
    expect(bad).toEqual([])
  })

  it('접근성점수·복지점수: sigungu_metrics.json(소수 4자리)과 일치', () => {
    const bad = regions.filter((r) => Math.abs(sim[r.코드].접근성점수 - r.접근성점수) > 1e-3 || Math.abs(sim[r.코드].복지점수 - r.복지점수) > 1e-3)
    expect(bad.map((r) => r.시군구)).toEqual([])
  })

  it('등급: 229곳 모두 일치 (이중 30 / 준 29)', () => {
    const bad = regions.filter((r) => sim[r.코드].등급 !== r.등급)
    expect(bad.map((r) => [r.시군구, sim[r.코드].등급, r.등급])).toEqual([])
    const count = (g: string) => Object.values(sim).filter((s) => s.등급 === g).length
    expect([count('이중 취약'), count('준 이중 취약')]).toEqual([30, 29])
  })
})

describe('시뮬레이션 동작', () => {
  it('기관을 하나 추가하면 그 주변만 좋아지고, 기준선이 고정이라 다른 지역 등급은 나빠지지 않는다', () => {
    const 영덕 = centers['47770'][0]
    const added: Facility = { hpid: 'SIM-1', 기관명: '가상', 등급: 'G006', 위도: 영덕.lat, 경도: 영덕.lon, 시군구코드: '47770' }
    const after = simulate([...facilities, added], centers, baseline)
    expect(after['47770'].metrics.최근접_응급의료기관_km).toBe(0)
    expect(after['47770'].접근성점수).toBeLessThan(sim['47770'].접근성점수)
    const rank = { '이중 취약': 2, '준 이중 취약': 1, '': 0 }
    const worse = Object.keys(sim).filter((c) => rank[after[c].등급] > rank[sim[c].등급])
    expect(worse).toEqual([])
  })

  it('기관을 제거하면 거리가 줄지 않는다', () => {
    const after = simulate(facilities.slice(1), centers, baseline)
    for (const c of Object.keys(sim)) expect(after[c].metrics.최근접_응급의료기관_km).toBeGreaterThanOrEqual(sim[c].metrics.최근접_응급의료기관_km)
  })
})
