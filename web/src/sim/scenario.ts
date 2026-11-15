import type { Facility, FacilityGrade } from './model'

/** code: 추가한 위치가 속한 시군구 (URL에는 넣지 않고 좌표로 다시 판정) */
export interface AddedFacility { lat: number; lon: number; grade: FacilityGrade; code?: string }
/** 시나리오 = 가상으로 추가한 기관 + 제거한 기존 기관 hpid + 지역센터로 승격한 기존 지역기관 hpid.
 *  승격은 기관을 지우고 새로 놓지 않고 등급만 바꾼다: 그 기관의 도로 주행시간을 그대로 써서 추천(recommend)과 같은 값이 나온다 */
export interface Scenario { added: AddedFacility[]; removed: string[]; upgraded?: string[] }

export const EMPTY: Scenario = { added: [], removed: [] }
export const GRADE_NAME: Record<FacilityGrade, string> = { G001: '권역응급의료센터', G006: '지역응급의료센터', G007: '지역응급의료기관' }
export const GRADE_SHORT: Record<FacilityGrade, string> = { G001: '권역센터', G006: '지역센터', G007: '지역기관' }
export const isEmpty = (s: Scenario) => !s.added.length && !s.removed.length && !s.upgraded?.length

export const simId = (i: number) => `SIM-${i + 1}`

export function applyScenario(base: Facility[], s: Scenario): Facility[] {
  const removed = new Set(s.removed)
  const upgraded = new Set(s.upgraded)
  return [
    ...base.filter((f) => !removed.has(f.hpid)).map((f) => (upgraded.has(f.hpid) && f.등급 === 'G007' ? { ...f, 등급: 'G006' as const, 승격: true } : f)),
    ...s.added.map((a, i) => ({ hpid: simId(i), 기관명: `가상 ${GRADE_SHORT[a.grade]} ${i + 1}`, 등급: a.grade, 위도: a.lat, 경도: a.lon, 시군구코드: a.code ?? null })),
  ]
}

/** 추가 기관을 시군구 경계로 판정: 경계 안이면 시군구 코드를 붙이고, 바다·경계 밖이면 뺀다 */
export function keepOnLand(s: Scenario, locate: (lat: number, lon: number) => string | null): { scenario: Scenario; dropped: number } {
  const added = s.added.flatMap((a) => {
    const code = locate(a.lat, a.lon)
    return code ? [{ ...a, code }] : []
  })
  return { scenario: { ...s, added }, dropped: s.added.length - added.length }
}

// URL 쿼리: ?sim=1&add=G006:36.41234,129.36543;G007:...&rm=A1100001,A1200002&up=A1300003 (up: 지역센터로 승격)
const GRADES: FacilityGrade[] = ['G001', 'G006', 'G007']

export function toQuery(on: boolean, s: Scenario): string {
  if (!on) return ''
  const p = new URLSearchParams({ sim: '1' })
  if (s.added.length) p.set('add', s.added.map((a) => `${a.grade}:${a.lat.toFixed(5)},${a.lon.toFixed(5)}`).join(';'))
  if (s.removed.length) p.set('rm', s.removed.join(','))
  if (s.upgraded?.length) p.set('up', s.upgraded.join(','))
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
  const upgraded = (p.get('up') ?? '').split(',').filter(Boolean)
  return { on: p.get('sim') === '1', scenario: { added, removed, ...(upgraded.length ? { upgraded } : {}) } }
}
