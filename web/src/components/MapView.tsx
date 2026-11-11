import { geoMercator, geoPath } from 'd3-geo'
import { select } from 'd3-selection'
import { zoom, zoomIdentity, type ZoomBehavior, type ZoomTransform } from 'd3-zoom'
import { memo, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import type { FeatureCollection, Geometry } from 'geojson'
import type { Data, Region } from '../data'
import type { Metric } from '../metrics'
import type { Facility } from '../sim/model'

/** 읍면동 드릴다운: 선택 시군구의 행정동 면을 위에 덮어 그리고, 바뀌면 그 범위로 확대 */
export interface MapOverlay {
  key: string                 // 시군구 코드: 이 값이 바뀔 때만 자동 확대 (탭을 오가도 줌·위치 유지)
  fc: FeatureCollection<Geometry, { code: string }>
  label: (code: string) => string
  color: (code: string) => string
  title: (code: string) => string
  selected: string | null
  onClick: (code: string) => void
}

/** 시뮬레이션 모드에서만 넘긴다 */
export interface MapSim {
  changed: Set<string>
  onMapClick: (lat: number, lon: number, clientX: number, clientY: number) => void
}

interface Props {
  data: Data
  byCode: Map<string, Region>
  metric: Metric
  selected: string | null
  onSelect: (code: string) => void
  onHover: (code: string | null, e?: React.MouseEvent) => void
  facilities: Facility[]      // 표시할 응급의료기관 (마커)
  onFacilityClick: (f: Facility, clientX: number, clientY: number) => void
  highlight?: Set<string>     // 강조할 기관 hpid (선택 지역 주민이 이용하는 기관)
  overlay?: MapOverlay
  sim?: MapSim
  children?: ReactNode        // 지도 위에 겹쳐 놓을 범례·지표 선택
}

/** 확대해도 커지지 않는 마커 크기(px). 권역센터는 마름모, 나머지는 원 */
const MARKER = { G001: 3.2, G006: 2.3, G007: 1.6 } as const
/** 마커 불투명도: 전국 화면에서는 흐리게(수도권 뭉침 완화), 확대할수록 진하게 */
const markerOpacity = (k: number) => Math.min(1, 0.35 + 0.22 * Math.log2(k))
const LABEL_K = 2.5  // 이 배율 이상에서 시군구 이름표
const MAX_K = 14     // 기본 최대 배율. 읍면동 보기에서는 시군구 크기에 맞춰 높인다 (EMD_ZOOM_X)
const EMD_ZOOM_X = 3 // 읍면동 보기 최대 배율 = 시군구를 화면에 맞춘 배율 × 이 값 (작은 구는 기본 최대 14배를 넘어 동이 구분되게)
const EMD_LABEL_PX = 2.2 // 읍면동 이름표: 면의 화면 폭이 글자 폭의 이 배 이상일 때
/** 기관 클릭 히트 반경(px, 줌과 무관). 터치 기기는 더 크게. CSS .hit 의 r 과 같은 값 */
const HIT_PX = () => (matchMedia('(pointer: coarse)').matches ? 22 : 12)
const GRADE_RANK = { '이중 취약': 1, '준 이중 취약': 2, '': 3 } as const
const INTRO_DELAY = { '': 0, '준 이중 취약': 200, '이중 취약': 550 } as const
/** 메인 스레드가 한가해지면 실행 (무거운 계산 중에 애니메이션을 돌리면 프레임이 밀려 안 보인다). 정리 함수 반환 */
function onIdle(fn: () => void) {
  if ('requestIdleCallback' in window) {
    const id = requestIdleCallback(fn, { timeout: 1500 })
    return () => cancelIdleCallback(id)
  }
  const id = setTimeout(fn, 300) // Safari: requestIdleCallback 없음
  return () => clearTimeout(id)
}
const INTRO_MS = 1200 // 가장 늦은 지연 + 전환 시간(--dur-long) 보다 길게
/** 터치 기기: 한 손가락은 페이지 스크롤, 두 손가락(핀치)만 지도 확대·이동 */
const zoomFilter = (e: Event) => {
  if (e.type.startsWith('touch')) return (e as TouchEvent).touches.length >= 2
  const m = e as MouseEvent
  return (!m.ctrlKey || e.type === 'wheel') && !m.button
}

function useSize<T extends HTMLElement>() {
  const ref = useRef<T>(null)
  const [size, setSize] = useState({ w: 600, h: 700 })
  useEffect(() => {
    if (!ref.current) return
    const ro = new ResizeObserver(([e]) => {
      const { width, height } = e.contentRect
      if (width > 0 && height > 0) setSize({ w: Math.round(width), h: Math.round(height) })
    })
    ro.observe(ref.current)
    return () => ro.disconnect()
  }, [])
  return [ref, size] as const
}

/** 시군구 단계구분도. 배경 지도 없이 SVG, d3-zoom으로 확대·이동 */
function MapView({ data, byCode, metric, selected, onSelect, onHover, facilities, onFacilityClick, highlight, overlay, sim, children }: Props) {
  const [boxRef, { w, h }] = useSize<HTMLDivElement>()
  const svgRef = useRef<SVGSVGElement>(null)
  const zoomRef = useRef<ZoomBehavior<SVGSVGElement, unknown> | null>(null)
  const [t, setT] = useState<ZoomTransform>(zoomIdentity)
  const [legendOpen, setLegendOpen] = useState(false) // 390px 이하에서만 의미 있음 (CSS)

  const { projection, path, paths, sidoPath } = useMemo(() => {
    const projection = geoMercator().fitExtent([[12, 12], [w - 12, h - 12]], data.sigungu)
    const path = geoPath(projection)
    return {
      projection, path,
      paths: data.sigungu.features.map((f) => ({ code: f.properties.code, d: path(f) ?? '', c: path.centroid(f), area: path.area(f) })),
      sidoPath: data.sido.features.map((f) => path(f) ?? '').join(''),
    }
  }, [data, w, h])

  useEffect(() => {
    if (!svgRef.current) return
    const z = zoom<SVGSVGElement, unknown>().scaleExtent([1, MAX_K]).filter(zoomFilter)
      .translateExtent([[-w * 0.2, -h * 0.2], [w * 1.2, h * 1.2]])
      .on('zoom', (e) => setT(e.transform))
    zoomRef.current = z
    select(svgRef.current).call(z).on('dblclick.zoom', null)
    return () => { select(svgRef.current!).on('.zoom', null) }
  }, [w, h])

  const reset = () => svgRef.current && zoomRef.current && select(svgRef.current).call(zoomRef.current.transform, zoomIdentity)

  // 읍면동 면이 바뀌면(다른 시군구 선택) 그 범위로 확대
  const overlayPaths = useMemo(() => overlay?.fc.features.map((f) => ({
    code: f.properties.code, d: path(f) ?? '', c: path.centroid(f), b: path.bounds(f),
  })) ?? [], [overlay?.fc, path])
  // 읍면동 보기: 최대 배율을 시군구 크기에 맞춰 높이고, 시군구가 바뀔 때만 그 범위로 확대
  const zoomed = useRef<string | null>(null)
  useEffect(() => {
    const z = zoomRef.current
    if (!z || !svgRef.current) return
    if (!overlay) { z.scaleExtent([1, MAX_K]); return }
    const [[x0, y0], [x1, y1]] = path.bounds(overlay.fc)
    const fit = 0.8 / Math.max((x1 - x0) / w, (y1 - y0) / h)
    z.scaleExtent([1, Math.max(MAX_K, fit * EMD_ZOOM_X)])
    if (zoomed.current === overlay.key) return
    zoomed.current = overlay.key
    select(svgRef.current).call(z.transform, zoomIdentity.translate(w / 2 - (fit * (x0 + x1)) / 2, h / 2 - (fit * (y0 + y1)) / 2).scale(fit))
  }, [overlay?.key, overlay?.fc, path, w, h]) // eslint-disable-line react-hooks/exhaustive-deps

  /** 화면 좌표 -> SVG 좌표 -> 줌 역변환 -> 위경도 */
  const handleClick = (e: React.MouseEvent) => {
    const svg = svgRef.current
    const ctm = svg?.getScreenCTM()
    if (!sim || !svg || !ctm) return
    const p = new DOMPoint(e.clientX, e.clientY).matrixTransform(ctm.inverse())
    const lonlat = projection.invert?.(t.invert([p.x, p.y]))
    if (lonlat) sim.onMapClick(lonlat[1], lonlat[0], e.clientX, e.clientY)
  }

  // 첫 화면: 회색 지도에 준 이중 -> 이중 취약 순으로 색이 차오른다 (CSS fill 전환 + 등급별 지연).
  // 기관 데이터까지 들어와 메인 스레드가 한가해진 뒤 시작: 로딩 중에 돌리면 프레임이 밀려 회색에서 바로 끝 색으로 튄다
  const [intro, setIntro] = useState<'wait' | 'play' | 'done'>(() => (matchMedia('(prefers-reduced-motion: reduce)').matches ? 'done' : 'wait'))
  const ready = facilities.length > 0
  useEffect(() => (intro === 'wait' && ready ? onIdle(() => setIntro('play')) : undefined), [intro, ready])
  // 시뮬레이션으로 등급이 바뀐 곳: 재계산(simulate, 1초 가까이)이 끝나 화면이 다시 그려질 때 테두리를 한 번 깜박인다
  const changedKey = sim ? [...sim.changed].sort().join() : ''
  const [flashKey, setFlashKey] = useState('')
  useEffect(() => (changedKey ? onIdle(() => setFlashKey(changedKey)) : undefined), [changedKey])
  useEffect(() => {
    if (intro !== 'play') return
    const id = window.setTimeout(() => setIntro('done'), INTRO_MS)
    return () => clearTimeout(id)
  }, [intro])
  // 직접 고른 지역이 있으면 나머지를 흐리게. 처음 자동 선택(합산 1위)과 시뮬레이션 중(전국 변화를 봐야 함)은 제외.
  // 지도에서 선택된 지역을 한 번 더 누르면 흐림을 끄고 켠다
  const autoSel = useRef<string | null>(null)
  autoSel.current ??= selected
  const [picked, setPicked] = useState(false)
  useEffect(() => { if (selected && selected !== autoSel.current) setPicked(true) }, [selected])
  const focus = picked && !!selected && !sim
  // 읍면동 보기: 행정동을 고르면 같은 시군구의 나머지 행정동을 75% 불투명도로. 같은 동을 다시 누르면 끄고 켬
  const [emdDim, setEmdDim] = useState(true)
  useEffect(() => setEmdDim(true), [overlay?.selected])
  const emdFocus = !!overlay?.selected && emdDim
  const regions = useMemo(() => paths.map(({ code, d }) => (
    <path key={code} d={d} fill={metric.color(byCode.get(code)!)} className={code === selected ? 'region sel' : 'region'} data-code={code}
      style={intro === 'play' ? { transitionDelay: `${INTRO_DELAY[byCode.get(code)!.등급]}ms` } : undefined}
      onMouseMove={(e) => onHover(code, e)} onMouseLeave={() => onHover(null)} onClick={() => { if (code === selected) setPicked((v) => !v); onSelect(code) }} />
  )), [paths, metric, byCode, onHover, onSelect, intro, selected])

  const sel = paths.find((p) => p.code === selected)

  /** 화면에 보이는 기관 마커의 화면 좌표 */
  const placed = useMemo(() => facilities.flatMap((f) => {
    const xy = projection([f.경도, f.위도])
    if (!xy) return []
    const [x, y] = t.apply(xy)
    return x < -10 || y < -10 || x > w + 10 || y > h + 10 ? [] : [{ f, x, y }]
  }), [facilities, projection, t, w, h])

  /** 히트 영역 클릭: 클릭 지점에서 가장 가까운 기관 (히트 반경 안) */
  const hitClick = (e: React.MouseEvent) => {
    e.stopPropagation()
    const box = svgRef.current!.getBoundingClientRect()
    const cx = e.clientX - box.left, cy = e.clientY - box.top
    let best: Facility | null = null, bd = HIT_PX() + 1
    for (const { f, x, y } of placed) {
      const d = Math.hypot(x - cx, y - cy)
      if (d < bd) { best = f; bd = d }
    }
    if (best) onFacilityClick(best, e.clientX, e.clientY)
  }

  /** 이름표: 선택 지역 > 이중 취약 > 준 이중 > 면적 큰 순으로 놓고, 겹치면 생략 */
  const labels = useMemo(() => {
    if (t.k < LABEL_K && !overlay) return []
    const order = [...paths].sort((a, b) => {
      const ra = a.code === selected ? 0 : GRADE_RANK[byCode.get(a.code)!.등급]
      const rb = b.code === selected ? 0 : GRADE_RANK[byCode.get(b.code)!.등급]
      return ra - rb || b.area - a.area
    })
    const placed: { x: number; y: number; w: number; h: number }[] = []
    const out: { code: string; x: number; y: number; text: string; emd?: boolean }[] = []
    // 읍면동 이름표 먼저: 면이 글자보다 충분히 넓게 보일 때만
    for (const o of overlay ? overlayPaths : []) {
      const [x, y] = t.apply(o.c)
      if (!Number.isFinite(x) || x < 0 || y < 0 || x > w || y > h) continue
      const text = overlay!.label(o.code)
      if ((o.b[1][0] - o.b[0][0]) * t.k < text.length * 11 * EMD_LABEL_PX) continue
      const box = { x: x - text.length * 5.5 - 2, y: y - 8, w: text.length * 11 + 4, h: 16 }
      if (placed.some((b) => box.x < b.x + b.w && b.x < box.x + box.w && box.y < b.y + b.h && b.y < box.y + box.h)) continue
      placed.push(box)
      out.push({ code: o.code, x, y, text, emd: true })
    }
    for (const p of t.k < LABEL_K ? [] : order) {
      if (overlay && p.code === overlay.key) continue // 읍면동을 보는 시군구 이름은 생략
      const [x, y] = t.apply(p.c)
      if (!Number.isFinite(x) || x < 0 || y < 0 || x > w || y > h) continue
      const r = byCode.get(p.code)!
      const text = r.시군구 || r.시도
      const box = { x: x - text.length * 5.8 - 2, y: y - 8, w: text.length * 11.6 + 4, h: 16 }
      if (placed.some((b) => box.x < b.x + b.w && b.x < box.x + box.w && box.y < b.y + b.h && b.y < box.y + box.h)) continue
      placed.push(box)
      out.push({ code: p.code, x, y, text })
    }
    return out
  }, [paths, t, w, h, byCode, selected, overlay, overlayPaths])
  return (
    <div ref={boxRef} className="map-box">
      <svg ref={svgRef} width={w} height={h} className={`map${sim ? ' sim' : ''}${intro === 'wait' ? ' intro-wait' : ''}${focus ? ' focus' : ''}${emdFocus ? ' emd-focus' : ''}`} role="img"
        aria-label={`시군구 지도: ${metric.label}`} onClick={sim ? handleClick : undefined}>
        <g transform={t.toString()}>
          {regions}
          {overlay && overlayPaths.map(({ code, d }) => (
            <path key={code} d={d} fill={overlay.color(code)} className={`emd${code === overlay.selected ? ' sel' : ''}`}
              onClick={(e) => { e.stopPropagation(); if (code === overlay.selected) setEmdDim((v) => !v); overlay.onClick(code) }}><title>{overlay.title(code)}</title></path>
          ))}
          <path d={sidoPath} className="sido-line" />
          {sim && paths.filter((p) => sim.changed.has(p.code)).map((p) => <path key={p.code} d={p.d} className={`region-changed${flashKey === changedKey ? ' flash' : ''}`} />)}
          {sel && sel.code !== overlay?.key && <path d={sel.d} className="region-selected" />}{/* 읍면동 보기에서는 동 경계가 대신 보임 */}
        </g>
        <g className="markers" style={{ opacity: markerOpacity(t.k) }}>
          {placed.map(({ f, x, y }) => {
            const added = f.hpid.startsWith('SIM-')
            const r = MARKER[f.등급] + (added ? 1.4 : 0)
            const className = `marker g-${f.등급}${added ? ' added' : ''}`
            return f.등급 === 'G001' && !added
              ? <rect key={f.hpid} x={x - r} y={y - r} width={r * 2} height={r * 2} transform={`rotate(45 ${x} ${y})`} className={className} />
              : <circle key={f.hpid} cx={x} cy={y} r={r} className={className} />
          })}
        </g>
        <g className="markers-hl">
          {placed.filter(({ f }) => highlight?.has(f.hpid)).map(({ f, x, y }) => <circle key={f.hpid} cx={x} cy={y} r={7} className="marker-hl" />)}
        </g>
        {/* 투명 히트 영역: 겹치면 커서에 가장 가까운 기관 */}
        <g className="hits" onClick={hitClick}>
          {placed.map(({ f, x, y }) => <circle key={f.hpid} cx={x} cy={y} className="hit"><title>{f.hpid.startsWith('SIM-') ? `가상 기관 (${f.기관명})` : f.기관명}</title></circle>)}
        </g>
        <g className="labels">
          {labels.map((l) => <text key={l.code} x={l.x} y={l.y} className={l.emd ? 'label emd-label' : l.code === selected ? 'label sel' : 'label'}>{l.text}</text>)}
        </g>
      </svg>
      <div className={`map-overlay${legendOpen ? '' : ' collapsed'}`}>
        <button type="button" className="legend-toggle" aria-expanded={legendOpen} onClick={() => setLegendOpen(!legendOpen)}>
          {legendOpen ? '범례 접기 ▲' : '☰ 범례·지표'}
        </button>
        <div className="overlay-body">{children}</div>
      </div>
      <div className="map-zoom">
        <button type="button" onClick={reset} disabled={t.k === 1 && t.x === 0 && t.y === 0}>전국 보기</button>
        <span className="muted small zoom-hint desktop">휠로 확대·드래그로 이동</span>
        <span className="muted small zoom-hint mobile">두 손가락으로 확대·이동</span>
      </div>
    </div>
  )
}

export default memo(MapView)
