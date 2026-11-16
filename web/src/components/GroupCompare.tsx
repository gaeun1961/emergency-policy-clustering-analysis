import { memo } from 'react'
import { GROUPS, groupMedians } from '../analysis'
import type { Region } from '../data'
import { GRADE_COLOR } from '../metrics'

const NAME = (g: string) => g || '해당 없음'

/** 지표별 세 그룹 중앙값 점 그래프. 줄마다 0 ~ 가장 큰 중앙값의 1.15배 */
function GroupCompare({ regions }: { regions: Region[] }) {
  const { counts, rows } = groupMedians(regions)
  const section = (used: boolean) => rows.filter((r) => r.used === used).map((r) => {
    const max = Math.max(...r.medians.filter(Number.isFinite)) * 1.15 || 1
    return (
      <div className="gc-row" key={r.key}>
        <span className="gc-label">{r.label}</span>
        <span className="gc-strip" aria-hidden="true">
          {[...GROUPS].reverse().map((g, i) => {
            const v = r.medians[GROUPS.length - 1 - i]
            return Number.isFinite(v) && (
              <i key={g} className="gc-dot" style={{ left: `${(v / max) * 100}%`, background: GRADE_COLOR[g] }} title={`${NAME(g)} 중앙값 ${r.text(v)}`} />
            )
          })}
        </span>
        <span className="gc-values">{r.medians.map((v, i) => <span key={i}>{Number.isFinite(v) ? r.text(v) : '-'}</span>)}</span>
      </div>
    )
  })
  return (
    <section className="group-compare" aria-label="등급별 지표 중앙값 비교">
      <h3>등급별 지표 비교 <span className="muted small">시군구 중앙값</span></h3>
      <p className="gc-legend small">
        {GROUPS.map((g, i) => <span key={g}><i style={{ background: GRADE_COLOR[g] }} />{NAME(g)} {counts[i]}곳</span>)}
      </p>
      <p className="gc-head small">판정에 쓴 지표</p>
      {section(true)}
      <p className="gc-head small">판정에 쓰지 않은 검증 지표</p>
      {section(false)}
      <p className="hint">오른쪽 숫자는 왼쪽부터 이중 취약, 준 이중 취약, 해당 없음 순서입니다. 판정에 쓰지 않은 기초연금·기초생활수급자 비율도 이중 취약에서 높게 나와 판정이 어르신 빈곤과 함께 움직임을 보여 줍니다. 응급실 병상은 적을수록 취약합니다.</p>
    </section>
  )
}

export default memo(GroupCompare)
