import { isIsland, quantile, regionName, type Region } from '../data'
import { CLUSTER_COLOR, CLUSTER_DESC, GRADE_COLOR, fmt } from '../metrics'
import { textOn } from '../theme'

interface Props { region: Region | null; total: number; regions: Region[] }

/** 전국 중앙값 대비 미니 막대: 선택 지역(막대)과 전국 중앙값(세로선) */
const COMPARE: { key: keyof Region; label: string; format: (v: number) => string }[] = [
  { key: '최근접_응급의료기관_km', label: '최근접 응급의료기관', format: fmt.km },
  { key: '최근접_권역지역센터_km', label: '최근접 권역·지역센터', format: fmt.km },
  { key: '고령인구비율', label: '고령인구비율', format: fmt.pct },
  { key: '독거노인비율', label: '독거노인비율', format: fmt.pct },
]

function MedianBars({ r, regions }: { r: Region; regions: Region[] }) {
  return (
    <div className="compare">
      <h3>전국 중앙값 대비 <span className="muted small">(막대: {r.시군구 || r.시도}, 세로선: 전국 {regions.length}곳 중앙값)</span></h3>
      {COMPARE.map(({ key, label, format }) => {
        const v = r[key] as number
        const med = quantile(regions.map((x) => x[key] as number), 0.5)
        const max = Math.max(v, med) * 1.15 || 1
        const ratio = med ? v / med : 0
        return (
          <div key={key} className="cmp-row">
            <div className="cmp-label"><span>{label}</span>
              <span className="cmp-val"><strong>{format(v)}</strong> <span className="muted">· 중앙값 {format(med)}</span>
                {ratio >= 1.05 || ratio <= 0.95 ? <span className="cmp-ratio"> ×{ratio.toFixed(ratio >= 10 ? 0 : 1)}</span> : null}</span>
            </div>
            <div className="cmp-track" role="img" aria-label={`${label} ${format(v)}, 전국 중앙값 ${format(med)}`}>
              <div className="cmp-bar" style={{ width: `${(v / max) * 100}%` }} />
              <div className="cmp-med" style={{ left: `${(med / max) * 100}%` }} />
            </div>
          </div>
        )
      })}
    </div>
  )
}

export function IslandBadge() {
  return (
    <span className="badge island" title="섬 지역은 군청 한 곳 대신 읍면사무소별 거리를 읍면 인구로 가중평균했다">
      읍면 인구가중 기준점
    </span>
  )
}

export default function DetailPanel({ region: r, total, regions }: Props) {
  if (!r) return <div className="detail"><p className="muted">지도, 산점도, 표에서 시군구를 선택하세요.</p></div>

  const cards: [string, string][] = [
    ['총인구', `${fmt.int(r.총인구)}명`],
    ['고령인구비율', fmt.pct(r.고령인구비율)],
    ['독거노인비율', fmt.pct(r.독거노인비율)],
    ['장애인비율', fmt.pct(r.장애인비율)],
    ['최근접 응급의료기관', fmt.km(r.최근접_응급의료기관_km)],
    ['최근접 권역·지역센터', fmt.km(r.최근접_권역지역센터_km)],
    ['반경 30km 응급의료기관', `${r.반경30km_기관수.toFixed(r.반경30km_기관수 % 1 ? 1 : 0)}곳`],
  ]
  return (
    <div className="detail" aria-live="polite">
      <div className="detail-head">
        <h2>{regionName(r)}</h2>
        <div className="badges">
          {r.등급 && <span className="badge" style={{ background: GRADE_COLOR[r.등급], color: textOn(GRADE_COLOR[r.등급]) }}>{r.등급}</span>}
          {isIsland(r) && <IslandBadge />}
        </div>
      </div>

      <div className="scores">
        {([['응급의료 접근성 취약', r.접근성점수, r.접근성순위], ['복지 취약', r.복지점수, r.복지순위]] as const).map(([label, score, rank]) => (
          <div key={label} className="score">
            <div className="score-label">{label}</div>
            <div className="score-value">{fmt.score(score)}<span>점</span></div>
            <div className="score-rank">{total}곳 중 <strong>{rank}위</strong></div>
            <div className="bar"><div style={{ width: `${score}%` }} /></div>
          </div>
        ))}
      </div>
      <p className="hint">순위는 취약한 순서(1위가 가장 취약)</p>

      <dl className="cards">
        {cards.map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}
      </dl>

      <div className="cluster">
        <span className="swatch" style={{ background: CLUSTER_COLOR[r.클러스터] }} />
        <div>
          <strong>유형 {r.클러스터}. {r.클러스터라벨}</strong>
          <p>{CLUSTER_DESC[r.클러스터]}</p>
        </div>
      </div>

      <MedianBars r={r} regions={regions} />
    </div>
  )
}
