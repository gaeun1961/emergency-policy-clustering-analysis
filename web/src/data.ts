import type { FeatureCollection, Geometry } from 'geojson'

export type Grade = '이중 취약' | '준 이중 취약' | ''

export interface Region {
  코드: string
  시도: string
  시군구: string
  총인구: number
  고령인구비율: number
  독거노인비율: number
  장애인비율: number
  최근접_응급의료기관_km: number
  최근접_권역지역센터_km: number
  반경30km_기관수: number
  접근성점수: number
  복지점수: number
  등급: Grade
  클러스터: number
  클러스터라벨: string
  접근성순위: number
  복지순위: number
  합산점수: number | null
  기준점방식: string
}

export interface Meta {
  기준시점: Record<string, string>
  시군구수: number
  이중취약수: number
  준이중취약수: number
  클러스터: Record<string, string>
  출처: { 이름: string; url: string; 기준: string | null }[]
  생성일시: string
}

export type SigunguGeo = FeatureCollection<Geometry, { code: string; 시도: string; 시군구: string }>
export type SidoGeo = FeatureCollection<Geometry>

export interface Data {
  regions: Region[]
  byCode: Map<string, Region>
  sigungu: SigunguGeo
  sido: SidoGeo
  meta: Meta
}

export async function loadData(): Promise<Data> {
  const get = (name: string) => fetch(`${import.meta.env.BASE_URL}data/${name}`).then((r) => {
    if (!r.ok) throw new Error(`${name}: ${r.status}`)
    return r.json()
  })
  const [regions, sigungu, sido, meta] = await Promise.all([
    get('sigungu_metrics.json'), get('sigungu.geojson'), get('sido.geojson'), get('meta.json'),
  ])
  return { regions, byCode: new Map((regions as Region[]).map((r) => [r.코드, r])), sigungu, sido, meta }
}

export const regionName = (r: Region) => (r.시군구 ? `${r.시도} ${r.시군구}` : r.시도)
export const isIsland = (r: Region) => r.기준점방식.startsWith('weighted')

/** pandas Series.quantile 과 같은 선형 보간 분위수 */
export function quantile(values: number[], q: number): number {
  const s = [...values].sort((a, b) => a - b)
  const pos = (s.length - 1) * q
  const lo = Math.floor(pos)
  return s[lo] + (s[Math.min(lo + 1, s.length - 1)] - s[lo]) * (pos - lo)
}
