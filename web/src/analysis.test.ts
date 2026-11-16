import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { GROUPS, groupMedians } from './analysis'
import { quantile, type Region } from './data'

const regions: Region[] = JSON.parse(readFileSync(new URL('../public/data/sigungu_metrics.json', import.meta.url), 'utf-8'))

describe('분포 탭 그룹 비교 (#83)', () => {
  const { counts, rows } = groupMedians(regions)
  const row = (k: string) => rows.find((r) => r.key === k)!
  it('그룹 크기: 이중 36, 준 이중 30, 합 229', () => {
    expect(counts).toEqual([36, 30, 229 - 66])
  })
  it('중앙값은 그 그룹만의 분위수', () => {
    const dbl = regions.filter((r) => r.등급 === GROUPS[0]).map((r) => r.독거노인비율)
    expect(row('독거노인비율').medians[0]).toBeCloseTo(quantile(dbl, 0.5))
  })
  it('판정에 쓰지 않은 기초연금 수급률도 이중 취약이 해당 없음보다 높다', () => {
    expect(row('기초연금수급률').used).toBe(false)
    expect(row('기초연금수급률').medians[0]).toBeGreaterThan(row('기초연금수급률').medians[2])
  })
})

describe('분포 탭 누적 인구 곡선 (#83)', () => {
  const c = JSON.parse(readFileSync(new URL('../public/data/access_curve.json', import.meta.url), 'utf-8'))
  it('그룹마다 0~60분 누적 비율이 줄지 않고 0~1 사이', () => {
    for (const vs of Object.values(c.비율) as number[][]) {
      expect(vs).toHaveLength(c.분.length)
      vs.forEach((v, i) => { expect(v).toBeGreaterThanOrEqual(i ? vs[i - 1] : 0); expect(v).toBeLessThanOrEqual(1) })
    }
  })
  it('이중 취약 주민은 전국보다 30분 안에 닿는 비율이 낮다, 인구 합 = 그룹 합', () => {
    expect(c.비율['이중 취약'][30]).toBeLessThan(c.비율['전국'][30])
    expect(c.인구['이중 취약'] + c.인구['준 이중 취약'] + c.인구['해당 없음']).toBe(c.인구['전국'])
  })
})
