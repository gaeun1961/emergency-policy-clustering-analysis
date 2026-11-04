import { useEffect, useRef } from 'react'
import type { Region } from '../data'
import { fmt } from '../metrics'
import type { EmdData, EmdRow } from '../sim/emd'
import { T } from '../theme'

/** 이보다 인구가 적은 행정동은 비율이 불안정하다고 안내 */
export const SMALL_POP = 500
/** 구간 색: 접근성 좋은 순 -> 취약 순으로 진하게 (램프 2~5단계) */
export const bandColor = (band: number) => T.ramp[band + 1]

interface Props {
  region: Region
  rows: EmdRow[] | null
  data: EmdData | null
  selected: string | null
  onSelect: (code: string) => void
  cap?: number
}

const minText = (v: number, raw: number | undefined) => fmt.minAtLeast(v, raw ?? v)
/** 가까운 순 기관: "이름 N분 (주민 P%)", 이용 0%는 대안으로 흐리게 "+N분" (시군구 상세와 같은 규칙) */
const RankText = ({ items }: { items: EmdRow['em'] }) => (
  <>
    {items.map((x, i) => (
      <span key={x.f.hpid} className={x.alt ? 'alt' : ''}>
        {i > 0 && ' · '}{x.f.기관명} {x.capped ? `≥ ${fmt.min(x.min)}` : fmt.min(x.min)}
        {x.alt ? ` (대안 +${fmt.min(x.plus)})` : ` (주민 ${fmt.pct(x.share)}${x.useMin !== null && Math.abs(x.useMin - x.min) > 0.05 ? `, 이용 주민 ${x.useCapped ? '≥ ' : ''}${fmt.min(x.useMin)}` : ''})`}
      </span>
    ))}
  </>
)

/** 시군구 상세의 읍면동 보기: 전국 행정동 기준 접근성 구간으로 색칠한 지도와 목록. 판정은 시군구 단위 그대로 */
export default function EmdPanel({ region, rows, data, selected, onSelect, cap }: Props) {
  const listRef = useRef<HTMLOListElement>(null)
  useEffect(() => { // 지도에서 고른 행정동을 목록에서 보이게
    listRef.current?.querySelector(`[data-code="${selected}"]`)?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }, [selected])
  if (!rows || !data) return <p className="muted small">읍면동 경계·지표를 불러오는 중…</p>

  const worst = data.구간.length - 1
  const sorted = [...rows].sort((a, b) => b.점수 - a.점수)
  const low = rows.filter((r) => r.구간 === worst)
  const pop = rows.reduce((s, r) => s + r.인구, 0)
  const lowPop = low.reduce((s, r) => s + r.인구, 0)
  return (
    <div className="emd-panel">
      <p className={`emd-summary${region.등급 === '이중 취약' ? ' strong' : ''}`}>
        읍면동 {rows.length}곳 중 <strong>전국 접근성 하위 25% {low.length}곳</strong> (주민 {fmt.pct(pop ? lowPop / pop : 0)})
        {region.등급 === '이중 취약' && ' · 이중 취약 시군구'}
      </p>
      <ul className="legend emd-legend" aria-label="읍면동 접근성 구간">
        {data.구간.map((b, i) => <li key={b}><span className="swatch" style={{ background: bandColor(i) }} />{b}</li>)}
      </ul>
      <p className="hint">전국 행정동 3,557곳 기준 접근성 구간(최근접 응급의료기관·센터 주행시간, 30분 내 기관 수의 백분위 평균)입니다.
        시군구 등급 판정은 바뀌지 않습니다. 독거노인·장애인 비율은 읍면동 통계가 없어 시군구 값만 씁니다.
        고령 비율은 10세 단위 인구에서 60대를 시군구 비율로 나눈 추정치입니다.</p>
      <ol className="emd-list" ref={listRef}>
        {sorted.map((r) => (
          <li key={r.code} data-code={r.code} className={r.code === selected ? 'sel' : ''}>
            <button className="emd-head" onClick={() => onSelect(r.code)}>
              <span className="swatch" style={{ background: bandColor(r.구간) }} />
              <strong>{r.이름}</strong>
              <span className="muted small">{data.구간[r.구간]}</span>
            </button>
            <div className="emd-cells small">
              <span>인구 {fmt.int(r.인구)}명{r.인구 < SMALL_POP && <em className="warn"> · 인구가 적어 비율 불안정</em>}</span>
              <span>고령 {fmt.pct(r.고령인구비율)}</span>
              <span>응급의료기관 {minText(r.metrics.최근접_응급의료기관_분, r.metrics.최근접_응급의료기관_분_원값)}</span>
              <span>센터 {minText(r.metrics.최근접_권역지역센터_분, r.metrics.최근접_권역지역센터_분_원값)}</span>
            </div>
            <div className="small emd-near">가까운 기관: <RankText items={r.em} /></div>
            <div className="small emd-near">센터: <RankText items={r.ctr} />
              {r.근사반영비율 > 0 && <span className="muted"> · 근사값 반영 {fmt.pct(r.근사반영비율)}</span>}</div>
            {r.li.length > 0 && (
              <details className="emd-li">
                <summary className="small">리(섬)별 {r.li.length}곳</summary>
                <table className="small">
                  <thead><tr><th>리</th><th>인구</th><th>고령</th><th>응급의료기관</th><th>센터</th></tr></thead>
                  <tbody>
                    {[...r.li].sort((a, b) => b.metrics.최근접_권역지역센터_분 - a.metrics.최근접_권역지역센터_분).map((l) => (
                      <tr key={l.리}>
                        <td>{l.리}</td><td>{fmt.int(l.인구)}</td><td>{l.고령인구비율 === null ? '-' : fmt.pct(l.고령인구비율)}</td>
                        <td>{minText(l.metrics.최근접_응급의료기관_분, l.metrics.최근접_응급의료기관_분_원값)}</td>
                        <td>{minText(l.metrics.최근접_권역지역센터_분, l.metrics.최근접_권역지역센터_분_원값)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </details>
            )}
          </li>
        ))}
      </ol>
      {cap !== undefined && <p className="hint">도로로 닿지 않는 섬 등은 직선거리 × 우회계수 근사값이고, {fmt.min(cap)}에서 잘라 "≥"로 표시합니다.</p>}
    </div>
  )
}
