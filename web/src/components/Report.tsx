import { geoMercator, geoPath } from 'd3-geo'
import { quantile, regionName, type Meta, type Region, type SigunguGeo } from '../data'
import { DEPT_NOTE, keyDepartments } from '../departments'
import { CLUSTER_COLOR, GRADE_COLOR, fmt } from '../metrics'
import { KIND_NAME, bestSentence, planStep } from '../report'
import type { RankedFacility } from '../sim/model'
import type { PlacementData } from '../sim/placement'
import { GRADE_NAME } from '../sim/scenario'
import type { RegionUsage } from './DetailPanel'

interface Props {
  r: Region
  regions: Region[]
  meta: Meta
  sigungu: SigunguGeo
  byCode: Map<string, Region>
  usage: RegionUsage | null
  placement: PlacementData | null | undefined
  brief: { text: string; model: string } | null
  url: string
  sim: boolean
}

const W = 250, H = 210

/** 주변 지도: 선택 시군구에 맞춰 확대, 이웃은 등급 색, 가까운 응급의료기관은 점 */
function MiniMap({ r, sigungu, byCode, usage }: Pick<Props, 'r' | 'sigungu' | 'byCode' | 'usage'>) {
  const self = sigungu.features.find((f) => f.properties.code === r.코드)
  if (!self) return null
  const facs = [...(usage?.em ?? []), ...(usage?.ctr ?? [])]
  // 시군구와 가까운 기관이 모두 들어오게 범위를 잡는다
  const extent = { type: 'FeatureCollection' as const, features: [self, { type: 'Feature' as const, properties: {}, geometry: { type: 'MultiPoint' as const, coordinates: facs.map(({ f }) => [f.경도, f.위도]) } }] }
  const proj = geoMercator().fitExtent([[14, 14], [W - 14, H - 14]], extent)
  const path = geoPath(proj)
  return (
    <svg className="report-map" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${regionName(r)} 주변 지도`}>
      {sigungu.features.map((f) => (
        <path key={f.properties.code} d={path(f) ?? ''} fill={GRADE_COLOR[byCode.get(f.properties.code)?.등급 ?? '']} className="report-region" />
      ))}
      <path d={path(self) ?? ''} className="report-self" />
      {facs.map(({ f }) => {
        const p = proj([f.경도, f.위도])
        return p && <circle key={f.hpid} cx={p[0]} cy={p[1]} r={3.2} className="report-fac" />
      })}
    </svg>
  )
}

const minText = (x: RankedFacility) => (x.capped ? `≥ ${fmt.min(x.min)}` : fmt.min(x.min))

function FacilityRows({ title, items }: { title: string; items: RankedFacility[] }) {
  return (
    <>
      <tr className="report-group"><th colSpan={4}>{title}</th></tr>
      {items.map((x) => {
        const keys = keyDepartments(x.f.진료과목)
        return (
          <tr key={x.f.hpid}>
            <td>{x.f.기관명}<span className="muted"> {GRADE_NAME[x.f.등급]}</span></td>
            <td className="num">{minText(x)}</td>
            <td className="num">{x.alt ? '-' : fmt.pct(x.share)}</td>
            <td>{keys ? <>{keys.filter((d) => d.has).map((d) => d.name).join(', ') || '없음'}
              {keys.some((d) => !d.has) && <span className="muted"> (없음: {keys.filter((d) => !d.has).map((d) => d.name).join(', ')})</span>}</> : '-'}</td>
          </tr>
        )
      })}
    </>
  )
}

/** 지역 정책 보고서: 화면에는 숨기고 인쇄(PDF 저장) 때만 A4 한 장으로 나온다 (index.css @media print) */
export default function Report({ r, regions, meta, sigungu, byCode, usage, placement, brief, url, sim }: Props) {
  const n = regions.length
  const med = (k: keyof Region) => quantile(regions.map((x) => x[k] as number), 0.5)
  const nameOf = (code: string) => { const x = byCode.get(code); return x ? (x.시군구 || x.시도) : code }
  const rank = (k: keyof Region) => 1 + regions.filter((x) => (x[k] as number) > (r[k] as number)).length
  const facts: [string, string][] = [
    ['최근접 응급의료기관 (자동차)', `${fmt.minAtLeast(r.최근접_응급의료기관_분, r.최근접_응급의료기관_분_원값)} (전국 중앙값 ${fmt.min(med('최근접_응급의료기관_분'))})`],
    ['최근접 권역·지역센터 (자동차)', `${fmt.minAtLeast(r.최근접_권역지역센터_분, r.최근접_권역지역센터_분_원값)} (전국 중앙값 ${fmt.min(med('최근접_권역지역센터_분'))})`],
    ['30분 내 응급의료기관', `${r['30분내_기관수'].toFixed(1)}곳`],
    ['응급실 병상 (2SFCA)', `인구 10만 명당 ${fmt.beds(r['2SFCA'])}`],
    ['고령인구비율', `${fmt.pct(r.고령인구비율)} (${n}곳 중 ${rank('고령인구비율')}위)`],
    ['독거노인비율', `${fmt.pct(r.독거노인비율)} (${rank('독거노인비율')}위)`],
    ['장애인비율', `${fmt.pct(r.장애인비율)} (${rank('장애인비율')}위)`],
    ['기초생활수급자 비율 (참고)', `${fmt.pct(r.수급자비율)} (${r.수급자비율순위}위)`],
  ]
  const g006 = placement?.시군구별.G006[r.코드], g007 = placement?.시군구별.G007[r.코드]
  const step6 = planStep(placement?.plans.G006, r.코드), step7 = planStep(placement?.plans.G007, r.코드)
  const today = new Date().toLocaleDateString('ko-KR', { year: 'numeric', month: 'long', day: 'numeric' })
  return (
    <article className="report" aria-hidden="true">
      <header className="report-head">
        <div>
          <h1>{regionName(r)} 지역 보고서</h1>
          <p className="report-sub">응급의료 × 복지 이중 취약지역 대시보드</p>
        </div>
        <div className="report-grade">
          <span className="badge" style={{ background: GRADE_COLOR[r.등급], color: r.등급 === '이중 취약' ? 'var(--color-accent-ink)' : 'var(--color-ink)' }}>{r.등급 || '해당 없음'}</span>
          <p>인구·복지 {meta.기준시점['인구·복지']}, 응급의료기관 {meta.기준시점['응급의료기관']} 기준<br />출력 {today}{sim ? ', 시뮬레이션 반영 화면' : ''}</p>
        </div>
      </header>

      <section className="report-top">
        <MiniMap r={r} sigungu={sigungu} byCode={byCode} usage={usage} />
        <div className="report-scores">
          <div><span>응급의료 접근성 취약</span><strong>{fmt.score(r.접근성점수)}점</strong><em>{n}곳 중 {r.접근성순위}위</em></div>
          <div><span>복지 취약</span><strong>{fmt.score(r.복지점수)}점</strong><em>{n}곳 중 {r.복지순위}위</em></div>
          <p className="report-cluster"><i style={{ background: CLUSTER_COLOR[r.클러스터] }} />유형 {r.클러스터}. {r.클러스터라벨}</p>
          <table className="report-facts"><tbody>
            {facts.map(([k, v]) => <tr key={k}><th>{k}</th><td>{v}</td></tr>)}
          </tbody></table>
        </div>
      </section>

      {brief && (
        <section className="report-brief">
          <div className="report-h"><h2>AI 브리핑</h2><span>{brief.model} 생성, 숫자는 데이터와 자동 대조</span></div>
          <p>{brief.text}</p>
        </section>
      )}

      {usage && (
        <section>
          <div className="report-h"><h2>가까운 응급의료기관</h2><span>주민 평균 자동차 주행시간 순</span></div>
          <table className="report-table">
            <thead><tr><th>기관</th><th className="num">주민 평균</th><th className="num">이용 주민</th><th>주요 진료과목</th></tr></thead>
            <tbody>
              <FacilityRows title="응급의료기관" items={usage.em} />
              <FacilityRows title="권역·지역응급의료센터" items={usage.ctr} />
            </tbody>
          </table>
        </section>
      )}

      {placement && (
        <section>
          <div className="report-h"><h2>배치 효과</h2><span>기관 추가가 없는 지금 상태 기준</span></div>
          <ul className="report-list">
            <li><b>{KIND_NAME.G006}</b>: {bestSentence(g006, 'G006', nameOf)}</li>
            <li><b>{KIND_NAME.G007}</b>: {bestSentence(g007, 'G007', nameOf)}</li>
            {r.등급 === '이중 취약' && <li><b>전국 순차 배치 추천</b>: {step6 ? `지역센터를 1곳씩 둘 때 ${step6}곳째에 이 시군구가 이중 취약에서 벗어난다.` : '지역센터 5곳 순차 배치 안에서는 이 시군구가 이중 취약에서 벗어나지 않는다.'}
              {step7 ? ` 지역기관으로는 ${step7}곳째에 벗어난다.` : ''}</li>}
          </ul>
        </section>
      )}

      <footer className="report-foot">
        <p>판정: 응급의료 접근성 취약 점수(최근접 응급의료기관·센터 주행시간, 30분 내 기관 수)와 복지 취약 점수(고령·독거·장애 비율)가 모두 상위 25%면 이중 취약, 한쪽 25% + 다른 쪽 40%면 준 이중 취약.
          배치 후보는 가정 위치이며 병상·인력·재정·인허가는 반영하지 않은 의사결정 지원용이다. {DEPT_NOTE(meta.기준시점['진료과목'])} 섬은 해상 이동을 반영하지 못한 근사값이다.</p>
        <p>출처: 행정안전부 주민등록 인구통계, 보건복지부 장애인현황, 복지로 기초생활보장 수급자, 국립중앙의료원 응급의료정보, OpenStreetMap(ODbL)·OSRM 주행시간, 행정동 경계 vuski/admdongkor(CC BY 4.0).</p>
        <p className="report-url">대시보드에서 보기: {url}</p>
      </footer>
    </article>
  )
}
