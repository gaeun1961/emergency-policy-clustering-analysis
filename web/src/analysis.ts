/** 분포 탭 그룹 비교: 등급별 지표 중앙값 (판정에 쓴 지표 / 판정에 쓰지 않은 검증 지표) */
import { quantile, type Grade, type Region } from './data'
import { fmt } from './metrics'

export const GROUPS: Grade[] = ['이중 취약', '준 이중 취약', '']

export interface Indicator { key: keyof Region; label: string; used: boolean; text: (v: number) => string }

export const INDICATORS: Indicator[] = [
  { key: '최근접_응급의료기관_분', label: '최근접 응급의료기관 (분)', used: true, text: fmt.min },
  { key: '30분내_기관수', label: '30분 내 응급의료기관 (곳)', used: true, text: (v) => `${v.toFixed(1)}곳` },
  { key: '고령인구비율', label: '고령인구비율', used: true, text: fmt.pct },
  { key: '독거노인비율', label: '독거노인비율', used: true, text: fmt.pct },
  { key: '장애인비율', label: '장애인비율', used: true, text: fmt.pct },
  { key: '기초연금수급률', label: '기초연금 수급률', used: false, text: fmt.pct },
  { key: '수급자비율', label: '기초생활수급자 비율', used: false, text: fmt.pct },
  { key: '2SFCA', label: '응급실 병상 (10만 명당)', used: false, text: fmt.beds },
]

/** 지표별 등급 그룹 중앙값과 그룹 크기 */
export function groupMedians(regions: Region[]) {
  const by = new Map(GROUPS.map((g) => [g, regions.filter((r) => r.등급 === g)]))
  return {
    counts: GROUPS.map((g) => by.get(g)!.length),
    rows: INDICATORS.map((ind) => ({
      ...ind,
      medians: GROUPS.map((g) => { const rs = by.get(g)!; return rs.length ? quantile(rs.map((r) => r[ind.key] as number), 0.5) : NaN }),
    })),
  }
}
