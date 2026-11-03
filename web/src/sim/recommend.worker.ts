/// <reference lib="webworker" />
/**
 * 추천 위치 계산을 화면 밖에서 (기준점 약 4,000개 × 후보 약 4,000개라 1초 가까이 걸림)
 * init: 바뀌지 않는 기준점·기준선·65세 이상 인구를 한 번 받아 둔다
 * run: 현재 기관 목록·시뮬레이션 결과로 추천 계산, id를 그대로 돌려줘 늦게 온 이전 결과를 버릴 수 있게
 */
import type { Baseline, Centers, Facility, SimRegion } from './model'
import { recommend } from './recommend'

type Init = { type: 'init'; centers: Centers; baseline: Baseline; elderly: Record<string, number> }
type Run = { type: 'run'; id: number; facilities: Facility[]; current: Record<string, SimRegion>; kind: 'G007' | 'G006' }

let ctx: Omit<Init, 'type'> | null = null
self.onmessage = (e: MessageEvent<Init | Run>) => {
  const m = e.data
  if (m.type === 'init') ctx = m
  else if (ctx) self.postMessage({ id: m.id, recs: recommend(m.facilities, ctx.centers, ctx.baseline, m.current, ctx.elderly, m.kind) })
}
