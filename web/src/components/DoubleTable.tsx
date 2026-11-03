import { useState } from 'react'
import { isIsland, regionName, type Region } from '../data'
import { CLUSTER_COLOR, GRADE_COLOR, fmt } from '../metrics'
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

interface Props { regions: Region[]; selected: string | null; onSelect: (code: string) => void }

/** 이중·준 이중 취약 목록. 머리글 정렬, 이름 검색, 처음 10개 + 더보기, 행 클릭으로 지도 선택 */
export default function DoubleTable({ regions, selected, onSelect }: Props) {
  const [sort, setSort] = useState<{ key: Key; desc: boolean }>({ key: '합산', desc: true })
  const [q, setQ] = useState('')
  const [all, setAll] = useState(false)
  const rows = regions
    .filter((r) => r.등급 && regionName(r).replace(/\s/g, '').includes(q.replace(/\s/g, '')))
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
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              {COLS.map((c) => (
                <th key={c.key} scope="col" className={c.num ? 'num' : ''}
                  aria-sort={sort.key === c.key ? (sort.desc ? 'descending' : 'ascending') : 'none'}>
                  <button onClick={() => toggle(c.key)}>{c.label}{sort.key === c.key ? (sort.desc ? ' ▼' : ' ▲') : ''}</button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {shown.map((r) => (
              <tr key={r.코드} className={r.코드 === selected ? 'selected' : ''} tabIndex={0}
                onClick={() => onSelect(r.코드)} onKeyDown={(e) => e.key === 'Enter' && onSelect(r.코드)}>
                <td><span className="grade-pill" style={{ background: GRADE_COLOR[r.등급], color: textOn(GRADE_COLOR[r.등급]) }}>{r.등급 === '이중 취약' ? '이중' : '준'}</span></td>
                <td>{regionName(r)}{isIsland(r) && <span className="island-mark" title="읍면 인구가중 기준점"> ◆</span>}</td>
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
        <button className="more" onClick={() => setAll(!all)}>{all ? '상위 10개만 보기' : `더보기 (${rows.length - PAGE}곳 더)`}</button>
      )}
      <p className="hint">◆ 읍면 인구가중 기준점(섬 지역) · 행을 누르면 지도에서 선택됩니다</p>
    </div>
  )
}
