import { useState } from 'react'
import { isIsland, regionName, type Region } from '../data'
import { CLUSTER_COLOR, GRADE_COLOR, fmt, isBothVulnerable, sfcaCuts } from '../metrics'
import { districtHints, listRegions, type District } from '../search'
import { textOn } from '../theme'

type Key = '합산' | '등급' | '시도' | '시군구' | '접근성점수' | '복지점수' | '클러스터'
const COLS: { key: Key; label: string; num?: boolean }[] = [
  { key: '등급', label: '등급' },
  { key: '시군구', label: '시군구' },
  { key: '접근성점수', label: '접근성', num: true },
  { key: '복지점수', label: '복지', num: true },
  { key: '합산', label: '합산', num: true },
  { key: '클러스터', label: '유형', num: true },
]
const PAGE = 10
const value = (r: Region, k: Key): number | string =>
  k === '합산' ? r.접근성점수 + r.복지점수 : k === '등급' ? (r.등급 === '이중 취약' ? 0 : 1) : k === '시군구' ? regionName(r) : r[k]

interface Props { regions: Region[]; selected: string | null; onSelect: (code: string) => void; sim?: boolean; districts: District[] }

/** 시군구 목록. 기본은 이중·준 이중 취약만(필터를 끄면 229곳 전체), 검색은 필터와 무관하게 전체에서. 머리글 정렬, 처음 10개 + 더보기, 행 클릭으로 지도 선택 */
export default function DoubleTable({ regions, selected, onSelect, sim, districts }: Props) {
  const [sort, setSort] = useState<{ key: Key; desc: boolean }>({ key: '합산', desc: true })
  const [q, setQ] = useState('')
  const [all, setAll] = useState(false)
  const [bothOnly, setBothOnly] = useState(false)
  const [gradeOnly, setGradeOnly] = useState(true)
  const cuts = sfcaCuts(regions)
  const both = (r: Region) => !sim && isBothVulnerable(r, cuts) // 시뮬레이션 중에는 2SFCA 를 다시 계산하지 않아 표시 안 함
  const nBoth = regions.filter(both).length
  const byCode = new Map(regions.map((r) => [r.코드, r]))
  const hints = districtHints(q, districts, byCode)
  const rows = listRegions(regions, { q, gradeOnly, bothOnly, both })
    .sort((a, b) => {
      const va = value(a, sort.key), vb = value(b, sort.key)
      const c = typeof va === 'number' && typeof vb === 'number' ? va - vb : String(va).localeCompare(String(vb), 'ko')
      return (sort.desc ? -c : c) || (b.접근성점수 + b.복지점수) - (a.접근성점수 + a.복지점수) // 동률이면 합산 높은 순
    })
  const shown = all || q ? rows : rows.slice(0, PAGE)
  const toggle = (key: Key) => setSort((s) => ({ key, desc: s.key === key ? !s.desc : !['시군구', '등급'].includes(key) }))
  const n = (g: string) => regions.filter((r) => r.등급 === g).length

  return (
    <div className="list">
      <div className="list-head">
        <input type="search" placeholder="시군구 검색" value={q} onChange={(e) => setQ(e.target.value)} aria-label="시군구 검색" />
        <span className="muted small">이중 {n('이중 취약')} · 준 이중 {n('준 이중 취약')}</span>
        <label className="small both-filter"><input type="checkbox" checked={gradeOnly} onChange={(e) => setGradeOnly(e.target.checked)} /> 이중·준 이중만</label>
        {!sim && <label className="small both-filter"><input type="checkbox" checked={bothOnly} onChange={(e) => setBothOnly(e.target.checked)} /> 거리·병상 모두 취약만 ({nBoth})</label>}
      </div>
      <p className="small muted list-count" aria-live="polite">전체 {regions.length}곳 중 <strong>{rows.length}곳</strong> 표시
        {q ? ' · 검색은 필터와 무관하게 전체에서 찾습니다' : (gradeOnly || bothOnly) ? ' · 필터 적용 중' : ''}</p>
      {hints.length > 0 && (
        <ul className="district-hints small">
          {hints.map((h) => (
            <li key={h.name}>{h.name}는 <button type="button" className="link" onClick={() => onSelect(h.parent.코드)}>{regionName(h.parent)}</button>에 포함되어 함께 분석합니다(일반구는 상위 시 단위).</li>
          ))}
        </ul>
      )}
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              {COLS.map((c) => (
                <th key={c.key} scope="col" className={c.num ? 'num' : ''}
                  aria-sort={sort.key === c.key ? (sort.desc ? 'descending' : 'ascending') : 'none'}>
                  <button type="button" onClick={() => toggle(c.key)}>{c.label}{sort.key === c.key ? (sort.desc ? ' ▼' : ' ▲') : ''}</button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {shown.map((r) => (
              <tr key={r.코드} className={r.코드 === selected ? 'selected' : ''} tabIndex={0}
                onClick={() => onSelect(r.코드)} onKeyDown={(e) => e.key === 'Enter' && onSelect(r.코드)}>
                <td><span className="grade-pill" style={{ background: GRADE_COLOR[r.등급], color: textOn(GRADE_COLOR[r.등급]) }}>{r.등급 === '이중 취약' ? '이중' : r.등급 ? '준' : '-'}</span></td>
                <td>{regionName(r)}{isIsland(r) && <span className="island-mark" title="섬 읍·면을 리(섬) 단위로 계산"> ◆</span>}
                  {both(r) && <span className="both-mark" title="거리·병상 모두 취약: 이중 취약이면서 2SFCA(30분 안 응급실 병상) 하위 25%"> ●</span>}</td>
                <td className="num">{fmt.score(r.접근성점수)}</td>
                <td className="num">{fmt.score(r.복지점수)}</td>
                <td className="num">{(r.접근성점수 + r.복지점수).toFixed(1)}</td>
                <td className="num"><span className="swatch sm" style={{ background: CLUSTER_COLOR[r.클러스터] }} />{r.클러스터}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!q && rows.length > PAGE && (
        <button type="button" className="more" onClick={() => setAll(!all)}>{all ? '상위 10개만 보기' : `더보기 (${rows.length - PAGE}곳 더)`}</button>
      )}
      <ul className="hint table-key">
        <li>◆ 섬 읍·면을 리(섬) 단위로 계산</li>
        <li><span className="both-mark">●</span> 거리·병상 모두 취약(이중 취약 + 2SFCA 하위 25%)</li>
        <li>행을 누르면 지도에서 선택됩니다</li>
      </ul>
    </div>
  )
}
