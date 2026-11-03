import { useState } from 'react'
import { isIsland, type Region } from '../data'
import { CLUSTER_COLOR, fmt } from '../metrics'

type Key = '합산점수' | '시도' | '시군구' | '접근성점수' | '복지점수' | '클러스터'
const COLS: { key: Key; label: string; num?: boolean }[] = [
  { key: '시도', label: '시도' },
  { key: '시군구', label: '시군구' },
  { key: '접근성점수', label: '접근성 취약', num: true },
  { key: '복지점수', label: '복지 취약', num: true },
  { key: '합산점수', label: '합산', num: true },
  { key: '클러스터', label: '유형', num: true },
]

interface Props { regions: Region[]; selected: string | null; onSelect: (code: string) => void }

/** 이중 취약지역 표. 머리글 클릭으로 정렬, 행 클릭으로 지도 선택 */
export default function DoubleTable({ regions, selected, onSelect }: Props) {
  const [sort, setSort] = useState<{ key: Key; desc: boolean }>({ key: '합산점수', desc: true })
  const rows = regions.filter((r) => r.등급 === '이중 취약').sort((a, b) => {
    const va = a[sort.key] ?? 0
    const vb = b[sort.key] ?? 0
    const c = typeof va === 'number' && typeof vb === 'number' ? va - vb : String(va).localeCompare(String(vb), 'ko')
    return sort.desc ? -c : c
  })
  const toggle = (key: Key) => setSort((s) => ({ key, desc: s.key === key ? !s.desc : key !== '시도' && key !== '시군구' }))

  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th scope="col">#</th>
            {COLS.map((c) => (
              <th key={c.key} scope="col" className={c.num ? 'num' : ''}
                aria-sort={sort.key === c.key ? (sort.desc ? 'descending' : 'ascending') : 'none'}>
                <button onClick={() => toggle(c.key)}>
                  {c.label}{sort.key === c.key ? (sort.desc ? ' ▼' : ' ▲') : ''}
                </button>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={r.코드} className={r.코드 === selected ? 'selected' : ''} tabIndex={0}
              onClick={() => onSelect(r.코드)} onKeyDown={(e) => e.key === 'Enter' && onSelect(r.코드)}>
              <td className="num muted">{i + 1}</td>
              <td>{r.시도}</td>
              <td>{r.시군구}{isIsland(r) && <span className="island-mark" title="읍면 인구가중 기준점"> ◆</span>}</td>
              <td className="num">{fmt.score(r.접근성점수)}</td>
              <td className="num">{fmt.score(r.복지점수)}</td>
              <td className="num">{(r.합산점수 ?? 0).toFixed(1)}</td>
              <td className="num"><span className="swatch sm" style={{ background: CLUSTER_COLOR[r.클러스터] }} />{r.클러스터}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="hint">◆ 읍면 인구가중 기준점(섬 지역)</p>
    </div>
  )
}
