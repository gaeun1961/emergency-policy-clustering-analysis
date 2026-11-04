import type { FeatureCollection, Geometry } from 'geojson'
import type { Baseline, Centers, Facility } from './sim/model'

export type Grade = '이중 취약' | '준 이중 취약' | ''

export interface Region {
  코드: string
  시도: string
  시군구: string
  총인구: number
  '65세이상인구': number
  고령인구비율: number
  독거노인비율: number
  장애인비율: number
  최근접_응급의료기관_분: number
  최근접_권역지역센터_분: number
  '30분내_기관수': number
  최근접_응급의료기관_km: number   // 직선거리 지표 (비교용으로 보존)
  최근접_권역지역센터_km: number
  반경30km_기관수: number
  우회계수: number                 // 분/직선km: 실주행시간이 없는 기관·가상 기관 근사에 씀
  근사반영비율: number              // 최근접 기관·센터가 근사값(도로 미연결·10곳 밖)인 기준점의 인구 비율
  최근접_응급의료기관_분_원값: number // 근사값 상한(도로 주행시간 99백분위) 적용 전 값. 지표보다 크면 화면에 "≥ N분 (근사)"
  최근접_권역지역센터_분_원값: number
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

export interface SimData { facilities: Facility[]; centers: Centers; baseline: Baseline }

/** 시뮬레이션 모드를 켤 때만 불러온다 */
export async function loadSimData(): Promise<SimData> {
  const get = (name: string) => fetch(`${import.meta.env.BASE_URL}data/${name}`).then((r) => {
    if (!r.ok) throw new Error(`${name}: ${r.status}`)
    return r.json()
  })
  const [facilities, centers, baseline] = await Promise.all([get('facilities.json'), get('centers.json'), get('baseline.json')])
  return { facilities, centers, baseline }
}

export const regionName =(r: Region) => (r.시군구 ? `${r.시도} ${r.시군구}` : r.시도)
/** 섬 읍·면을 리(섬) 단위로 나눠 계산한 시군구 */
export const isIsland = (r: Region) => r.기준점방식.includes('리 단위')

/** pandas Series.quantile 과 같은 선형 보간 분위수 */
export function quantile(values: number[], q: number): number {
  const s = [...values].sort((a, b) => a - b)
  const pos = (s.length - 1) * q
  const lo = Math.floor(pos)
  return s[lo] + (s[Math.min(lo + 1, s.length - 1)] - s[lo]) * (pos - lo)
}
