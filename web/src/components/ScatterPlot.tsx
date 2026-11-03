import { memo } from 'react'
import { regionName, type Grade, type Region } from '../data'
import { GRADE_COLOR } from '../metrics'

const W = 520
const H = 420
const M = { top: 12, right: 14, bottom: 44, left: 48 }
const x = (v: number) => M.left + (v / 100) * (W - M.left - M.right)
const y = (v: number) => H - M.bottom - (v / 100) * (H - M.top - M.bottom)
const ORDER: Grade[] = ['', '준 이중 취약', '이중 취약'] // 이중 취약을 맨 위에 그린다

interface Props {
  regions: Region[]
  cuts: { top: [number, number]; near: [number, number] }
  selected: string | null
  onSelect: (code: string) => void
  onHover: (code: string | null, e?: React.MouseEvent) => void
}

function ScatterPlot({ regions, cuts, selected, onSelect, onHover }: Props) {
  const sel = regions.find((r) => r.코드 === selected)
  const ticks = [0, 20, 40, 60, 80, 100]
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="scatter" role="img"
      aria-label="접근성 취약 점수와 복지 취약 점수 산점도">
      {ticks.map((t) => (
        <g key={t} className="gridline">
          <line x1={x(t)} x2={x(t)} y1={y(0)} y2={y(100)} />
          <line x1={x(0)} x2={x(100)} y1={y(t)} y2={y(t)} />
          <text x={x(t)} y={y(0) + 16} textAnchor="middle">{t}</text>
          <text x={x(0) - 8} y={y(t) + 4} textAnchor="end">{t}</text>
        </g>
      ))}
      <g className="cut">
        <line x1={x(cuts.top[0])} x2={x(cuts.top[0])} y1={y(0)} y2={y(100)} />
        <line x1={x(0)} x2={x(100)} y1={y(cuts.top[1])} y2={y(cuts.top[1])} />
      </g>
      <g className="cut near">
        <line x1={x(cuts.near[0])} x2={x(cuts.near[0])} y1={y(0)} y2={y(100)} />
        <line x1={x(0)} x2={x(100)} y1={y(cuts.near[1])} y2={y(cuts.near[1])} />
      </g>
      <text x={x(0) + 4} y={y(cuts.top[1]) - 5} className="cut-label">복지 상위 25%</text>
      <text x={x(cuts.top[0]) - 4} y={y(0) - 5} textAnchor="end" className="cut-label">접근성 상위 25%</text>
      <text x={(x(0) + x(100)) / 2} y={H - 6} textAnchor="middle" className="axis-label">응급의료 접근성 취약 점수 →</text>
      <text transform={`translate(14 ${(y(0) + y(100)) / 2}) rotate(-90)`} textAnchor="middle" className="axis-label">
        복지 취약 점수 →
      </text>
      {ORDER.map((g) => regions.filter((r) => r.등급 === g).map((r) => (
        <circle
          key={r.코드} cx={x(r.접근성점수)} cy={y(r.복지점수)} r={g ? 5 : 4}
          fill={GRADE_COLOR[g]} className="dot" aria-label={regionName(r)}
          onMouseMove={(e) => onHover(r.코드, e)} onMouseLeave={() => onHover(null)} onClick={() => onSelect(r.코드)}
        />
      )))}
      {sel && <circle cx={x(sel.접근성점수)} cy={y(sel.복지점수)} r={9} className="dot-selected" />}
    </svg>
  )
}

export default memo(ScatterPlot)
