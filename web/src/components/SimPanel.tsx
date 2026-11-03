import { useState } from 'react'
import { regionName, type Region } from '../data'
import { GRADE_COLOR, fmt } from '../metrics'
import type { Effect } from '../sim/recommend'
import { GRADE_SHORT, type Scenario } from '../sim/scenario'

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
}

const gradeLabel = (g: string) => g || '해당 없음'
const names = (codes: string[], byCode: Map<string, Region>) => codes.map((c) => byCode.get(c)!.시군구 || byCode.get(c)!.시도).join('·')

/** "왜 이 위치인가" 한 줄 */
export function reason(e: Effect, byCode: Map<string, Region>): string {
  const parts: string[] = []
  if (e.escaped.length) parts.push(`${names(e.escaped, byCode)} ${e.escaped.length}곳이 이중 취약에서 벗어남`)
  if (e.nearImproved.elderly) parts.push(`65세 이상 ${fmt.int(e.nearImproved.elderly)}명의 최근접 응급의료기관 거리 평균 ${e.nearImproved.kmAvg.toFixed(1)}km 감소`)
  if (e.ctrImproved.elderly) parts.push(`${fmt.int(e.ctrImproved.elderly)}명의 최근접 센터 거리 평균 ${e.ctrImproved.kmAvg.toFixed(1)}km 감소`)
  return parts.join(', ')
}

export default function SimPanel(p: Props) {
  const [copied, setCopied] = useState(false)
  const count = (rs: Iterable<Region>, g: string) => [...rs].filter((r) => r.등급 === g).length
  const changed = p.base.filter((r) => p.now.get(r.코드)!.등급 !== r.등급)
  const elderly = changed.reduce((s, r) => s + r['65세이상인구'], 0)
  const copy = () => navigator.clipboard?.writeText(location.href).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1500) })

  return (
    <div className="sim-panel" aria-live="polite">
      <div className="panel-head">
        <h2>배치 시뮬레이션</h2>
        <div className="sim-actions">
          <button onClick={p.onUndo} disabled={!p.canUndo}>되돌리기</button>
          <button onClick={p.onReset} disabled={!p.scenario.added.length && !p.scenario.removed.length}>전체 초기화</button>
          <button onClick={copy}>{copied ? '복사됨' : '링크 복사'}</button>
        </div>
      </div>
      <p className="notice">가상 시나리오이며 시군구청(섬 지역은 읍면사무소) 기준 직선거리로 계산합니다. 판정 기준선은 현재 분포로 고정합니다.</p>
      <p className="hint">지도를 누르면 그 위치에 기관을 추가하고, 기존 기관 점을 누르면 제거합니다.
        추가 {p.scenario.added.length}곳 · 제거 {p.scenario.removed.length}곳</p>

      <div className="sim-counts">
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
              <li key={r.코드}><button onClick={() => p.onSelect(r.코드)}>{regionName(r)}</button>
                <span className="muted"> {gradeLabel(r.등급)} → </span><strong>{gradeLabel(p.now.get(r.코드)!.등급)}</strong></li>
            ))}
          </ul>
        </>
      )}

      <details className="recs-box" open>
      <summary><h3>추천 위치: 1곳을 더한다면</h3></summary>
      <div className="tabs" role="tablist">
        {(['G007', 'G006'] as const).map((k) => (
          <button key={k} role="tab" aria-selected={p.recKind === k} className={p.recKind === k ? 'on' : ''} onClick={() => p.onRecKind(k)}>
            {k === 'G007' ? '지역응급의료기관 신설' : '지역응급의료센터 신설·승격'}
          </button>
        ))}
      </div>
      <p className="hint">후보: 시군구 기준점 위치{p.recKind === 'G006' ? ' + 기존 지역기관의 지역센터 승격' : ''}.
        순위: ① 이중 취약에서 벗어나는 시군구 수 ② 65세 이상 인구 가중 거리 감소. 시군구당 1곳.</p>
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
                  <button onClick={() => p.onApply(e)}>적용</button>
                </div>
                <p className="small">{reason(e, p.now)}</p>
              </li>
            )
          })}
        </ol>
      )}
      </details>
      <p className="hint">후보지는 시군구청 위치이며, 거리는 시군구청 기준으로 측정됩니다. 그래서 시군구청에 놓는 후보가 유리하게 나오고, 시군구청에서 떨어진 곳의 효과는 과소평가될 수 있습니다.</p>
    </div>
  )
}

export function AddChooser({ x, y, onPick, onCancel }: { x: number; y: number; onPick: (g: 'G007' | 'G006' | 'G001') => void; onCancel: () => void }) {
  return (
    <div className="chooser" style={{ left: Math.min(x, window.innerWidth - 200), top: y + 8 }} role="dialog" aria-label="추가할 기관 등급">
      <div className="small muted">이 위치에 추가</div>
      {(['G007', 'G006', 'G001'] as const).map((g) => <button key={g} onClick={() => onPick(g)}>{GRADE_SHORT[g]}</button>)}
      <button className="link" onClick={onCancel}>취소</button>
    </div>
  )
}
