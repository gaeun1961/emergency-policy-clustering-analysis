import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { DEPT_NOTE, KEY_DEPARTMENTS, keyDepartments } from './departments'
import type { Facility } from './sim/model'

const load = <T>(name: string): T => JSON.parse(readFileSync(new URL(`../public/data/${name}`, import.meta.url), 'utf-8'))

describe('진료과목 (참고 표시, #67)', () => {
  it('주요 과 보유 여부, 정보가 없으면 null', () => {
    expect(keyDepartments(undefined)).toBeNull()
    const k = keyDepartments(['내과', '소아청소년과', '응급의학과'])!
    expect(k.map((d) => d.name)).toEqual([...KEY_DEPARTMENTS])
    expect(k.filter((d) => d.has).map((d) => d.name)).toEqual(['응급의학과', '소아청소년과'])
  })

  it('고지 문구: 실시간 진료 가능 여부 아님 + 기준월', () => {
    expect(DEPT_NOTE('2026-11')).toBe('진료과목 보유 정보이며 실시간 진료 가능 여부가 아닙니다 (기준 2026-11).')
  })

  it('내보낸 데이터: 응급의료기관 416곳 모두 진료과목 목록, 기준월 YYYY-MM', () => {
    const fac = load<Facility[]>('facilities.json')
    expect(fac.length).toBe(416)
    expect(fac.filter((f) => !Array.isArray(f.진료과목)).map((f) => f.기관명)).toEqual([])
    expect(fac.filter((f) => (f.진료과목 ?? []).some((d) => !d || d.includes(',') || d !== d.trim()))).toEqual([])
    expect(load<{ 기준시점: Record<string, string> }>('meta.json').기준시점['진료과목']).toMatch(/^\d{4}-\d{2}$/)
  })
})
