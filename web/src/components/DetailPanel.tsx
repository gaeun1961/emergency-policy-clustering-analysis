import { isIsland, regionName, type Region } from '../data'
import { CLUSTER_COLOR, CLUSTER_DESC, GRADE_COLOR, fmt } from '../metrics'

interface Props { region: Region | null; total: number }

export function IslandBadge() {
  return (
    <span className="badge island" title="섬 지역은 군청 한 곳 대신 읍면사무소별 거리를 읍면 인구로 가중평균했다">
      읍면 인구가중 기준점
    </span>
  )
}

export default function DetailPanel({ region: r, total }: Props) {
  if (!r) return <section className="panel detail"><p className="muted">지도, 산점도, 표에서 시군구를 선택하세요.</p></section>

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
    <section className="panel detail" aria-live="polite">
      <div className="detail-head">
        <h2>{regionName(r)}</h2>
        <div className="badges">
          {r.등급 && <span className="badge" style={{ background: GRADE_COLOR[r.등급], color: '#fff' }}>{r.등급}</span>}
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
    </section>
  )
}
