import { quantile, type Grade, type Region } from './data'
import { T } from './theme'

// 색: 테마(theme.ts)의 한 색상 계열. 진할수록 취약
export const GRADE_COLOR: Record<Grade, string> = { '이중 취약': T.grade.double, '준 이중 취약': T.grade.near, '': T.grade.none }
export const CLUSTER_COLOR = T.cluster // 0 도시 / 1 센터 원거리 / 2 응급의료 취약 (취약할수록 진하게)
const RAMP = T.ramp

export type MetricKey = '등급' | '접근성점수' | '복지점수' | '클러스터' | '최근접_응급의료기관_km' | '최근접_권역지역센터_km'

export interface LegendItem { color: string; label: string }
export interface Metric {
  key: MetricKey
  label: string
  format: (r: Region) => string
  color: (r: Region) => string
  legend: LegendItem[]
  note?: string
}

const pct = (v: number) => `${(v * 100).toFixed(1)}%`
export const fmt = {
  km: (v: number) => `${v < 10 ? v.toFixed(1) : v.toFixed(0)}km`,
  score: (v: number) => v.toFixed(1),
  pct,
  int: (v: number) => Math.round(v).toLocaleString('ko-KR'),
}

/** 5단계 계급: 점수는 0~100 등간격, 거리는 분위수(오른쪽으로 치우친 분포) */
function stepped(values: number[], breaks: number[], fmtBreak: (v: number) => string) {
  const color = (v: number) => RAMP[breaks.filter((b) => v >= b).length]
  const edges = [Math.min(...values), ...breaks, Math.max(...values)]
  const legend = RAMP.map((c, i) => ({ color: c, label: `${fmtBreak(edges[i])} ~ ${fmtBreak(edges[i + 1])}` }))
  return { color, legend }
}

export function buildMetrics(regions: Region[], clusterLabels: Record<string, string>): Record<MetricKey, Metric> {
  const scoreBreaks = [20, 40, 60, 80]
  const acc = stepped(regions.map((r) => r.접근성점수), scoreBreaks, (v) => v.toFixed(0))
  const wel = stepped(regions.map((r) => r.복지점수), scoreBreaks, (v) => v.toFixed(0))
  const kmScale = (get: (r: Region) => number) => {
    const vs = regions.map(get)
    return stepped(vs, [0.2, 0.4, 0.6, 0.8].map((q) => quantile(vs, q)), (v) => fmt.km(v))
  }
  const near = kmScale((r) => r.최근접_응급의료기관_km)
  const ctr = kmScale((r) => r.최근접_권역지역센터_km)

  return {
    등급: {
      key: '등급', label: '등급',
      format: (r) => r.등급 || '해당 없음',
      color: (r) => GRADE_COLOR[r.등급],
      legend: (['이중 취약', '준 이중 취약', ''] as Grade[]).map((g) => ({ color: GRADE_COLOR[g], label: g || '해당 없음' })),
    },
    접근성점수: {
      key: '접근성점수', label: '응급의료 접근성 취약 점수',
      format: (r) => `${fmt.score(r.접근성점수)}점`, color: (r) => acc.color(r.접근성점수), legend: acc.legend,
      note: '0~100, 높을수록 취약',
    },
    복지점수: {
      key: '복지점수', label: '복지 취약 점수',
      format: (r) => `${fmt.score(r.복지점수)}점`, color: (r) => wel.color(r.복지점수), legend: wel.legend,
      note: '0~100, 높을수록 취약',
    },
    클러스터: {
      key: '클러스터', label: '시군구 유형 (클러스터)',
      format: (r) => `${r.클러스터}. ${r.클러스터라벨}`,
      color: (r) => CLUSTER_COLOR[r.클러스터],
      legend: Object.entries(clusterLabels).map(([k, v]) => ({ color: CLUSTER_COLOR[Number(k)], label: `${k}. ${v}` })),
    },
    최근접_응급의료기관_km: {
      key: '최근접_응급의료기관_km', label: '최근접 응급의료기관 거리',
      format: (r) => fmt.km(r.최근접_응급의료기관_km), color: (r) => near.color(r.최근접_응급의료기관_km), legend: near.legend,
      note: '행정동 인구가중 직선거리, 5분위',
    },
    최근접_권역지역센터_km: {
      key: '최근접_권역지역센터_km', label: '최근접 권역·지역응급의료센터 거리',
      format: (r) => fmt.km(r.최근접_권역지역센터_km), color: (r) => ctr.color(r.최근접_권역지역센터_km), legend: ctr.legend,
      note: '행정동 인구가중 직선거리, 5분위',
    },
  }
}

const CLUSTER_LEAD: Record<number, string> = {
  0: '수도권·광역시 등 도시.',
  1: '지방 중소도시와 도시 외곽.',
  2: '고령 농촌. 응급의료기관과 중증 센터가 모두 멀다.',
}

/** 클러스터 설명: 수치는 데이터(클러스터별 중앙값)에서 계산 */
export function clusterDesc(regions: Region[], k: number): string {
  const rs = regions.filter((r) => r.클러스터 === k)
  if (!rs.length) return CLUSTER_LEAD[k] ?? ''
  const med = (f: (r: Region) => number) => quantile(rs.map(f), 0.5)
  return `${CLUSTER_LEAD[k] ?? ''} 중앙값: 최근접 응급의료기관 ${fmt.km(med((r) => r.최근접_응급의료기관_km))}, ` +
    `권역·지역센터 ${fmt.km(med((r) => r.최근접_권역지역센터_km))}, 반경 30km 기관 ${Math.round(med((r) => r.반경30km_기관수))}곳, ` +
    `고령인구 ${fmt.pct(med((r) => r.고령인구비율))} (${rs.length}곳)`
}
