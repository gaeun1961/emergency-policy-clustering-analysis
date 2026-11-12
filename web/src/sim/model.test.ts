import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { regionName, type Region } from '../data'
import { districtHints, listRegions, type District } from '../search'
import { isBothVulnerable, sfcaBand, sfcaCuts } from '../metrics'
import { ACCESS_KEYS, RAW_KEYS, driveMinutes, facilityUsage, haversine, makeScorer, nearestFacilities, rankFacilities, scoreAgainstBaseline, simulate, LIST_MAX, LIST_TOP, type Baseline, type Centers, type Facility, type RankedFacility } from './model'
import { recommend } from './recommend'
import type { SigunguGeo } from '../data'
import { locateSigungu } from './geo'
import { emdRows, type EmdData } from './emd'
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
    }, 30000) // 추천 + 전체 재계산 5회라 기본 5초를 넘을 수 있음
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

/** Python 순위 행(csv)과 rankFacilities 결과 비교: 순서·평균 주행분·직선km·이용 비율·근사·상한 */
function sameRank(rs: RankedFacility[], p: Record<string, string>[]) {
  return rs.length === p.length && p.every((u, i) => {
    const v = rs[i]
    return v.f.hpid === u.hpid && Math.abs(v.min - +u.평균주행분) < 1e-5 && Math.abs(v.km - +u.평균직선km) < 1e-5
      && Math.abs(v.share - +u.주민비율) < 1e-5 && v.alt === (+u.주민비율 === 0)
      && v.approx === (u.근사포함 === 'True') && v.capped === (u.상한포함 === 'True')
      && (u.이용주민평균주행분 === '' ? v.useMin === null : Math.abs(v.useMin! - +u.이용주민평균주행분) < 1e-5)
      && v.useCapped === (u.이용주민상한포함 === 'True')
  })
}

describe('가까운 기관 목록 (주민 평균 주행시간 순 + 이용 비율, 대안)', () => {
  const rank = readFileSync(new URL('../../../data/processed/facility_rank.csv', import.meta.url), 'utf-8')
    .replace(/^\uFEFF/, '').trim().split(/\r?\n/)
  const cols = rank[0].split(',')
  const py = rank.slice(1).map((l) => Object.fromEntries(l.split(',').map((v, i) => [cols[i], v])))
  for (const [kind, centersOnly] of [['응급의료기관', false], ['권역지역센터', true]] as const) {
    it(`${kind}: 229곳 목록(순서·값)이 Python facility_rank 와 같다`, () => {
      const bad = regions.filter((r) => !sameRank(
        rankFacilities(centers[r.코드], facilities, r.우회계수, baseline.근사상한분, centersOnly ? LIST_TOP.ctr : LIST_TOP.em, centersOnly),
        py.filter((u) => u.행정기관코드 === r.코드 && u.구분 === kind),
      )).map((r) => r.시군구)
      expect(bad).toEqual([])
    })
  }

  it('영덕: 주민 30%의 최근접인 울진군의료원이 이용 10% 이상 규칙으로 목록에 들어간다', () => {
    const r = regions.find((x) => x.코드 === '47770')!
    const rs = rankFacilities(centers['47770'], facilities, r.우회계수, baseline.근사상한분, LIST_TOP.em)
    const 울진 = rs.find((x) => x.f.기관명 === '울진군의료원')!
    expect(울진.share).toBeGreaterThan(0.29)
    expect(rs.indexOf(울진)).toBe(3)                                   // 주행시간 순 3곳 다음 (4번째)
    expect(울진.useMin).toBeCloseTo(53.09, 1)                          // 이용 주민(북부) 기준 약 53분, 전체 평균은 88분
    expect(울진.min).toBeGreaterThan(80)
    for (let i = 1; i < rs.length; i++) expect(rs[i].min).toBeGreaterThanOrEqual(rs[i - 1].min)
    expect(rs.length).toBeLessThanOrEqual(LIST_MAX)
  })

  it('대안은 이용 비율 0, plus 는 1위 대비 추가 시간', () => {
    const r = regions.find((x) => x.코드 === '47770')!
    const rs = rankFacilities(centers['47770'], facilities, r.우회계수, baseline.근사상한분, 3)
    for (const x of rs) {
      expect(x.alt).toBe(x.share === 0)
      expect(x.plus).toBeCloseTo(x.min - rs[0].min, 9)
    }
  })

  it('시뮬레이터 추가 기관이 1위가 되고 이용 비율이 생긴다', () => {
    const r = regions.find((x) => x.코드 === '47770')!
    const 영덕 = [...centers['47770']].sort((a, b) => b.weight - a.weight)[0]
    const added: Facility = { hpid: 'SIM-1', 기관명: '가상', 등급: 'G006', 위도: 영덕.lat, 경도: 영덕.lon, 시군구코드: '47770' }
    const [top] = rankFacilities(centers['47770'], [...facilities, added], r.우회계수, baseline.근사상한분, 3, true)
    expect(top.f.hpid).toBe('SIM-1')
    expect(top.share).toBeGreaterThan(0)
  })
})

describe('이용 기관 (기준점별 주행시간 최근접 기관의 주민 비율)', () => {
  // Python src.accessibility.facility_usage 결과: 행정기관코드,구분,hpid,주민비율,평균주행분,평균직선km,근사포함
  const rows = readFileSync(new URL('../../../data/processed/facility_usage.csv', import.meta.url), 'utf-8')
    .replace(/^\uFEFF/, '').trim().split(/\r?\n/).slice(1).map((l) => l.split(','))
  const cap = baseline.근사상한분

  for (const [kind, centersOnly] of [['응급의료기관', false], ['권역지역센터', true]] as const) {
    it(`${kind}: 229곳 기관·비율·평균 주행시간·직선거리·근사 여부가 Python과 같다`, () => {
      const bad: unknown[] = []
      for (const r of regions) {
        const py = rows.filter((x) => x[0] === r.코드 && x[1] === kind)
        const js = facilityUsage(centers[r.코드], facilities, r.우회계수, cap, centersOnly)
        const same = py.length === js.length && py.every((x, i) => {
          const u = js.find((v) => v.f.hpid === x[2])
          return u && Math.abs(u.share - +x[3]) < 1e-5 && Math.abs(u.min - +x[4]) < 1e-5 && Math.abs(u.km - +x[5]) < 1e-5
            && u.approx === (x[6] === 'True') && (i > 0 || js[0].f.hpid === x[2] || Math.abs(js[0].share - +x[3]) < 1e-9)
        })
        if (!same) bad.push([r.시군구, py.map((x) => x[2]), js.map((u) => u.f.hpid)])
      }
      expect(bad).toEqual([])
    })
  }

  it('비율 합은 1, 비율이 큰 순', () => {
    for (const r of regions) {
      const u = facilityUsage(centers[r.코드], facilities, r.우회계수, cap)
      expect(u.reduce((s, x) => s + x.share, 0)).toBeCloseTo(1, 9)
      for (let i = 1; i < u.length; i++) expect(u[i - 1].share).toBeGreaterThanOrEqual(u[i].share)
    }
  })

  it('시뮬레이터 추가 기관도 이용 기관 집계에 들어간다 (근사값)', () => {
    const 영덕 = [...centers['47770']].sort((a, b) => b.weight - a.weight)[0]
    const added: Facility = { hpid: 'SIM-1', 기관명: '가상', 등급: 'G006', 위도: 영덕.lat, 경도: 영덕.lon, 시군구코드: '47770' }
    const factor = regions.find((r) => r.코드 === '47770')!.우회계수
    for (const centersOnly of [false, true]) {
      const [top] = facilityUsage(centers['47770'], [...facilities, added], factor, cap, centersOnly)
      expect(top.f.hpid).toBe('SIM-1')
      expect(top.approx).toBe(true)
    }
  })
})

describe('읍면동 드릴다운 (Python src.emd_metrics 와 일치)', () => {
  const emd = load<EmdData>('emd.json')
  const csv = (name: string) => {
    const [head, ...lines] = readFileSync(new URL(`../../../data/processed/${name}`, import.meta.url), 'utf-8').replace(/^\uFEFF/, '').trim().split(/\r?\n/)
    const cols = head.split(',')
    const split = (l: string) => l.split(/,(?=(?:[^"]*"[^"]*")*[^"]*$)/).map((v) => v.replace(/^"|"$/g, ''))  // "두류1,2동" 같은 따옴표 칸
    return lines.map((l) => Object.fromEntries(split(l).map((v, i) => [cols[i], v])))
  }
  const py = new Map(csv('emd_metrics.csv').map((r) => [r.행정동코드, r]))
  const cap = baseline.근사상한분
  const rows = regions.flatMap((r) => emdRows(centers[r.코드], facilities, r.우회계수, cap, baseline.기준분, emd))

  it('행정동 3,557곳 모두 계산되고 인구 합이 시군구 인구와 같다', () => {
    expect(rows).toHaveLength(3557)
    for (const r of regions) {
      const sum = emdRows(centers[r.코드], facilities, r.우회계수, cap, baseline.기준분, emd).reduce((s, x) => s + x.인구, 0)
      expect(sum).toBe(r.총인구)
    }
  }, 30000) // 229곳 읍면동 재계산이라 기본 5초를 넘을 수 있음

  it('지표·점수·구간·근사 반영 비율이 Python과 같다', () => {
    const bad = rows.filter((x) => {
      const p = py.get(x.code)!
      return [...ACCESS_KEYS, ...RAW_KEYS].some((k) => Math.abs(x.metrics[k]! - +p[k]) > 1e-6)
        || Math.abs(x.점수 - +p.접근성점수) > 1e-5 || emd.구간[x.구간] !== p.접근성구간
        || Math.abs(x.근사반영비율 - +p.근사반영_인구비율) > 1e-5 || Math.abs(x.고령인구비율 - +p.고령인구비율) > 1e-4
    }).map((x) => [x.code, x.이름])
    expect(bad).toEqual([])
  })

  it('가까운 기관(주민 평균 주행시간 순 + 이용 비율)이 Python emd_facility_rank 와 같다', () => {
    const pyRank = csv('emd_facility_rank.csv')
    const bad: unknown[] = []
    for (const x of rows) {
      for (const [kind, rs] of [['응급의료기관', x.em], ['권역지역센터', x.ctr]] as const) {
        const p = pyRank.filter((u) => u.행정동코드 === x.code && u.구분 === kind)
        if (!sameRank(rs, p)) bad.push([x.code, x.이름, kind, p.map((u) => u.hpid), rs.map((v) => v.f.hpid)])
      }
    }
    expect(bad).toEqual([])
  }, 30_000) // 앱 계산(emdRows)은 위 describe 에서 끝남. 느린 건 이 비교: CSV 17,800줄 정규식 파싱 + 행정동 7,114번 x 전체 filter

  it('시뮬레이터 기관 추가가 읍면동 값에도 반영된다', () => {
    const 영덕 = regions.find((r) => r.코드 === '47770')!
    const before = emdRows(centers['47770'], facilities, 영덕.우회계수, cap, baseline.기준분, emd)
    const target = before.reduce((a, b) => (a.점수 > b.점수 ? a : b))   // 가장 취약한 행정동 기준점에 지역센터 추가
    const p = centers['47770'].find((c) => c.emd === target.code)!
    const added: Facility = { hpid: 'SIM-1', 기관명: '가상', 등급: 'G006', 위도: p.lat, 경도: p.lon, 시군구코드: '47770' }
    const after = emdRows(centers['47770'], [...facilities, added], 영덕.우회계수, cap, baseline.기준분, emd)
    const t = after.find((x) => x.code === target.code)!
    expect(t.metrics.최근접_권역지역센터_분).toBeLessThan(target.metrics.최근접_권역지역센터_분)
    expect(t.em[0].f.hpid).toBe('SIM-1')
    expect(t.점수).toBeLessThan(target.점수)
  })
})

describe('2SFCA 보조 지표 (Python src.sfca 와 일치)', () => {
  const cuts = sfcaCuts(regions)
  it('하위 25% 판정이 Python 2SFCA하위25 와 같다 (229곳)', () => {
    expect(regions.filter((r) => (sfcaBand(r['2SFCA'], cuts) === 0) !== r['2SFCA하위25']).map((r) => r.시군구)).toEqual([])
  })
  it('거리·병상 모두 취약 = 이중 취약 중 2SFCA 하위 25%: 10곳 (영덕·보은 포함)', () => {
    const both = regions.filter((r) => isBothVulnerable(r, cuts)).map((r) => r.시군구)
    expect(both).toHaveLength(regions.filter((r) => r.등급 === '이중 취약' && r['2SFCA하위25']).length)
    expect(both).toHaveLength(10)
    expect(both).toEqual(expect.arrayContaining(['영덕군', '보은군']))
  })
  it('기존 판정·점수 필드는 그대로 (등급 개수)', () => {
    expect(regions.filter((r) => r.등급 === '이중 취약')).toHaveLength(36)
    expect(regions.filter((r) => r.등급 === '준 이중 취약')).toHaveLength(30)
  })
})


describe('목록 필터·검색 (229곳 전체)', () => {
  const meta = load<{ 일반구: District[] }>('meta.json')
  const byCode = new Map(regions.map((r) => [r.코드, r]))
  const none = { q: '', gradeOnly: false, bothOnly: false, both: () => false }
  it('필터를 모두 끄면 229곳 전체', () => {
    expect(listRegions(regions, none)).toHaveLength(229)
  })
  it('기본(이중·준 이중만)은 66곳', () => {
    expect(listRegions(regions, { ...none, gradeOnly: true })).toHaveLength(66)
  })
  it('검색은 필터와 무관하게 전체에서 (등급 없는 지역·띄어쓰기 무시)', () => {
    const f = { ...none, gradeOnly: true, bothOnly: true }
    expect(listRegions(regions, { ...f, q: '종로' }).map((r) => r.시군구)).toEqual(['종로구'])
    expect(listRegions(regions, { ...f, q: '서울 종로구' }).map((r) => r.시군구)).toEqual(['종로구'])
    expect(listRegions(regions, { ...f, q: '세종' }).map((r) => r.시도)).toEqual(['세종'])
    // 모든 지역이 자기 이름으로 검색된다
    for (const r of regions) expect(listRegions(regions, { ...f, q: regionName(r) })).toContain(r)
  })
  it('일반구 이름으로 검색하면 상위 시 안내 (수원 장안구, 청주 상당구, 포항 남구)', () => {
    expect(districtHints('장안구', meta.일반구, byCode).map((h) => h.parent.시군구)).toEqual(['수원시'])
    expect(districtHints('상당구', meta.일반구, byCode).map((h) => h.parent.시군구)).toEqual(['청주시'])
    expect(districtHints('포항시 남구', meta.일반구, byCode).map((h) => h.parent.시군구)).toEqual(['포항시'])
    expect(districtHints('남구', meta.일반구, byCode).map((h) => h.parent.시군구)).toContain('포항시')
    expect(districtHints('수원', meta.일반구, byCode)).toEqual([])   // 시 이름만 맞으면 목록에 수원시가 나오므로 안내 없음
    const cities = new Set(meta.일반구.map((d) => d[2]))
    expect([...cities].every((c) => byCode.has(c))).toBe(true)        // 상위 시 코드가 모두 229곳 안에 있음
  })
})
