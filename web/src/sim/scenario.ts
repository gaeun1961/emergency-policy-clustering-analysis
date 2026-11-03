import type { Facility, FacilityGrade } from './model'

export interface AddedFacility { lat: number; lon: number; grade: FacilityGrade }
/** 시나리오 = 가상으로 추가한 기관 + 제거한 기존 기관 hpid */
export interface Scenario { added: AddedFacility[]; removed: string[] }

export const EMPTY: Scenario = { added: [], removed: [] }
export const GRADE_NAME: Record<FacilityGrade, string> = { G001: '권역응급의료센터', G006: '지역응급의료센터', G007: '지역응급의료기관' }
export const GRADE_SHORT: Record<FacilityGrade, string> = { G001: '권역센터', G006: '지역센터', G007: '지역기관' }
export const isEmpty = (s: Scenario) => !s.added.length && !s.removed.length

export const simId = (i: number) => `SIM-${i + 1}`

export function applyScenario(base: Facility[], s: Scenario): Facility[] {
  const removed = new Set(s.removed)
  return [
    ...base.filter((f) => !removed.has(f.hpid)),
    ...s.added.map((a, i) => ({ hpid: simId(i), 기관명: `가상 ${GRADE_SHORT[a.grade]} ${i + 1}`, 등급: a.grade, 위도: a.lat, 경도: a.lon, 시군구코드: null })),
  ]
}

// URL 쿼리: ?sim=1&add=G006:36.41234,129.36543;G007:...&rm=A1100001,A1200002
const GRADES: FacilityGrade[] = ['G001', 'G006', 'G007']

export function toQuery(on: boolean, s: Scenario): string {
  if (!on) return ''
  const p = new URLSearchParams({ sim: '1' })
  if (s.added.length) p.set('add', s.added.map((a) => `${a.grade}:${a.lat.toFixed(5)},${a.lon.toFixed(5)}`).join(';'))
  if (s.removed.length) p.set('rm', s.removed.join(','))
  return `?${p.toString().replace(/%3A/g, ':').replace(/%2C/g, ',').replace(/%3B/g, ';')}`
}

export function fromQuery(search: string): { on: boolean; scenario: Scenario } {
  const p = new URLSearchParams(search)
  const added = (p.get('add') ?? '').split(';').filter(Boolean).flatMap((item) => {
    const [grade, coords] = item.split(':')
    const [lat, lon] = (coords ?? '').split(',').map(Number)
    return GRADES.includes(grade as FacilityGrade) && Number.isFinite(lat) && Number.isFinite(lon)
      ? [{ grade: grade as FacilityGrade, lat, lon }] : []
  })
  const removed = (p.get('rm') ?? '').split(',').filter(Boolean)
  return { on: p.get('sim') === '1', scenario: { added, removed } }
}
