/** 지역 정책 보고서(인쇄용 A4 한 장)의 문장 (components/Report.tsx). 숫자는 모두 배치 추천 결과(placement_greedy.json)에서 */
import { fmt } from './metrics'
import type { Placement, RegionBest } from './sim/placement'

export const KIND_NAME = { G006: '지역응급의료센터', G007: '지역응급의료기관' } as const

/** "이 시군구 안 OO에 기관 1곳을 두면" 효과 한 문장 (기관 추가 없는 상태 기준, simulate 로 확인한 값) */
export function bestSentence(best: RegionBest | undefined, kind: 'G006' | 'G007', nameOf: (code: string) => string): string {
  if (!best) return `시군구 안에 ${KIND_NAME[kind]} 1곳을 두어도 나아지는 후보가 없다.`
  const where = best.kind === 'upgrade' ? `${best.label}을(를) 지역응급의료센터로 승격하면` : `${best.label}에 ${KIND_NAME[kind]} 1곳을 두면`
  const effect = best.escaped.length
    ? `${best.escaped.map(nameOf).join(', ')} ${best.escaped.length}곳이 이중 취약에서 벗어나고`
    : '이중 취약에서 벗어나는 시군구는 없지만'
  return `${where} ${effect}, 주변 시군구를 포함해 ${fmt.int(best.popImproved)}명의 최근접 응급의료기관·센터 주행시간이 줄어든다.`
}

/** 순차 배치(1곳씩 5곳)에서 이 시군구가 이중 취약을 벗어나는 단계 (없으면 null) */
export const planStep = (plan: Placement | undefined, code: string) => {
  const i = plan?.steps.findIndex((s) => s.escaped.includes(code)) ?? -1
  return i < 0 ? null : i + 1
}
