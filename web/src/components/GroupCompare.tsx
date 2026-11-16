import { memo } from 'react'
import { GROUPS, groupMedians } from '../analysis'
import type { Region } from '../data'
import { GRADE_COLOR } from '../metrics'
import { strip } from '../report'

const NAME = (g: string) => g || '해당 없음'

/** 지표별 세 그룹 중앙값 점 그래프. 보고서 지표 위치 차트(report.strip)와 같은 축: 전국 229곳 분포, 오른쪽일수록 취약, 취약 쪽 25% 음영, 전국 중앙값 선 */
function GroupCompare({ regions }: { regions: Region[] }) {
  const { counts, rows } = groupMedians(regions)
  const section = (used: boolean) => rows.filter((r) => r.used === used).map((r) => {
    const all = regions.map((x) => x[r.key] as number)
    const at = (v: number) => strip(all, v, r.worse)
    const base = at(all[0])
    return (
      <div className="gc-row" key={r.key}>
        <span className="gc-label">{r.label}</span>
        <span className="gc-strip" aria-hidden="true">
          <b className="gc-zone" style={{ left: `${base.cut * 100}%` }} />
          <b className="gc-med" style={{ left: `${base.median * 100}%` }} />
          {[...GROUPS].reverse().map((g, i) => {
            const v = r.medians[GROUPS.length - 1 - i]
            return Number.isFinite(v) && (
              <i key={g} className="gc-dot" style={{ left: `${at(v).pos * 100}%`, background: GRADE_COLOR[g] }} title={`${NAME(g)} 중앙값 ${r.text(v)}`} />
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
        <span><i className="gc-key-med" />전국 중앙값</span><span><i className="gc-key-zone" />취약 쪽 25%</span>
      </p>
      <p className="gc-head small">판정에 쓴 지표</p>
      {section(true)}
      <p className="gc-head small">판정에 쓰지 않은 검증 지표</p>
      {section(false)}
      <p className="hint">가로축은 전국 229곳의 분포이고 오른쪽일수록 취약합니다(30분 내 기관·병상은 적을수록 오른쪽). 오른쪽 숫자는 왼쪽부터 이중 취약, 준 이중 취약, 해당 없음 순서입니다. 판정에 쓰지 않은 기초연금·기초생활수급자 비율도 이중 취약에서 높게 나와 판정이 어르신 빈곤과 함께 움직임을 보여 줍니다.</p>
    </section>
  )
}

export default memo(GroupCompare)
