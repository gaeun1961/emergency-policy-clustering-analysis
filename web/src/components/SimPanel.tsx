import { useState } from 'react'
import { regionName, type Region } from '../data'
import { GRADE_COLOR, fmt } from '../metrics'
import { planScenario, type Placement } from '../sim/placement'
import type { Effect } from '../sim/recommend'
import { GRADE_SHORT, isEmpty, toQuery, type Scenario } from '../sim/scenario'

export type RecKind = 'G007' | 'G006'

interface Props {
  base: Region[]
  now: Map<string, Region>
  scenario: Scenario
  canUndo: boolean
  onUndo: () => void
  onReset: () => void
  recKind: RecKind
  onRecKind: (k: RecKind) => void
  recs: Effect[] | null
  onApply: (e: Effect) => void
  onSelect: (code: string) => void
  busy?: boolean // 재계산(워커) 중: 숫자는 직전 결과
  plan?: Placement | null // 순차 배치 추천(오프라인 계산, 지금 탭 종류). 불러오기 전이면 undefined
  onApplyPlan: (s: Scenario) => void
}

const gradeLabel = (g: string) => g || '해당 없음'
const names = (codes: string[], byCode: Map<string, Region>) => codes.map((c) => byCode.get(c)!.시군구 || byCode.get(c)!.시도).join('·')

/** "왜 이 위치인가" 한 줄 */
export function reason(e: Effect, byCode: Map<string, Region>): string {
  const parts: string[] = []
  if (e.escaped.length) parts.push(`${names(e.escaped, byCode)} ${e.escaped.length}곳이 이중 취약에서 벗어남`)
  if (e.nearImproved.elderly) parts.push(`65세 이상 ${fmt.int(e.nearImproved.elderly)}명의 최근접 응급의료기관 주행시간 평균 ${e.nearImproved.minAvg.toFixed(1)}분 감소`)
  if (e.ctrImproved.elderly) parts.push(`${fmt.int(e.ctrImproved.elderly)}명의 최근접 센터 주행시간 평균 ${e.ctrImproved.minAvg.toFixed(1)}분 감소`)
  return parts.join(', ')
}

export default function SimPanel(p: Props) {
  const [copied, setCopied] = useState(false)
  const [planN, setPlanN] = useState(3)
  const count = (rs: Iterable<Region>, g: string) => [...rs].filter((r) => r.등급 === g).length
  const changed = p.base.filter((r) => p.now.get(r.코드)!.등급 !== r.등급)
  const elderly = changed.reduce((s, r) => s + r['65세이상인구'], 0)
  const copy = () => navigator.clipboard?.writeText(location.href).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1500) })

  return (
    <div className="sim-panel">
      <div className="panel-head">
        <h2>배치 시뮬레이션</h2>
        <div className="sim-actions">
          <button type="button" onClick={p.onUndo} disabled={!p.canUndo}>되돌리기</button>
          <button type="button" onClick={p.onReset} disabled={isEmpty(p.scenario)}>전체 초기화</button>
          <button type="button" onClick={copy}>{copied ? '복사됨' : '링크 복사'}</button>
        </div>
      </div>
      <p className="notice">가상 시나리오이며, 전국 행정동(섬은 리) 기준점에서 잰 자동차 주행시간을 인구로 가중평균합니다. 새로 추가한 기관은 실제 도로 경로가 없어
        <strong> 직선거리 × 시군구 우회계수로 계산한 근사값</strong>입니다. 판정 기준선은 현재 분포로 고정합니다.
        2SFCA(30분 안 응급실 병상) 보조 지표는 시뮬레이션에 반영되지 않습니다.</p>
      <p className="hint">지도를 누르면 그 위치에 기관을 추가하고, 기관 점을 누르면 정보와 제거 버튼이 뜹니다.
        추가 {p.scenario.added.length}곳 · 제거 {p.scenario.removed.length}곳{p.scenario.upgraded?.length ? ` · 승격 ${p.scenario.upgraded.length}곳` : ''}</p>

      <p className="sim-busy small" role="status">{p.busy ? '재계산 중…' : ''}</p>
      <div className={`sim-counts${p.busy ? ' busy' : ''}`} aria-live="polite" aria-busy={p.busy}>
        {(['이중 취약', '준 이중 취약'] as const).map((g) => {
          const before = count(p.base, g), after = count(p.now.values(), g)
          return (
            <div key={g} className="score">
              <div className="score-label"><span className="swatch" style={{ background: GRADE_COLOR[g] }} /> {g}</div>
              <div className="score-value">{before}<span>곳</span> → {after}<span>곳</span></div>
              <div className="score-rank">{after - before === 0 ? '변화 없음' : `${after - before > 0 ? '+' : ''}${after - before}곳`}</div>
            </div>
          )
        })}
      </div>

      {changed.length > 0 && (
        <>
          <h3>등급이 바뀐 시군구 {changed.length}곳 <span className="muted small">(65세 이상 {fmt.int(elderly)}명, 지도에 점선 테두리)</span></h3>
          <ul className="changed">
            {changed.map((r) => (
              <li key={r.코드}><button type="button" onClick={() => p.onSelect(r.코드)}>{regionName(r)}</button>
                <span className="muted"> {gradeLabel(r.등급)} → </span><strong>{gradeLabel(p.now.get(r.코드)!.등급)}</strong></li>
            ))}
          </ul>
        </>
      )}

      <details className="recs-box" open>
      <summary><h3>추천 위치: 1곳을 더한다면</h3></summary>
      <div className="tabs" role="tablist">
        {(['G007', 'G006'] as const).map((k) => (
          <button type="button" key={k} role="tab" aria-selected={p.recKind === k} className={p.recKind === k ? 'on' : ''} onClick={() => p.onRecKind(k)}>
            {k === 'G007' ? '지역응급의료기관 신설' : '지역응급의료센터 신설·승격'}
          </button>
        ))}
      </div>
      <p className="hint">후보: 행정동 기준점 위치{p.recKind === 'G006' ? ' + 기존 지역기관의 지역센터 승격' : ''}.
        순위: ① 이중 취약에서 벗어나는 시군구 수 ② 65세 이상 인구 가중 주행시간 감소(근사값). 시군구당 1곳.</p>
      {!p.recs ? <p className="muted small">계산 중…</p> : p.recs.length === 0 ? <p className="muted small">개선되는 후보가 없습니다.</p> : (
        <ol className="recs">
          {p.recs.map((e) => {
            const c = e.candidate
            const region = p.now.get(c.code)!
            return (
              <li key={`${c.kind}-${c.hpid ?? c.label}-${c.code}`}>
                <div className="rec-head">
                  <strong>{regionName(region)}</strong>
                  <span className="muted small"> {c.kind === 'upgrade' ? `${c.label} → 지역센터 승격` : `${c.label} 자리에 ${GRADE_SHORT[c.kind]}`}</span>
                  <button type="button" onClick={() => p.onApply(e)}>적용</button>
                </div>
                <p className="small">{reason(e, p.now)}</p>
              </li>
            )
          })}
        </ol>
      )}
      <PlanView plan={p.plan} n={planN} onN={setPlanN} now={p.now} onApply={p.onApplyPlan} />
      </details>
      <p className="hint">후보지는 행정동 행정복지센터(섬은 리) 위치입니다. 신설 후보의 주행시간은 직선거리 × 시군구 우회계수(분/직선km) 근사값이고, 승격은 기존 기관의 등급만 바꿔 그 기관의 실주행시간을 그대로 씁니다(적용해도 같은 값).</p>
    </div>
  )
}

/** 순차 배치 추천: 1곳씩 더할 때마다 가장 효과적인 곳 (data/processed/placement_greedy.json, web/scripts/placement.mjs) */
function PlanView({ plan, n, onN, now, onApply }: { plan?: Placement | null; n: number; onN: (n: number) => void; now: Map<string, Region>; onApply: (s: Scenario) => void }) {
  if (plan === undefined) return <p className="muted small">추천 배치를 불러오는 중…</p>
  if (!plan || !plan.steps.length) return null
  const max = plan.steps.length
  const k = Math.min(n, max)
  const steps = plan.steps.slice(0, k)
  const scenario = planScenario(steps)
  const where = (code: string) => now.get(code)?.시군구 || now.get(code)?.시도
  return (
    <div className="plan">
      <h3>추천 배치 보기 ({k}곳)</h3>
      <div className="subtabs" role="tablist" aria-label="추천 배치 기관 수">
        {Array.from({ length: max }, (_, i) => i + 1).map((v) => (
          <button type="button" key={v} role="tab" aria-selected={v === k} className={v === k ? 'on' : ''} onClick={() => onN(v)}>{v}곳</button>
        ))}
      </div>
      <p className="plan-total">이중 취약 <strong>{plan.base}곳 → {steps[k - 1].double}곳</strong></p>
      <ol className="recs plan-steps">
        {steps.map((s, i) => (
          <li key={i}>
            <div className="rec-head"><strong>{regionName(now.get(s.code)!)}</strong>
              <span className="muted small">{s.kind === 'upgrade' ? `${s.label} → 지역센터 승격` : `${s.label} 자리에 ${GRADE_SHORT[s.kind]}`}</span></div>
            <p className="small">이중 취약 {i ? steps[i - 1].double : plan.base} → {s.double}곳
              {s.escaped.length > 0 && ` (${s.escaped.map(where).join(', ')} 벗어남)`}</p>
          </li>
        ))}
      </ol>
      <div className="sim-actions">
        <button type="button" onClick={() => onApply(scenario)}>이 배치 적용</button>
        <a className="link" href={toQuery(true, scenario)}>공유 링크</a>
      </div>
      <p className="hint">기관 추가가 없는 상태에서 1곳씩 더해 가며 매번 다시 계산한 고정 결과입니다(순서: 이중 취약 감소 수, 동률이면 주행시간이 줄어드는 인구).
        적용하면 지금 시나리오를 바꿉니다. 후보는 가정 위치이고, 병상 공급·실제 인허가·재정 제약은 반영하지 않은 의사결정 지원용입니다.</p>
    </div>
  )
}

export function AddChooser({ x, y, onPick, onCancel }: { x: number; y: number; onPick: (g: 'G007' | 'G006' | 'G001') => void; onCancel: () => void }) {
  return (
    <div className="chooser" style={{ left: Math.min(x, window.innerWidth - 200), top: y + 8 }} role="dialog" aria-label="추가할 기관 등급">
      <div className="small muted">이 위치에 추가</div>
      {(['G007', 'G006', 'G001'] as const).map((g) => <button type="button" key={g} onClick={() => onPick(g)}>{GRADE_SHORT[g]}</button>)}
      <button type="button" className="link" onClick={onCancel}>취소</button>
    </div>
  )
}
