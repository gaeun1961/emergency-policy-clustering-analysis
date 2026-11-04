import { isIsland, quantile, regionName, type Region } from '../data'
import { CLUSTER_COLOR, GRADE_COLOR, clusterDesc, fmt } from '../metrics'
import type { RankedFacility } from '../sim/model'
import { textOn } from '../theme'
import { FacilityLines } from './FacilityInfo'

interface Props { region: Region | null; total: number; regions: Region[]; usage?: RegionUsage | null; cap?: number; sim?: boolean }

/** 근사값 반영 인구 비율이 이 이상이면 배지 */
const APPROX_BADGE = 0.05

/** 전국 중앙값 대비 미니 막대: 선택 지역(막대)과 전국 중앙값(세로선) */
const COMPARE: { key: keyof Region; label: string; format: (v: number) => string }[] = [
  { key: '최근접_응급의료기관_분', label: '최근접 응급의료기관 (자동차)', format: fmt.min },
  { key: '최근접_권역지역센터_분', label: '최근접 권역·지역센터 (자동차)', format: fmt.min },
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

/** 기관 목록: 주민 평균 주행시간 가까운 순 + 이용 주민 비율. 이용 0%는 대안(흐리게, 1위 대비 +N분). App 에서 계산해 넘김 (지도 강조와 같은 목록) */
function RankList({ title, items }: { title: string; items: RankedFacility[] }) {
  return (
    <>
      <h3>{title}</h3>
      <ol>
        {items.map(({ f, share, alt, plus, min, km, approx, capped }) => (
          <li key={f.hpid} className={alt ? 'alt' : ''}>
            <div className="nearest-km">{capped ? `≥ ${fmt.min(min)}` : fmt.min(min)}
              <div className="muted small">{alt ? <>대안 +{fmt.min(plus)}</> : <>주민 {fmt.pct(share)}</>}</div></div>
            <div>
              <FacilityLines f={f} />
              <div className="small">주민 평균 자동차 {capped ? `≥ ${fmt.min(min)} (근사)` : fmt.min(min)}{approx && !capped && <span className="muted"> (일부 근사)</span>} · 직선 {fmt.km(km)}
                {alt ? <span className="muted"> · 이 기관이 가장 가까운 주민 없음</span> : <> · 이 기관이 가장 가까운 주민 {fmt.pct(share)}</>}</div>
            </div>
          </li>
        ))}
      </ol>
    </>
  )
}

export interface RegionUsage { em: RankedFacility[]; ctr: RankedFacility[] }
function Usages({ usage, cap, factor }: { usage: RegionUsage; cap?: number; factor: number }) {
  return (
    <div className="nearest">
      <RankList title="가까운 응급의료기관" items={usage.em} />
      <RankList title="가까운 권역·지역응급의료센터" items={usage.ctr} />
      <p className="hint">시군구 행정동 기준점(섬 읍·면은 리)에서 잰 OSRM <strong>자동차 주행시간</strong>을 주민 수로 평균해 가까운 순으로 보여줍니다(시군구 밖 기관 포함, 지도에 테두리로 강조).
        "주민 %"는 그 기관이 가장 가까운 주민의 비율이고, 0%인 기관은 대안으로 흐리게 표시하고 1위보다 몇 분 더 걸리는지 적었습니다.
        실시간 교통·구급차 우선통행은 반영하지 않습니다. 도로로 닿지 않거나 가까운 10곳 밖이면 직선거리 × 우회계수({factor.toFixed(2)}분/km) 근사값이고,
        {cap !== undefined && <> 근사값은 {fmt.min(cap)}에서 잘라 "≥"로 표시합니다.</>}</p>
    </div>
  )
}

export function IslandBadge() {
  return (
    <span className="badge island" title="면사무소와 다른 섬에 사람이 사는 읍·면은 리(섬)별 좌표·인구로 거리를 가중평균했다">
      섬 읍·면 리 단위 반영
    </span>
  )
}

export default function DetailPanel({ region: r, total, regions, usage, cap, sim }: Props) {
  if (!r) return <div className="detail"><p className="muted">지도, 산점도, 표에서 시군구를 선택하세요.</p></div>

  const cards: [string, string][] = [
    ['총인구', `${fmt.int(r.총인구)}명`],
    ['고령인구비율', fmt.pct(r.고령인구비율)],
    ['독거노인비율', fmt.pct(r.독거노인비율)],
    ['장애인비율', fmt.pct(r.장애인비율)],
    ['최근접 응급의료기관', fmt.minAtLeast(r.최근접_응급의료기관_분, r.최근접_응급의료기관_분_원값) + (sim ? '' : ` · 직선 ${fmt.km(r.최근접_응급의료기관_km)}`)],
    ['최근접 권역·지역센터', fmt.minAtLeast(r.최근접_권역지역센터_분, r.최근접_권역지역센터_분_원값) + (sim ? '' : ` · 직선 ${fmt.km(r.최근접_권역지역센터_km)}`)],
    ['30분 내 응급의료기관', `${r['30분내_기관수'].toFixed(r['30분내_기관수'] % 1 ? 1 : 0)}곳`],
  ]
  return (
    <div className="detail" aria-live="polite">
      <div className="detail-head">
        <h2>{regionName(r)}</h2>
        <div className="badges">
          {r.등급 && <span className="badge" style={{ background: GRADE_COLOR[r.등급], color: textOn(GRADE_COLOR[r.등급]) }}>{r.등급}</span>}
          {isIsland(r) && <IslandBadge />}
          {r.근사반영비율 >= APPROX_BADGE && <span className="badge island" title="최근접 응급의료기관이나 센터까지 도로로 닿지 않는(연륙 안 된 섬 등) 주민 비율. 이 부분은 직선거리 × 우회계수 근사값이고 해상 이동은 반영하지 않았다">
            근사값 반영 {fmt.pct(r.근사반영비율)}</span>}
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
          <p>{clusterDesc(regions, r.클러스터)}</p>
        </div>
      </div>

      {usage && <Usages usage={usage} cap={cap} factor={r.우회계수} />}

      <MedianBars r={r} regions={regions} />
    </div>
  )
}
