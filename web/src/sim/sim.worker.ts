/// <reference lib="webworker" />
/**
 * 시뮬레이션 재계산(simulate: 등급·점수)을 화면 밖에서. 기준점 약 4,000개 × 기관이라 프로덕션에서도 1초 가까이 걸려,
 * 메인 스레드에서 돌리면 기관을 추가·제거할 때마다 화면이 멈춘다.
 * init: 바뀌지 않는 기준점·기준선을 한 번 받아 둔다
 * run: 기관 목록으로 재계산. 계산 중에 들어온 요청은 쌓지 않고 마지막 것만 계산한다(이전 요청 취소).
 *      id를 그대로 돌려줘 메인 쪽에서 늦게 온 결과를 버릴 수 있게
 */
import { simulate, type Baseline, type Centers, type Facility } from './model'

type Init = { type: 'init'; centers: Centers; baseline: Baseline }
type Run = { type: 'run'; id: number; facilities: Facility[] }

let ctx: Omit<Init, 'type'> | null = null
let latest: Run | null = null

/** 대기 중인 요청 중 마지막 것만 계산. 계산하는 동안 온 메시지는 그 뒤에 처리돼 latest 를 덮어쓴다 */
function flush() {
  const m = latest
  if (!m || !ctx) return
  latest = null
  self.postMessage({ id: m.id, result: simulate(m.facilities, ctx.centers, ctx.baseline) })
}

self.onmessage = (e: MessageEvent<Init | Run>) => {
  const m = e.data
  if (m.type === 'init') {
    ctx = m
    flush() // init 보다 먼저 온 요청이 있으면
    return
  }
  const idle = latest === null
  latest = m
  if (idle) setTimeout(flush) // 같은 틈에 이어 들어온 요청까지 받은 뒤 마지막 것만
}
