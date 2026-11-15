// 기관 N곳 순차 최적 배치를 오프라인으로 계산 (src/sim/placement.ts). 브라우저는 결과 JSON 만 읽는다.
// 실행: cd web && npm run placement   (python scripts/export_web_data.py 뒤에)
// 입력: web/public/data/facilities.json, centers.json, baseline.json, sigungu_metrics.json (65세 이상 인구)
// 출력: data/processed/placement_greedy.json, web/public/data/placement_greedy.json (같은 내용)
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { runnerImport } from 'vite'

const N = 5
const pub = new URL('../public/data/', import.meta.url)
const load = (name) => JSON.parse(readFileSync(new URL(name, pub), 'utf-8'))
const { module: placement } = await runnerImport(new URL('../src/sim/placement.ts', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1'))

const facilities = load('facilities.json'), centers = load('centers.json'), baseline = load('baseline.json')
const elderly = Object.fromEntries(load('sigungu_metrics.json').map((r) => [r.코드, r['65세이상인구']]))

const plans = {}
for (const kind of ['G007', 'G006']) {
  const t = performance.now()
  plans[kind] = placement.greedyPlacement(facilities, centers, baseline, elderly, kind, N)
  const p = plans[kind]
  console.log(`${kind}: 이중 취약 ${p.base} -> ${p.steps.map((s) => s.double).join(' -> ')} (${((performance.now() - t) / 1000).toFixed(1)}초)`)
  for (const [i, s] of p.steps.entries()) console.log(`  ${i + 1}. ${s.code} ${s.label} [${s.kind}] 벗어남 ${s.escaped.join(',') || '-'}, 주행시간 줄어드는 인구 ${s.popImproved.toLocaleString()}`)
}

const out = {
  설명: '기관 N곳 순차 배치(탐욕): 단계마다 이중 취약 감소 수 -> 동률이면 최근접 주행시간이 줄어드는 인구 합이 최대인 후보 1곳. '
    + '후보는 시뮬레이터 추천과 같은 가정 위치(기준점 신설, 지역센터는 지역기관 승격 포함). 기관 추가 없는 상태에서 시작, 판정은 고정 baseline 기준선',
  N,
  기준선: baseline.기준선,
  기관수: facilities.length,
  plans,
}
const json = JSON.stringify(out, null, 1)
const processed = new URL('../../data/processed/', import.meta.url)
mkdirSync(processed, { recursive: true })
writeFileSync(new URL('placement_greedy.json', processed), json)
writeFileSync(new URL('placement_greedy.json', pub), json)
console.log('-> data/processed/placement_greedy.json, web/public/data/placement_greedy.json')
