/**
 * 읍면동(행정동) 드릴다운: 선택한 시군구의 기준점을 행정동별로 묶어 주행시간 지표·전국 접근성 구간·이용 기관을 계산한다.
 * Python src/emd_metrics.py 와 같은 정의 (기준점 인구가중 → 소수 3자리, 전국 행정동 분포 기준 백분위 평균, 사분위 구간).
 * 시뮬레이션 중에는 추가·제거가 반영된 기관 목록을 넘기면 된다. 시군구 판정에는 쓰지 않는다
 */
import {
  ACCESS_KEYS, aggregate, aggregateUsage, isCenter, nearestOf, percentile, pointMetrics,
  type AccessKey, type CenterPoint, type Facility, type PointMetrics, type Usage,
} from './model'

/** emd.json: 고정값과 전국 행정동 분포 (scripts/export_web_data.py export_emd) */
export interface EmdData {
  행정동: Record<string, [string, number, number]>          // [이름, 인구, 고령인구비율]
  리: Record<string, Record<string, [number, number]>>      // 섬 읍·면: 리 -> [인구, 고령인구비율]
  지표: Record<AccessKey, number[]>
  방향: Record<AccessKey, 1 | -1>
  구간: string[]                                            // 접근성 좋은 순, 마지막이 '하위 25%'
  구간경계: number[]
}

export interface EmdLi { 리: string; 인구: number; 고령인구비율: number | null; metrics: PointMetrics }
export interface EmdRow {
  code: string
  이름: string
  인구: number
  고령인구비율: number
  metrics: PointMetrics
  점수: number
  구간: number                // EmdData.구간 위치 (클수록 취약)
  근사반영비율: number
  em: Usage[]                 // 이 행정동 주민의 이용 응급의료기관
  ctr: Usage[]                // 이용 권역·지역센터
  li: EmdLi[]                 // 섬 읍·면만
}

export function emdScore(m: PointMetrics, d: EmdData): number {
  return ACCESS_KEYS.reduce((s, k) => s + percentile(d.지표[k], m[k], d.방향[k]), 0) / ACCESS_KEYS.length
}
export const emdBand = (score: number, d: EmdData) => d.구간경계.filter((c) => score >= c - 1e-9).length

/** 한 시군구의 행정동별 지표. points: centers[시군구코드] (emd = 행정동코드) */
export function emdRows(points: CenterPoint[], facilities: Facility[], factor: number, cap: number, minutes: number, d: EmdData): EmdRow[] {
  const index = new Map(facilities.map((f, i) => [f.hpid, i]))
  const centers = facilities.filter(isCenter)
  const groups = new Map<string, CenterPoint[]>()
  for (const p of points) groups.set(p.emd!, [...(groups.get(p.emd!) ?? []), p])
  return [...groups].map(([code, ps]) => {
    const per = ps.map((p) => pointMetrics(p, facilities, factor, minutes, cap, index))
    const ne = ps.map((p) => nearestOf(p, facilities, factor, cap))
    const nc = ps.map((p) => nearestOf(p, centers, factor, cap))
    const metrics = aggregate(ps, per)
    const score = emdScore(metrics, d)
    const wsum = ps.reduce((s, p) => s + p.weight, 0)
    const approxW = ps.reduce((s, p, i) => s + (ne[i]?.approx || nc[i]?.approx ? p.weight : 0), 0)
    const [이름, 인구, 고령인구비율] = d.행정동[code]
    const liInfo = d.리[code]
    return {
      code, 이름, 인구, 고령인구비율, metrics, 점수: score, 구간: emdBand(score, d), 근사반영비율: approxW / wsum,
      em: aggregateUsage(ps, ne), ctr: aggregateUsage(ps, nc),
      li: liInfo ? ps.map((p, i) => {
        const name = p.지점.split(' ').at(-1)!
        return { 리: name, 인구: liInfo[name]?.[0] ?? p.weight, 고령인구비율: liInfo[name]?.[1] ?? null, metrics: per[i] }
      }) : [],
    }
  })
}
