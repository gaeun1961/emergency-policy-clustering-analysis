import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import DetailPanel, { IslandBadge } from './components/DetailPanel'
import DoubleTable from './components/DoubleTable'
import MapView, { type MapSim } from './components/MapView'
import ScatterPlot from './components/ScatterPlot'
import SimPanel, { AddChooser, type RecKind } from './components/SimPanel'
import { isIsland, loadData, loadSimData, quantile, regionName, type Data, type Region, type SimData } from './data'
import { CLUSTER_COLOR, CLUSTER_DESC, GRADE_COLOR, buildMetrics, type MetricKey } from './metrics'
import { simulate, type Facility, type FacilityGrade } from './sim/model'
import { recommend, type Effect } from './sim/recommend'
import { locateSigungu } from './sim/geo'
import { EMPTY, applyScenario, fromQuery, keepOnLand, toQuery, type Scenario } from './sim/scenario'

const REPO = 'https://github.com/gaeun1961/emergency-policy-clustering-analysis'
const METRIC_KEYS: MetricKey[] = ['등급', '접근성점수', '복지점수', '클러스터', '최근접_응급의료기관_km', '최근접_권역지역센터_km']
type Tab = 'detail' | 'dist' | 'list' | 'sim' | 'about'
const TABS: { id: Tab; label: string }[] = [
  { id: 'detail', label: '지역 상세' }, { id: 'dist', label: '분포' }, { id: 'list', label: '목록' },
  { id: 'sim', label: '시뮬레이터' }, { id: 'about', label: '소개' },
]
const initial = fromQuery(location.search)

export default function App() {
  const [data, setData] = useState<Data | null>(null)
  const [simData, setSimData] = useState<SimData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [metricKey, setMetricKey] = useState<MetricKey>('등급')
  const [selected, setSelected] = useState<string | null>(null)
  const [hover, setHover] = useState<{ code: string; x: number; y: number } | null>(null)
  const [tab, setTab] = useState<Tab>(initial.on ? 'sim' : 'detail')
  const [showLocal, setShowLocal] = useState(false) // 지역응급의료기관(G007) 마커

  // 시뮬레이션: 시나리오는 URL 쿼리와 동기화
  const [simOn, setSimOn] = useState(initial.on)
  const [history, setHistory] = useState<Scenario[]>([initial.scenario])
  const [pending, setPending] = useState<{ lat: number; lon: number; x: number; y: number; code: string } | null>(null)
  const [toast, setToast] = useState<string | null>(null)
  const toastTimer = useRef<number | undefined>(undefined)
  const flash = useCallback((msg: string, ms = 2600) => {
    setToast(msg)
    window.clearTimeout(toastTimer.current)
    toastTimer.current = window.setTimeout(() => setToast(null), ms)
  }, [])
  const [recKind, setRecKind] = useState<RecKind>('G006')
  const scenario = history[history.length - 1]
  const push = useCallback((s: Scenario) => setHistory((h) => [...h, s]), [])

  useEffect(() => {
    loadData().then((d) => {
      setData(d)
      // 처음에는 합산점수가 가장 높은 이중 취약지역을 선택해 둔다
      setSelected([...d.regions].sort((a, b) => (b.합산점수 ?? -1) - (a.합산점수 ?? -1))[0].코드)
    }).catch((e) => setError(String(e)))
    loadSimData().then(setSimData).catch((e) => setError(String(e))) // 마커에도 쓰므로 항상 불러온다
  }, [])
  // 공유 링크로 들어온 추가 기관도 시군구 경계로 판정: 바다·경계 밖 좌표는 빼고 안내
  const checkedLink = useRef(false)
  useEffect(() => {
    if (!data || checkedLink.current) return
    checkedLink.current = true
    const { scenario: s, dropped } = keepOnLand(initial.scenario, (lat, lon) => locateSigungu(data.sigungu, lat, lon))
    setHistory((h) => (h.length === 1 ? [s] : h))
    if (dropped) flash(`공유 링크의 ${dropped}곳은 바다·경계 밖이라 제외했어요`, 6000)
  }, [data, flash])
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

  const applied = useMemo(() => simData && (simOn ? applyScenario(simData.facilities, scenario) : simData.facilities), [simData, simOn, scenario])
  const simResult = useMemo(() => (simOn && simData && applied ? simulate(applied, simData.centers, simData.baseline) : null), [simOn, simData, applied])

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
    if (!simOn || !simData || !applied || !simResult || !data) return null
    const elderly = Object.fromEntries(data.regions.map((r) => [r.코드, r['65세이상인구']]))
    return recommend(applied, simData.centers, simData.baseline, simResult, elderly, recKind)
  }, [simOn, simData, applied, simResult, data, recKind])

  const onHover = useCallback((code: string | null, e?: React.MouseEvent) => {
    setHover(code && e ? { code, x: e.clientX, y: e.clientY } : null)
  }, [])
  /** 지도·산점도·목록에서 선택: 시뮬레이터 탭이 아니면 [지역 상세]로 이동 */
  const select = useCallback((code: string) => {
    setSelected(code)
    setTab((t) => (t === 'sim' ? t : 'detail'))
  }, [])

  const markers = useMemo(() => (applied ?? []).filter((f) => showLocal || f.등급 !== 'G007' || f.hpid.startsWith('SIM-')), [applied, showLocal])
  const mapSim: MapSim | undefined = useMemo(() => {
    if (!simOn || !data || !view) return undefined
    return {
      changed: new Set(data.regions.filter((r) => view.byCode.get(r.코드)?.등급 !== r.등급).map((r) => r.코드)),
      onMapClick: (lat, lon, x, y) => {
        const code = locateSigungu(data.sigungu, lat, lon)
        if (code) setPending({ lat, lon, x, y, code })
        else { setPending(null); flash('육지(시군구 경계 안)에만 추가할 수 있어요') }
      },
      onFacilityClick: (f: Facility) => {
        if (f.hpid.startsWith('SIM-')) {
          const i = Number(f.hpid.slice(4)) - 1
          push({ ...scenario, added: scenario.added.filter((_, j) => j !== i) })
        } else push({ ...scenario, removed: [...scenario.removed, f.hpid] })
      },
    }
  }, [simOn, data, view, scenario, push, flash])

  const toggleSim = () => {
    setSimOn(!simOn)
    setPending(null)
    setTab(simOn ? 'detail' : 'sim')
  }
  const addAt = (grade: FacilityGrade) => {
    if (pending) push({ ...scenario, added: [...scenario.added, { grade, lat: pending.lat, lon: pending.lon, code: pending.code }] })
    setPending(null)
  }
  const applyRec = (e: Effect) => {
    const c = e.candidate
    push(c.kind === 'upgrade'
      ? { added: [...scenario.added, { grade: 'G006', lat: c.lat, lon: c.lon, code: c.code }], removed: [...scenario.removed, c.hpid!] }
      : { ...scenario, added: [...scenario.added, { grade: c.kind, lat: c.lat, lon: c.lon, code: c.code }] })
    setSelected(c.code)
  }

  if (error) return <main className="page"><p>데이터를 불러오지 못했습니다: {error}</p></main>
  if (!data || !metrics || !baseCuts || !view) return <main className="page"><p className="muted">불러오는 중…</p></main>

  const metric = metrics[metricKey]
  const hovered = hover && view.byCode.get(hover.code)
  const { meta } = data
  const cuts = simOn && simData ? {
    top: [simData.baseline.기준선.상위25.접근성, simData.baseline.기준선.상위25.복지] as [number, number],
    near: [simData.baseline.기준선.상위40.접근성, simData.baseline.기준선.상위40.복지] as [number, number],
  } : baseCuts
  const count = (g: string) => view.regions.filter((r) => r.등급 === g).length
  const chip = (g: '이중 취약' | '준 이중 취약', base: number) => {
    const now = count(g)
    return (
      <span className="chip"><span className="swatch" style={{ background: GRADE_COLOR[g] }} />
        {g} <strong>{base}곳</strong>{simOn && now !== base && <> → <strong>{now}곳</strong></>}
      </span>
    )
  }

  return (
    <div className="app">
      <header className="topbar">
        <h1>응급의료 × 복지 이중 취약지역</h1>
        <div className="chips">
          {chip('이중 취약', meta.이중취약수)}
          {chip('준 이중 취약', meta.준이중취약수)}
          <span className="chip muted">시군구 {meta.시군구수}곳 · 인구 {meta.기준시점['인구·복지']} · 기관 {meta.기준시점['응급의료기관']}</span>
        </div>
        <button className={`sim-toggle${simOn ? ' on' : ''}`} aria-pressed={simOn} onClick={toggleSim}>
          {simOn ? '시뮬레이션 끄기' : '시뮬레이션 모드'}
        </button>
      </header>

      <main className="body">
        <section className="map-area" aria-label="지도">
          <MapView data={data} byCode={view.byCode} metric={metric} selected={selected} onSelect={select} onHover={onHover}
            facilities={markers} sim={mapSim}>
            <label className="select">
              <select value={metricKey} onChange={(e) => setMetricKey(e.target.value as MetricKey)} aria-label="지도 지표">
                {METRIC_KEYS.map((k) => <option key={k} value={k}>{metrics[k].label}</option>)}
              </select>
            </label>
            <ul className="legend" aria-label={`${metric.label} 범례`}>
              {metric.legend.map((l) => <li key={l.label}><span className="swatch" style={{ background: l.color }} />{l.label}</li>)}
            </ul>
            {metric.note && <p className="hint">{metric.note}</p>}
            <ul className="legend markers-key">
              <li><span className="mk diamond" />권역센터</li>
              <li><span className="mk circle" />지역센터</li>
              <li><label><input type="checkbox" checked={showLocal} onChange={(e) => setShowLocal(e.target.checked)} /> 지역응급의료기관 표시</label></li>
              {simOn && <li><span className="mk added" />가상 추가</li>}
              {simOn && <li><span className="mk changed" />등급 변경</li>}
            </ul>
            {simOn && <p className="hint sim-hint">지도를 누르면 기관 추가, 기관 점을 누르면 제거</p>}
          </MapView>
        </section>

        <aside className="side">
          <nav className="tabs" role="tablist" aria-label="패널">
            {TABS.filter((t) => t.id !== 'sim' || simOn).map((t) => (
              <button key={t.id} role="tab" aria-selected={tab === t.id} className={tab === t.id ? 'on' : ''} onClick={() => setTab(t.id)}>
                {t.label}
              </button>
            ))}
          </nav>
          <div className="tab-body" role="tabpanel">
            {tab === 'detail' && <DetailPanel region={selected ? view.byCode.get(selected) ?? null : null} total={meta.시군구수} regions={view.regions} />}
            {tab === 'dist' && (
              <>
                <ul className="legend">
                  {(['이중 취약', '준 이중 취약', ''] as const).map((g) => (
                    <li key={g}><span className="swatch" style={{ background: GRADE_COLOR[g] }} />{g || '해당 없음'}</li>
                  ))}
                  <li className="muted">파선 상위 25% · 점선 상위 40%</li>
                </ul>
                <ScatterPlot regions={view.regions} cuts={cuts} selected={selected} onSelect={select} onHover={onHover} />
              </>
            )}
            {tab === 'list' && <DoubleTable regions={view.regions} selected={selected} onSelect={select} />}
            {tab === 'sim' && simOn && (simData ? (
              <SimPanel base={data.regions} now={view.byCode} scenario={scenario} canUndo={history.length > 1}
                onUndo={() => setHistory((h) => (h.length > 1 ? h.slice(0, -1) : h))} onReset={() => push(EMPTY)}
                recKind={recKind} onRecKind={setRecKind} recs={recs} onApply={applyRec} onSelect={(c) => setSelected(c)} />
            ) : <p className="muted">시뮬레이션 데이터를 불러오는 중…</p>)}
            {tab === 'about' && (
              <div className="about">
                <p className="small">응급의료 접근성이 낮고 고령·독거·장애 인구 비율이 높은 <strong>이중 취약지역</strong>을 찾아, 복지 서비스(예: 응급안전안심서비스)를 먼저 배치할 곳을 보여줍니다.
                  두 점수가 모두 상위 25%면 이중 취약, 한쪽 25% + 다른 쪽 40%면 준 이중 취약입니다.</p>
                <h3>시군구 유형 3개</h3>
                <ul className="clusters">
                  {Object.entries(meta.클러스터).map(([k, label]) => (
                    <li key={k}>
                      <span className="swatch" style={{ background: CLUSTER_COLOR[Number(k)] }} />
                      <div><strong>{k}. {label}</strong><p>{CLUSTER_DESC[Number(k)]}</p></div>
                    </li>
                  ))}
                </ul>
                <p className="small">1번과 2번은 모두 고령 농촌이지만, 1번은 <strong>읍내 응급실은 있으나 중증 센터가 멀고</strong>, 2번은 <strong>가까운 응급실 자체가 없다</strong>는 점이 다릅니다.</p>
                <h3>데이터 한계</h3>
                <ul className="small">
                  <li>거리는 시군구청(섬 지역은 읍면사무소) 기준 직선거리로, 실제 도로·해상 이동보다 짧습니다.</li>
                  <li>시군구청 바로 옆에 병원이 있는 곳은 최근접 거리가 과소 추정됩니다.</li>
                  <li>독거노인은 주민등록상 65세 이상 1인세대로, 실제 단독 거주와 다를 수 있습니다.</li>
                  <li>일반구는 상위 시로 합쳤고, 기초생활수급자는 시군구 단위 공개 통계가 없어 제외했습니다.</li>
                  <li>기준선 근처 지역은 기준이 조금만 바뀌어도 등급이 달라질 수 있습니다.</li>
                </ul>
                <h3>출처</h3>
                <ul className="small">
                  {meta.출처.map((s) => (
                    <li key={s.이름}><a href={s.url} target="_blank" rel="noreferrer">{s.이름}</a>{s.기준 ? ` (${s.기준})` : ''}</li>
                  ))}
                </ul>
                <p className="small">기준 시점: 인구·복지 {meta.기준시점['인구·복지']} · 응급의료기관 {meta.기준시점['응급의료기관']} 수집 · 경계 {meta.기준시점['경계']}</p>
                <p className="small"><a href={REPO} target="_blank" rel="noreferrer">GitHub 저장소</a> · 생성 {meta.생성일시.slice(0, 10)}</p>
              </div>
            )}
          </div>
        </aside>
      </main>

      {hovered && hover && (
        <div className="tooltip" style={{ left: hover.x + 14, top: hover.y + 14 }} role="status">
          <strong>{regionName(hovered)}</strong>
          <div>{metric.label}: {metric.format(hovered)}</div>
          {metricKey !== '등급' && hovered.등급 && <div>{hovered.등급}</div>}
          {isIsland(hovered) && <IslandBadge />}
        </div>
      )}
      {toast && <div className="toast" role="status">{toast}</div>}
      {simOn && pending && <AddChooser x={pending.x} y={pending.y} onPick={addAt} onCancel={() => setPending(null)} />}
    </div>
  )
}
