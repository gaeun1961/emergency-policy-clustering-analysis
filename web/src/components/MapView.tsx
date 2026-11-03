import { geoMercator, geoPath } from 'd3-geo'
import { select } from 'd3-selection'
import { zoom, zoomIdentity, type ZoomBehavior, type ZoomTransform } from 'd3-zoom'
import { memo, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import type { Data, Region } from '../data'
import type { Metric } from '../metrics'
import type { Facility } from '../sim/model'

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
  sim?: MapSim
  children?: ReactNode        // 지도 위에 겹쳐 놓을 범례·지표 선택
}

/** 확대해도 커지지 않는 마커 크기(px). 권역센터는 마름모, 나머지는 원 */
const MARKER = { G001: 3.2, G006: 2.3, G007: 1.6 } as const
/** 마커 불투명도: 전국 화면에서는 흐리게(수도권 뭉침 완화), 확대할수록 진하게 */
const markerOpacity = (k: number) => Math.min(1, 0.35 + 0.22 * Math.log2(k))
const LABEL_K = 2.5  // 이 배율 이상에서 시군구 이름표
const GRADE_RANK = { '이중 취약': 1, '준 이중 취약': 2, '': 3 } as const
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
function MapView({ data, byCode, metric, selected, onSelect, onHover, facilities, onFacilityClick, sim, children }: Props) {
  const [boxRef, { w, h }] = useSize<HTMLDivElement>()
  const svgRef = useRef<SVGSVGElement>(null)
  const zoomRef = useRef<ZoomBehavior<SVGSVGElement, unknown> | null>(null)
  const [t, setT] = useState<ZoomTransform>(zoomIdentity)
  const [legendOpen, setLegendOpen] = useState(false) // 390px 이하에서만 의미 있음 (CSS)

  const { projection, paths, sidoPath } = useMemo(() => {
    const projection = geoMercator().fitExtent([[12, 12], [w - 12, h - 12]], data.sigungu)
    const path = geoPath(projection)
    return {
      projection,
      paths: data.sigungu.features.map((f) => ({ code: f.properties.code, d: path(f) ?? '', c: path.centroid(f), area: path.area(f) })),
      sidoPath: data.sido.features.map((f) => path(f) ?? '').join(''),
    }
  }, [data, w, h])

  useEffect(() => {
    if (!svgRef.current) return
    const z = zoom<SVGSVGElement, unknown>().scaleExtent([1, 14]).filter(zoomFilter)
      .translateExtent([[-w * 0.2, -h * 0.2], [w * 1.2, h * 1.2]])
      .on('zoom', (e) => setT(e.transform))
    zoomRef.current = z
    select(svgRef.current).call(z).on('dblclick.zoom', null)
    return () => { select(svgRef.current!).on('.zoom', null) }
  }, [w, h])

  const reset = () => svgRef.current && zoomRef.current && select(svgRef.current).call(zoomRef.current.transform, zoomIdentity)

  /** 화면 좌표 -> SVG 좌표 -> 줌 역변환 -> 위경도 */
  const handleClick = (e: React.MouseEvent) => {
    const svg = svgRef.current
    const ctm = svg?.getScreenCTM()
    if (!sim || !svg || !ctm) return
    const p = new DOMPoint(e.clientX, e.clientY).matrixTransform(ctm.inverse())
    const lonlat = projection.invert?.(t.invert([p.x, p.y]))
    if (lonlat) sim.onMapClick(lonlat[1], lonlat[0], e.clientX, e.clientY)
  }

  const regions = useMemo(() => paths.map(({ code, d }) => (
    <path key={code} d={d} fill={metric.color(byCode.get(code)!)} className="region" data-code={code}
      onMouseMove={(e) => onHover(code, e)} onMouseLeave={() => onHover(null)} onClick={() => onSelect(code)} />
  )), [paths, metric, byCode, onHover, onSelect])

  const sel = paths.find((p) => p.code === selected)

  /** 이름표: 선택 지역 > 이중 취약 > 준 이중 > 면적 큰 순으로 놓고, 겹치면 생략 */
  const labels = useMemo(() => {
    if (t.k < LABEL_K) return []
    const order = [...paths].sort((a, b) => {
      const ra = a.code === selected ? 0 : GRADE_RANK[byCode.get(a.code)!.등급]
      const rb = b.code === selected ? 0 : GRADE_RANK[byCode.get(b.code)!.등급]
      return ra - rb || b.area - a.area
    })
    const placed: { x: number; y: number; w: number; h: number }[] = []
    const out: { code: string; x: number; y: number; text: string }[] = []
    for (const p of order) {
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
  }, [paths, t, w, h, byCode, selected])
  return (
    <div ref={boxRef} className="map-box">
      <svg ref={svgRef} width={w} height={h} className={sim ? 'map sim' : 'map'} role="img"
        aria-label={`시군구 지도: ${metric.label}`} onClick={sim ? handleClick : undefined}>
        <g transform={t.toString()}>
          {regions}
          <path d={sidoPath} className="sido-line" />
          {sim && paths.filter((p) => sim.changed.has(p.code)).map((p) => <path key={p.code} d={p.d} className="region-changed" />)}
          {sel && <path d={sel.d} className="region-selected" />}
        </g>
        <g className="markers" style={{ opacity: markerOpacity(t.k) }}>
          {facilities.map((f) => {
            const xy = projection([f.경도, f.위도])
            if (!xy) return null
            const [x, y] = t.apply(xy)
            if (x < -10 || y < -10 || x > w + 10 || y > h + 10) return null
            const added = f.hpid.startsWith('SIM-')
            const r = MARKER[f.등급] + (added ? 1.4 : 0)
            const common = {
              className: `marker g-${f.등급}${added ? ' added' : ''}`,
              onClick: (e: React.MouseEvent) => { e.stopPropagation(); onFacilityClick(f, e.clientX, e.clientY) },
            }
            const title = <title>{added ? `가상 기관 (${f.기관명})` : f.기관명}</title>
            return f.등급 === 'G001' && !added
              ? <rect key={f.hpid} x={x - r} y={y - r} width={r * 2} height={r * 2} transform={`rotate(45 ${x} ${y})`} {...common}>{title}</rect>
              : <circle key={f.hpid} cx={x} cy={y} r={r} {...common}>{title}</circle>
          })}
        </g>
        <g className="labels">
          {labels.map((l) => <text key={l.code} x={l.x} y={l.y} className={l.code === selected ? 'label sel' : 'label'}>{l.text}</text>)}
        </g>
      </svg>
      <div className={`map-overlay${legendOpen ? '' : ' collapsed'}`}>
        <button className="legend-toggle" aria-expanded={legendOpen} onClick={() => setLegendOpen(!legendOpen)}>
          {legendOpen ? '범례 접기 ▲' : '☰ 범례·지표'}
        </button>
        <div className="overlay-body">{children}</div>
      </div>
      <div className="map-zoom">
        <button onClick={reset} disabled={t.k === 1 && t.x === 0 && t.y === 0}>전국 보기</button>
        <span className="muted small zoom-hint desktop">휠로 확대·드래그로 이동</span>
        <span className="muted small zoom-hint mobile">두 손가락으로 확대·이동</span>
      </div>
    </div>
  )
}

export default memo(MapView)
