import { geoMercator, geoPath } from 'd3-geo'
import { memo, useMemo } from 'react'
import type { Data } from '../data'
import type { Metric } from '../metrics'

const W = 560
const H = 680

interface Props {
  data: Data
  metric: Metric
  selected: string | null
  onSelect: (code: string) => void
  onHover: (code: string | null, e?: React.MouseEvent) => void
}

/** 시군구 단계구분도. 배경 지도 없이 SVG로만 그린다 */
function MapView({ data, metric, selected, onSelect, onHover }: Props) {
  const { paths, sidoPath } = useMemo(() => {
    const projection = geoMercator().fitExtent([[8, 8], [W - 8, H - 8]], data.sigungu)
    const path = geoPath(projection)
    return {
      paths: data.sigungu.features.map((f) => ({ code: f.properties.code, d: path(f) ?? '' })),
      sidoPath: data.sido.features.map((f) => path(f) ?? '').join(''),
    }
  }, [data])

  const sel = paths.find((p) => p.code === selected)
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="map" role="img" aria-label={`시군구 지도: ${metric.label}`}>
      <g>
        {paths.map(({ code, d }) => {
          const r = data.byCode.get(code)!
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
      {sel && <path d={sel.d} className="region-selected" />}
    </svg>
  )
}

export default memo(MapView)
