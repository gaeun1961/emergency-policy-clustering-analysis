import { geoMercator, geoPath } from 'd3-geo'
import { memo, useMemo, useRef } from 'react'
import type { Data, Region } from '../data'
import type { Metric } from '../metrics'
import type { Facility } from '../sim/model'

const W = 560
const H = 680
const MARKER_R = { G001: 4.2, G006: 3.2, G007: 2.3 } as const

/** 시뮬레이션 모드에서만 넘긴다. 없으면 기존 지도와 똑같이 그린다 */
export interface MapSim {
  facilities: Facility[]
  changed: Set<string>
  onMapClick: (lat: number, lon: number, clientX: number, clientY: number) => void
  onFacilityClick: (f: Facility) => void
}

interface Props {
  data: Data
  byCode: Map<string, Region>
  metric: Metric
  selected: string | null
  onSelect: (code: string) => void
  onHover: (code: string | null, e?: React.MouseEvent) => void
  sim?: MapSim
}

/** 시군구 단계구분도. 배경 지도 없이 SVG로만 그린다 */
function MapView({ data, byCode, metric, selected, onSelect, onHover, sim }: Props) {
  const svgRef = useRef<SVGSVGElement>(null)
  const { projection, paths, sidoPath } = useMemo(() => {
    const projection = geoMercator().fitExtent([[8, 8], [W - 8, H - 8]], data.sigungu)
    const path = geoPath(projection)
    return {
      projection,
      paths: data.sigungu.features.map((f) => ({ code: f.properties.code, d: path(f) ?? '' })),
      sidoPath: data.sido.features.map((f) => path(f) ?? '').join(''),
    }
  }, [data])

  /** 화면 좌표 -> SVG 좌표 -> 위경도 (projection.invert) */
  const handleClick = (e: React.MouseEvent) => {
    const svg = svgRef.current
    const ctm = svg?.getScreenCTM()
    if (!sim || !svg || !ctm) return
    const p = new DOMPoint(e.clientX, e.clientY).matrixTransform(ctm.inverse())
    const lonlat = projection.invert?.([p.x, p.y])
    if (lonlat) sim.onMapClick(lonlat[1], lonlat[0], e.clientX, e.clientY)
  }

  const sel = paths.find((p) => p.code === selected)
  return (
    <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} className={sim ? 'map sim' : 'map'} role="img"
      aria-label={`시군구 지도: ${metric.label}`} onClick={sim ? handleClick : undefined}>
      <g>
        {paths.map(({ code, d }) => {
          const r = byCode.get(code)!
          return (
            <path
              key={code} d={d} fill={metric.color(r)} className="region" data-code={code}
              onMouseMove={(e) => onHover(code, e)} onMouseLeave={() => onHover(null)}
              onClick={() => onSelect(code)}
            />
          )
        })}
      </g>
      <path d={sidoPath} className="sido-line" />
      {sim && paths.filter((p) => sim.changed.has(p.code)).map((p) => <path key={p.code} d={p.d} className="region-changed" />)}
      {sel && <path d={sel.d} className="region-selected" />}
      {sim && (
        <g className="markers">
          {sim.facilities.map((f) => {
            const [x, y] = projection([f.경도, f.위도]) ?? [0, 0]
            const added = f.hpid.startsWith('SIM-')
            return (
              <circle key={f.hpid} cx={x} cy={y} r={MARKER_R[f.등급] + (added ? 1.5 : 0)}
                className={`marker g-${f.등급}${added ? ' added' : ''}`}
                onClick={(e) => { e.stopPropagation(); sim.onFacilityClick(f) }}>
                <title>{`${f.기관명} (클릭하면 제거)`}</title>
              </circle>
            )
          })}
        </g>
      )}
    </svg>
  )
}

export default memo(MapView)
