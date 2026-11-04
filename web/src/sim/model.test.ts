import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import type { Region } from '../data'
import { ACCESS_KEYS, RAW_KEYS, driveMinutes, haversine, makeScorer, nearestFacilities, scoreAgainstBaseline, simulate, type Baseline, type Centers, type Facility } from './model'
import { recommend } from './recommend'
import type { SigunguGeo } from '../data'
import { locateSigungu } from './geo'
import { applyScenario, fromQuery, keepOnLand, toQuery, type Scenario } from './scenario'

const load = <T>(name: string): T => JSON.parse(readFileSync(new URL(`../../public/data/${name}`, import.meta.url), 'utf-8'))
const facilities = load<Facility[]>('facilities.json')
const centers = load<Centers>('centers.json')
const baseline = load<Baseline>('baseline.json')
const regions = load<Region[]>('sigungu_metrics.json')
const sim = simulate(facilities, centers, baseline)
const FIELD = { 최근접_응급의료기관_분: '최근접_응급의료기관_분', 최근접_권역지역센터_분: '최근접_권역지역센터_분', '30분내_응급의료기관수': '30분내_기관수' } as const

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

  it('등급: 229곳 모두 일치 (이중·준 이중 개수도 Python과 같음)', () => {
    const bad = regions.filter((r) => sim[r.코드].등급 !== r.등급)
    expect(bad.map((r) => [r.시군구, sim[r.코드].등급, r.등급])).toEqual([])
    const count = (g: string) => Object.values(sim).filter((s) => s.등급 === g).length
    const py = (g: string) => regions.filter((r) => r.등급 === g).length
    expect([count('이중 취약'), count('준 이중 취약')]).toEqual([py('이중 취약'), py('준 이중 취약')])
  })
})

describe('시뮬레이션 동작', () => {
  it('기관을 하나 추가하면 그 주변만 좋아지고, 기준선이 고정이라 다른 지역 등급은 나빠지지 않는다', () => {
    // 영덕에서 인구가 가장 많은 행정동 기준점에 지역센터 추가
    const 영덕 = [...centers['47770']].sort((a, b) => b.weight - a.weight)[0]
    const added: Facility = { hpid: 'SIM-1', 기관명: '가상', 등급: 'G006', 위도: 영덕.lat, 경도: 영덕.lon, 시군구코드: '47770' }
    const after = simulate([...facilities, added], centers, baseline)
    expect(after['47770'].metrics.최근접_응급의료기관_분).toBeLessThan(sim['47770'].metrics.최근접_응급의료기관_분)
    expect(after['47770'].접근성점수).toBeLessThan(sim['47770'].접근성점수)
    const rank = { '이중 취약': 2, '준 이중 취약': 1, '': 0 }
    const worse = Object.keys(sim).filter((c) => rank[after[c].등급] > rank[sim[c].등급])
    expect(worse).toEqual([])
  })

  it('기관을 제거하면 주행시간이 줄지 않는다', () => {
    const after = simulate(facilities.slice(1), centers, baseline)
    for (const c of Object.keys(sim)) expect(after[c].metrics.최근접_응급의료기관_분).toBeGreaterThanOrEqual(sim[c].metrics.최근접_응급의료기관_분)
  })

  it('makeScorer(이진 탐색) = scoreAgainstBaseline(선형)', () => {
    const score = makeScorer(baseline)
    const samples = Object.values(sim).flatMap((s) => [s.metrics, {
      최근접_응급의료기관_분: s.metrics.최근접_응급의료기관_분 * 0.7, 최근접_권역지역센터_분: s.metrics.최근접_권역지역센터_분 + 3.3,
      '30분내_응급의료기관수': s.metrics['30분내_응급의료기관수'] + 1,
    }])
    for (const m of samples) expect(score(m)).toBeCloseTo(scoreAgainstBaseline(m, baseline), 9)
  })
})

describe('시나리오 URL', () => {
  it('추가·제거가 쿼리로 왕복된다', () => {
    const s = { added: [{ grade: 'G006' as const, lat: 36.41234, lon: 129.36543 }, { grade: 'G007' as const, lat: 37.1, lon: 128.2 }], removed: ['A1', 'B2'] }
    const q = toQuery(true, s)
    expect(q).toBe('?sim=1&add=G006:36.41234,129.36543;G007:37.10000,128.20000&rm=A1,B2')
    expect(fromQuery(q)).toEqual({ on: true, scenario: s })
    expect(toQuery(false, s)).toBe('')
    expect(fromQuery('?sim=1&add=X:1,2;G007:abc').scenario.added).toEqual([])
  })

  it('applyScenario: 제거한 기관은 빠지고 추가한 기관이 붙는다', () => {
    const out = applyScenario(facilities, { added: [{ grade: 'G007', lat: 36, lon: 128 }], removed: [facilities[0].hpid] })
    expect(out).toHaveLength(facilities.length)
    expect(out.some((f) => f.hpid === facilities[0].hpid)).toBe(false)
    expect(out.at(-1)).toMatchObject({ hpid: 'SIM-1', 등급: 'G007', 위도: 36, 경도: 128 })
  })
})

describe('추천 위치', () => {
  const elderly = Object.fromEntries(regions.map((r) => [r.코드, r['65세이상인구']]))
  for (const kind of ['G007', 'G006'] as const) {
    it(`${kind}: 증분 계산 결과 = 그 시나리오를 전체 재계산한 결과`, () => {
      const top = recommend(facilities, centers, baseline, sim, elderly, kind)
      expect(top.length).toBe(5)
      for (const e of top) {
        const c = e.candidate
        const scenario: Scenario = c.kind === 'upgrade'
          ? { added: [{ grade: 'G006', lat: c.lat, lon: c.lon }], removed: [c.hpid!] }
          : { added: [{ grade: c.kind, lat: c.lat, lon: c.lon }], removed: [] }
        const full = simulate(applyScenario(facilities, scenario), centers, baseline)
        const escaped = Object.keys(sim).filter((k) => sim[k].등급 === '이중 취약' && full[k].등급 !== '이중 취약')
        expect(escaped.sort()).toEqual([...e.escaped].sort())
        for (const k of Object.keys(sim)) expect(full[k].등급).toBe(e.newGrades[k] ?? sim[k].등급)
      }
    })
  }
})

describe('시군구 경계 판정 (바다 클릭 방지)', () => {
  const sigungu = load<SigunguGeo>('sigungu.geojson')
  const at = (code: string, name: string) => centers[code].find((p) => p.지점 === name) ?? centers[code][0]
  it('바다 좌표는 null', () => {
    expect(locateSigungu(sigungu, 36.5, 130.3)).toBeNull()  // 동해
    expect(locateSigungu(sigungu, 35.5, 125.0)).toBeNull()  // 서해
    expect(locateSigungu(sigungu, 33.0, 127.5)).toBeNull()  // 제주 남쪽 바다
    expect(locateSigungu(sigungu, 34.9, 128.95)).toBeNull() // 남해 (부산·거제 사이 바다)
  })
  it('섬 좌표는 그 섬의 시군구: 울릉도·백령도·흑산도', () => {
    const 울릉 = at('47940', '울릉군청'), 백령 = at('28720', '백령면사무소'), 흑산 = at('46910', '흑산면사무소')
    expect(locateSigungu(sigungu, 울릉.lat, 울릉.lon)).toBe('47940')
    expect(locateSigungu(sigungu, 백령.lat, 백령.lon)).toBe('28720')
    expect(locateSigungu(sigungu, 흑산.lat, 흑산.lon)).toBe('46910')
  })
  it('육지 좌표는 해당 시군구 (영덕군청, 종로구청)', () => {
    expect(locateSigungu(sigungu, centers['47770'][0].lat, centers['47770'][0].lon)).toBe('47770')
    expect(locateSigungu(sigungu, centers['11110'][0].lat, centers['11110'][0].lon)).toBe('11110')
  })
  it('keepOnLand: 공유 링크의 바다 좌표는 빼고, 남은 기관에 시군구 코드를 붙인다', () => {
    const s = fromQuery('?sim=1&add=G006:34.57391,126.59964;G007:36.50000,130.30000').scenario
    const { scenario, dropped } = keepOnLand(s, (lat, lon) => locateSigungu(sigungu, lat, lon))
    expect(dropped).toBe(1)
    expect(scenario.added).toEqual([{ grade: 'G006', lat: 34.57391, lon: 126.59964, code: '46820' }])
    expect(applyScenario(facilities, scenario).at(-1)?.시군구코드).toBe('46820')
  })
})

describe('가까운 응급의료기관 (지역 상세)', () => {
  it('기관마다 이름·주소·전화가 있다', () => {
    expect(facilities.filter((f) => !f.기관명 || !f.주소 || !f.응급실전화)).toEqual([])
  })

  it('주행시간 오름차순 3곳, 1위 시간 ≥ 최근접 응급의료기관 지표(점별 최소의 평균)', () => {
    for (const r of regions) {
      const near = nearestFacilities(centers[r.코드], facilities, r.우회계수, 3, baseline.근사상한분)
      expect(near).toHaveLength(3)
      expect(near[0].min <= near[1].min && near[1].min <= near[2].min).toBe(true)
      expect(near[0].min).toBeGreaterThanOrEqual(r.최근접_응급의료기관_분 - 0.001)
    }
  })

  it('기준점이 1곳뿐이면 1위 시간 = 최근접 시간', () => {
    const c = centers[regions[0].코드][0]
    const [top] = nearestFacilities([c], facilities, regions[0].우회계수, 1, baseline.근사상한분)
    expect(top.min).toBeCloseTo(Math.min(...facilities.map((f) => driveMinutes(c, f, regions[0].우회계수, baseline.근사상한분).min)), 9)
  })
})

describe('근사값 상한', () => {
  for (const k of RAW_KEYS) {
    it(`${k}: 229곳 Python 원값과 오차 0.01 이내`, () => {
      const bad = regions.filter((r) => Math.abs(sim[r.코드].metrics[k]! - r[k]) >= 0.01)
      expect(bad.map((r) => [r.시군구, sim[r.코드].metrics[k], r[k]])).toEqual([])
    })
  }

  it('상한에 걸린 시군구는 지표 < 원값, 울릉 센터는 상한 그대로', () => {
    const 울릉 = regions.find((r) => r.코드 === '47940')!
    expect(울릉.최근접_권역지역센터_분).toBeCloseTo(baseline.근사상한분, 3)
    expect(울릉.최근접_권역지역센터_분_원값).toBeGreaterThan(300)
    for (const r of regions) expect(r.최근접_권역지역센터_분).toBeLessThanOrEqual(r.최근접_권역지역센터_분_원값 + 1e-3)
  })

  it('가상 기관 근사값도 상한에서 잘린다', () => {
    const p = centers['47940'][0]
    const far: Facility = { ...facilities[0], hpid: 'SIM-1', 위도: 37.5, 경도: 126.9 }
    expect(driveMinutes(p, far, 2.4, baseline.근사상한분)).toMatchObject({ min: baseline.근사상한분, approx: true, capped: true })
  })
})

describe('주행시간 (OSRM)', () => {
  it('우회계수: baseline과 sigungu_metrics가 같은 값', () => {
    expect(regions.filter((r) => baseline.우회계수[r.코드] !== r.우회계수).map((r) => r.시군구)).toEqual([])
  })

  it('실주행시간이 있으면 그 값, 없으면(가상 기관) 직선거리 × 우회계수 근사', () => {
    const p = centers['47770'][0]
    const [hpid, sec] = Object.entries(p.drive!)[0]
    const f = facilities.find((x) => x.hpid === hpid)!
    expect(driveMinutes(p, f, 1.5)).toEqual({ min: sec / 60, approx: false, capped: false })
    const v: Facility = { ...f, hpid: 'SIM-1' }
    expect(driveMinutes(p, v, 1.5)).toEqual({ min: haversine(p.lat, p.lon, f.위도, f.경도) * 1.5, approx: true, capped: false })
  })

  it('주행시간은 직선거리보다 길다: 실주행 쌍의 평균 속도가 직선 기준 120km/h 이하', () => {
    const fast = Object.values(centers).flat().flatMap((p) => Object.entries(p.drive ?? {}).map(([h, sec]) => {
      const f = facilities.find((x) => x.hpid === h)!
      const km = haversine(p.lat, p.lon, f.위도, f.경도)
      return km >= 1 && km / (sec / 3600) > 120 ? `${p.지점}->${f.기관명}` : null
    })).filter(Boolean)
    expect(fast).toEqual([])
  })
})
