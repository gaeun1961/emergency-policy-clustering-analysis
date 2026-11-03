import { useCallback, useEffect, useMemo, useState } from 'react'
import DetailPanel, { IslandBadge } from './components/DetailPanel'
import DoubleTable from './components/DoubleTable'
import MapView, { type MapSim } from './components/MapView'
import ScatterPlot from './components/ScatterPlot'
import SimPanel, { AddChooser, type RecKind } from './components/SimPanel'
import { isIsland, loadData, loadSimData, quantile, regionName, type Data, type Region, type SimData } from './data'
import { CLUSTER_COLOR, CLUSTER_DESC, buildMetrics, type MetricKey } from './metrics'
import { simulate, type Facility, type FacilityGrade } from './sim/model'
import { recommend, type Effect } from './sim/recommend'
import { EMPTY, applyScenario, fromQuery, toQuery, type Scenario } from './sim/scenario'

const REPO = 'https://github.com/gaeun1961/emergency-policy-clustering-analysis'
const METRIC_KEYS: MetricKey[] = ['등급', '접근성점수', '복지점수', '클러스터', '최근접_응급의료기관_km', '최근접_권역지역센터_km']
const initial = fromQuery(location.search)

export default function App() {
  const [data, setData] = useState<Data | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [metricKey, setMetricKey] = useState<MetricKey>('등급')
  const [selected, setSelected] = useState<string | null>(null)
  const [hover, setHover] = useState<{ code: string; x: number; y: number } | null>(null)

  // 시뮬레이션: 켜져 있을 때만 데이터를 불러오고, 시나리오는 URL 쿼리와 동기화
  const [simOn, setSimOn] = useState(initial.on)
  const [simData, setSimData] = useState<SimData | null>(null)
  const [history, setHistory] = useState<Scenario[]>([initial.scenario])
  const [pending, setPending] = useState<{ lat: number; lon: number; x: number; y: number } | null>(null)
  const [recKind, setRecKind] = useState<RecKind>('G006')
  const scenario = history[history.length - 1]
  const push = useCallback((s: Scenario) => setHistory((h) => [...h, s]), [])

  useEffect(() => {
    loadData().then((d) => {
      setData(d)
      // 처음에는 합산점수가 가장 높은 이중 취약지역을 선택해 둔다
      setSelected([...d.regions].sort((a, b) => (b.합산점수 ?? -1) - (a.합산점수 ?? -1))[0].코드)
    }).catch((e) => setError(String(e)))
  }, [])
  useEffect(() => {
    if (simOn && !simData) loadSimData().then(setSimData).catch((e) => setError(String(e)))
  }, [simOn, simData])
  useEffect(() => {
    window.history.replaceState(null, '', `${location.pathname}${toQuery(simOn, scenario)}${location.hash}`)
  }, [simOn, scenario])

  const metrics = useMemo(() => data && buildMetrics(data.regions, data.meta.클러스터), [data])
  const baseCuts = useMemo(() => {
    if (!data) return null
    const a = data.regions.map((r) => r.접근성점수)
    const w = data.regions.map((r) => r.복지점수)
    return { top: [quantile(a, 0.75), quantile(w, 0.75)] as [number, number], near: [quantile(a, 0.6), quantile(w, 0.6)] as [number, number] }
  }, [data])

  const active = simOn && simData && data ? { data, sim: simData } : null
  const applied = useMemo(() => active && applyScenario(active.sim.facilities, scenario), [active?.sim, scenario])
  const simResult = useMemo(() => active && applied && simulate(applied, active.sim.centers, active.sim.baseline), [applied])

  /** 지금 화면에 보여줄 지역 데이터: 시뮬레이션이 꺼져 있으면 원래 데이터 그대로 */
  const view = useMemo(() => {
    if (!data) return null
    if (!simResult) return { regions: data.regions, byCode: data.byCode }
    const scores = data.regions.map((r) => simResult[r.코드].접근성점수)
    const regions: Region[] = data.regions.map((r) => {
      const s = simResult[r.코드]
      return {
        ...r, 접근성점수: s.접근성점수, 등급: s.등급,
        최근접_응급의료기관_km: s.metrics.최근접_응급의료기관_km, 최근접_권역지역센터_km: s.metrics.최근접_권역지역센터_km,
        반경30km_기관수: s.metrics.반경30km_응급의료기관수,
        접근성순위: 1 + scores.filter((v) => v > s.접근성점수).length,
        합산점수: s.등급 === '이중 취약' ? s.접근성점수 + r.복지점수 : null,
      }
    })
    return { regions, byCode: new Map(regions.map((r) => [r.코드, r])) }
  }, [data, simResult])

  const recs = useMemo(() => {
    if (!active || !applied || !simResult || !data) return null
    const elderly = Object.fromEntries(data.regions.map((r) => [r.코드, r['65세이상인구']]))
    return recommend(applied, active.sim.centers, active.sim.baseline, simResult, elderly, recKind)
  }, [applied, simResult, recKind])

  const onHover = useCallback((code: string | null, e?: React.MouseEvent) => {
    setHover(code && e ? { code, x: e.clientX, y: e.clientY } : null)
  }, [])

  const mapSim: MapSim | undefined = useMemo(() => {
    if (!applied || !data) return undefined
    return {
      facilities: applied,
      changed: new Set(data.regions.filter((r) => view?.byCode.get(r.코드)?.등급 !== r.등급).map((r) => r.코드)),
      onMapClick: (lat, lon, x, y) => setPending({ lat, lon, x, y }),
      onFacilityClick: (f: Facility) => {
        if (f.hpid.startsWith('SIM-')) {
          const i = Number(f.hpid.slice(4)) - 1
          push({ ...scenario, added: scenario.added.filter((_, j) => j !== i) })
        } else push({ ...scenario, removed: [...scenario.removed, f.hpid] })
      },
    }
  }, [applied, data, view, scenario, push])

  const addAt = (grade: FacilityGrade) => {
    if (pending) push({ ...scenario, added: [...scenario.added, { grade, lat: pending.lat, lon: pending.lon }] })
    setPending(null)
  }
  const applyRec = (e: Effect) => {
    const c = e.candidate
    push(c.kind === 'upgrade'
      ? { added: [...scenario.added, { grade: 'G006', lat: c.lat, lon: c.lon }], removed: [...scenario.removed, c.hpid!] }
      : { ...scenario, added: [...scenario.added, { grade: c.kind, lat: c.lat, lon: c.lon }] })
    setSelected(c.code)
  }

  if (error) return <main className="page"><p>데이터를 불러오지 못했습니다: {error}</p></main>
  if (!data || !metrics || !baseCuts || !view) return <main className="page"><p className="muted">불러오는 중…</p></main>

  const metric = metrics[metricKey]
  const hovered = hover && view.byCode.get(hover.code)
  const { meta } = data
  const cuts = active ? {
    top: [active.sim.baseline.기준선.상위25.접근성, active.sim.baseline.기준선.상위25.복지] as [number, number],
    near: [active.sim.baseline.기준선.상위40.접근성, active.sim.baseline.기준선.상위40.복지] as [number, number],
  } : baseCuts
  const doubleCount = view.regions.filter((r) => r.등급 === '이중 취약').length

  return (
    <main className="page">
      <header className="header">
        <div className="title-row">
          <h1>응급의료 접근성 × 복지 취약: 이중 취약지역</h1>
          <button className={`sim-toggle${simOn ? ' on' : ''}`} aria-pressed={simOn} onClick={() => { setSimOn(!simOn); setPending(null) }}>
            시뮬레이션 모드 {simOn ? '끄기' : '켜기'}
          </button>
        </div>
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
            <h2>{simOn ? '시군구 지도 (시뮬레이션)' : '시군구 지도'}</h2>
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
          {simOn && (
            <ul className="legend">
              <li><span className="dot-key" /> 응급의료기관 (크기: 권역 &gt; 지역센터 &gt; 지역기관)</li>
              <li><span className="dot-key added" /> 가상 추가</li>
              <li><span className="swatch changed-key" /> 등급 변경</li>
            </ul>
          )}
          <MapView data={data} byCode={view.byCode} metric={metric} selected={selected} onSelect={setSelected} onHover={onHover}
            sim={simOn ? mapSim : undefined} />
        </section>

        <div className="side">
          {simOn && (active && view ? (
            <SimPanel base={data.regions} now={view.byCode} scenario={scenario} canUndo={history.length > 1}
              onUndo={() => setHistory((h) => (h.length > 1 ? h.slice(0, -1) : h))} onReset={() => push(EMPTY)}
              recKind={recKind} onRecKind={setRecKind} recs={recs} onApply={applyRec} onSelect={setSelected} />
          ) : <section className="panel"><p className="muted">시뮬레이션 데이터를 불러오는 중…</p></section>)}
          <DetailPanel region={selected ? view.byCode.get(selected) ?? null : null} total={meta.시군구수} />
          <section className="panel">
            <h2>접근성 × 복지 취약 점수</h2>
            <ul className="legend">
              {(['이중 취약', '준 이중 취약', '해당 없음'] as const).map((g) => (
                <li key={g}><span className={`swatch g-${g === '해당 없음' ? 'none' : g === '이중 취약' ? 'double' : 'near'}`} />{g}</li>
              ))}
              <li className="muted">파선 상위 25% · 점선 상위 40%</li>
            </ul>
            <ScatterPlot regions={view.regions} cuts={cuts} selected={selected} onSelect={setSelected} onHover={onHover} />
          </section>
        </div>
      </div>

      <section className="panel">
        <h2>이중 취약지역 {doubleCount}곳</h2>
        <p className="hint">두 점수가 모두 상위 25%. 행을 누르면 지도에서 선택됩니다.</p>
        <DoubleTable regions={view.regions} selected={selected} onSelect={setSelected} />
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
      {simOn && pending && <AddChooser x={pending.x} y={pending.y} onPick={addAt} onCancel={() => setPending(null)} />}
    </main>
  )
}
