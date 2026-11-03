import { useCallback, useEffect, useMemo, useState } from 'react'
import DetailPanel, { IslandBadge } from './components/DetailPanel'
import DoubleTable from './components/DoubleTable'
import MapView from './components/MapView'
import ScatterPlot from './components/ScatterPlot'
import { isIsland, loadData, quantile, regionName, type Data } from './data'
import { CLUSTER_COLOR, CLUSTER_DESC, buildMetrics, type MetricKey } from './metrics'

const REPO = 'https://github.com/gaeun1961/emergency-policy-clustering-analysis'
const METRIC_KEYS: MetricKey[] = ['등급', '접근성점수', '복지점수', '클러스터', '최근접_응급의료기관_km', '최근접_권역지역센터_km']

export default function App() {
  const [data, setData] = useState<Data | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [metricKey, setMetricKey] = useState<MetricKey>('등급')
  const [selected, setSelected] = useState<string | null>(null)
  const [hover, setHover] = useState<{ code: string; x: number; y: number } | null>(null)

  useEffect(() => {
    loadData().then((d) => {
      setData(d)
      // 처음에는 합산점수가 가장 높은 이중 취약지역을 선택해 둔다
      setSelected([...d.regions].sort((a, b) => (b.합산점수 ?? -1) - (a.합산점수 ?? -1))[0].코드)
    }).catch((e) => setError(String(e)))
  }, [])

  const metrics = useMemo(() => data && buildMetrics(data.regions, data.meta.클러스터), [data])
  const cuts = useMemo(() => {
    if (!data) return null
    const a = data.regions.map((r) => r.접근성점수)
    const w = data.regions.map((r) => r.복지점수)
    return { top: [quantile(a, 0.75), quantile(w, 0.75)] as [number, number], near: [quantile(a, 0.6), quantile(w, 0.6)] as [number, number] }
  }, [data])
  const onHover = useCallback((code: string | null, e?: React.MouseEvent) => {
    setHover(code && e ? { code, x: e.clientX, y: e.clientY } : null)
  }, [])

  if (error) return <main className="page"><p>데이터를 불러오지 못했습니다: {error}</p></main>
  if (!data || !metrics || !cuts) return <main className="page"><p className="muted">불러오는 중…</p></main>

  const metric = metrics[metricKey]
  const hovered = hover && data.byCode.get(hover.code)
  const { meta } = data

  return (
    <main className="page">
      <header className="header">
        <h1>응급의료 접근성 × 복지 취약: 이중 취약지역</h1>
        <p className="summary">
          시군구 {meta.시군구수}곳 중 <strong className="t-double">이중 취약 {meta.이중취약수}곳</strong>,{' '}
          <strong className="t-near">준 이중 취약 {meta.준이중취약수}곳</strong>.
          응급의료 접근성이 낮고 고령·독거·장애 인구 비율이 높아 복지 서비스(예: 응급안전안심서비스)를 먼저 배치할 지역입니다.
        </p>
        <p className="muted small">
          기준 시점: 인구·복지 {meta.기준시점['인구·복지']} · 응급의료기관 {meta.기준시점['응급의료기관']} 수집 · 경계 {meta.기준시점['경계']}
        </p>
      </header>

      <div className="grid">
        <section className="panel map-panel">
          <div className="panel-head">
            <h2>시군구 지도</h2>
            <label className="select">
              <span>지표</span>
              <select value={metricKey} onChange={(e) => setMetricKey(e.target.value as MetricKey)}>
                {METRIC_KEYS.map((k) => <option key={k} value={k}>{metrics[k].label}</option>)}
              </select>
            </label>
          </div>
          <ul className="legend" aria-label={`${metric.label} 범례`}>
            {metric.legend.map((l) => <li key={l.label}><span className="swatch" style={{ background: l.color }} />{l.label}</li>)}
          </ul>
          {metric.note && <p className="hint">{metric.note}</p>}
          <MapView data={data} metric={metric} selected={selected} onSelect={setSelected} onHover={onHover} />
        </section>

        <div className="side">
          <DetailPanel region={selected ? data.byCode.get(selected) ?? null : null} total={meta.시군구수} />
          <section className="panel">
            <h2>접근성 × 복지 취약 점수</h2>
            <ul className="legend">
              {(['이중 취약', '준 이중 취약', '해당 없음'] as const).map((g) => (
                <li key={g}><span className={`swatch g-${g === '해당 없음' ? 'none' : g === '이중 취약' ? 'double' : 'near'}`} />{g}</li>
              ))}
              <li className="muted">파선 상위 25% · 점선 상위 40%</li>
            </ul>
            <ScatterPlot regions={data.regions} cuts={cuts} selected={selected} onSelect={setSelected} onHover={onHover} />
          </section>
        </div>
      </div>

      <section className="panel">
        <h2>이중 취약지역 {meta.이중취약수}곳</h2>
        <p className="hint">두 점수가 모두 상위 25%. 행을 누르면 지도에서 선택됩니다.</p>
        <DoubleTable regions={data.regions} selected={selected} onSelect={setSelected} />
      </section>

      <footer className="footer">
        <section>
          <h2>시군구 유형 3개</h2>
          <ul className="clusters">
            {Object.entries(meta.클러스터).map(([k, label]) => (
              <li key={k}>
                <span className="swatch" style={{ background: CLUSTER_COLOR[Number(k)] }} />
                <div><strong>{k}. {label}</strong><p>{CLUSTER_DESC[Number(k)]}</p></div>
              </li>
            ))}
          </ul>
          <p className="small">1번과 2번은 모두 고령 농촌이지만, 1번은 <strong>읍내 응급실은 있으나 중증 센터가 멀고</strong>, 2번은 <strong>가까운 응급실 자체가 없다</strong>는 점이 다릅니다.</p>
        </section>
        <section>
          <h2>데이터 한계</h2>
          <ul className="small">
            <li>거리는 시군구청(섬 지역은 읍면사무소) 기준 직선거리로, 실제 도로·해상 이동보다 짧습니다.</li>
            <li>시군구청 바로 옆에 병원이 있는 곳은 최근접 거리가 과소 추정됩니다.</li>
            <li>독거노인은 주민등록상 65세 이상 1인세대로, 실제 단독 거주와 다를 수 있습니다.</li>
            <li>일반구는 상위 시로 합쳤고, 기초생활수급자는 시군구 단위 공개 통계가 없어 제외했습니다.</li>
            <li>기준선 근처 지역은 기준이 조금만 바뀌어도 등급이 달라질 수 있습니다.</li>
          </ul>
        </section>
        <section>
          <h2>출처</h2>
          <ul className="small">
            {meta.출처.map((s) => (
              <li key={s.이름}><a href={s.url} target="_blank" rel="noreferrer">{s.이름}</a>{s.기준 ? ` (${s.기준})` : ''}</li>
            ))}
          </ul>
          <p className="small"><a href={REPO} target="_blank" rel="noreferrer">GitHub 저장소</a> · 생성 {meta.생성일시.slice(0, 10)}</p>
        </section>
      </footer>

      {hovered && hover && (
        <div className="tooltip" style={{ left: hover.x + 14, top: hover.y + 14 }} role="status">
          <strong>{regionName(hovered)}</strong>
          <div>{metric.label}: {metric.format(hovered)}</div>
          {metricKey !== '등급' && hovered.등급 && <div>{hovered.등급}</div>}
          {isIsland(hovered) && <IslandBadge />}
        </div>
      )}
    </main>
  )
}
