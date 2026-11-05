/**
 * 목록 탭의 필터·검색 (순수 함수, vitest 로 검증)
 * - 필터(등급 지역만, 거리·병상 모두 취약만)가 모두 꺼지면 229곳 전체
 * - 검색어가 있으면 필터와 무관하게 229곳 전체에서 찾는다 (띄어쓰기 무시)
 * - 상위 시로 합친 일반구(수원시 장안구 등)는 구 이름으로 검색하면 "OO시에 포함" 안내
 */
import { regionName, type Region } from './data'

const norm = (s: string) => s.replace(/\s/g, '')

export interface ListFilter { q: string; gradeOnly: boolean; bothOnly: boolean; both: (r: Region) => boolean }

/** 목록에 보일 지역 (정렬 전). 검색 중이면 필터 무시 */
export function listRegions(regions: Region[], f: ListFilter): Region[] {
  const q = norm(f.q)
  if (q) return regions.filter((r) => norm(regionName(r)).includes(q))
  return regions.filter((r) => (!f.gradeOnly || r.등급 !== '') && (!f.bothOnly || f.both(r)))
}

/** meta.json 일반구: [시도, '수원시 장안구', 상위 시 코드] */
export type District = [string, string, string]
export interface DistrictHint { name: string; parent: Region }

/** 구 이름(또는 '시 구' 전체)으로 검색했을 때 상위 시 안내. 시 이름만 맞는 검색(예: '수원')은 그 시가 목록에 나오므로 안내하지 않음 */
export function districtHints(q: string, districts: District[], byCode: Map<string, Region>): DistrictHint[] {
  const n = norm(q)
  if (!n) return []
  return districts.flatMap(([sido, name, code]) => {
    const [city] = name.split(' ')
    const parent = byCode.get(code)
    return parent && norm(name).includes(n) && !norm(city).includes(n) ? [{ name: `${sido} ${name}`, parent }] : []
  })
}
