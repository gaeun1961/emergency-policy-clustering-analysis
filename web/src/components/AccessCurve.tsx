import { memo, useState } from 'react'
import { GRADE_COLOR } from '../metrics'

/** access_curve.json (scripts/export_web_data.py export_access_curve) */
export interface CurveData { 분: number[]; 비율: Record<string, number[]>; 인구: Record<string, number> }

const W = 360, H = 220
const M = { top: 10, right: 12, bottom: 30, left: 40 }
const SERIES: { name: string; color: string; dash?: string; width: number }[] = [
  { name: '전국', color: 'var(--color-muted)', dash: '5 4', width: 2 },
  { name: '준 이중 취약', color: GRADE_COLOR['준 이중 취약'], width: 2 },
  { name: '이중 취약', color: GRADE_COLOR['이중 취약'], width: 2.5 },
]

/** 최근접 응급의료기관까지 N분 안에 사는 주민 비율 (누적). 마우스를 올리면 그 분의 값 */
function AccessCurve({ data }: { data: CurveData }) {
  const max = data.분[data.분.length - 1]
  const x = (m: number) => M.left + (m / max) * (W - M.left - M.right)
  const y = (v: number) => H - M.bottom - v * (H - M.top - M.bottom)
  const [hover, setHover] = useState<number | null>(null)
  const line = (vs: number[]) => vs.map((v, i) => `${i ? 'L' : 'M'}${x(data.분[i]).toFixed(1)},${y(v).toFixed(1)}`).join('')
  const onMove = (e: React.MouseEvent<SVGSVGElement>) => {
    const r = e.currentTarget.getBoundingClientRect()
    const m = Math.round(((e.clientX - r.left) / r.width * W - M.left) / (W - M.left - M.right) * max)
    setHover(m >= 0 && m <= max ? m : null)
  }
  const at30 = (n: string) => `${(data.비율[n][30] * 100).toFixed(1)}%`
  return (
    <section className="access-curve" aria-label="응급의료기관까지 시간별 누적 주민 비율">
      <h3>몇 분 안에 응급실에 닿나 <span className="muted small">주민 누적 비율</span></h3>
      <p className="curve-legend small">
        {[...SERIES].reverse().map((s) => (
          <span key={s.name}><svg width="22" height="8" aria-hidden="true"><line x1="0" x2="22" y1="4" y2="4" stroke={s.color} strokeWidth={s.width} strokeDasharray={s.dash} /></svg>{s.name}</span>
        ))}
      </p>
      <svg viewBox={`0 0 ${W} ${H}`} className="curve" role="img" onMouseMove={onMove} onMouseLeave={() => setHover(null)}
        aria-label={`30분 안에 최근접 응급의료기관에 닿는 주민: 전국 ${at30('전국')}, 이중 취약 ${at30('이중 취약')}`}>
        {[0, 0.25, 0.5, 0.75, 1].map((v) => (
          <g key={v} className="gridline"><line x1={x(0)} x2={x(max)} y1={y(v)} y2={y(v)} /><text x={x(0) - 6} y={y(v) + 4} textAnchor="end">{v * 100}%</text></g>
        ))}
        {[0, 10, 20, 30, 40, 50, 60].filter((m) => m <= max).map((m) => (
          <text key={m} className="axis-label" x={x(m)} y={H - M.bottom + 16} textAnchor="middle">{m}분</text>
        ))}
        {SERIES.map((s) => (
          <g key={s.name}>
            <path d={line(data.비율[s.name])} fill="none" stroke={s.color} strokeWidth={s.width} strokeDasharray={s.dash} strokeLinejoin="round" />
          </g>
        ))}
        {hover !== null && (
          <g className="curve-hover">
            <line x1={x(hover)} x2={x(hover)} y1={y(0)} y2={y(1)} />
            {SERIES.map((s) => <circle key={s.name} cx={x(hover)} cy={y(data.비율[s.name][hover])} r={4} fill={s.color} />)}
          </g>
        )}
      </svg>
      <p className="curve-readout small" aria-live="polite">
        {hover === null
          ? <>30분 안에 닿는 주민: 전국 <b>{at30('전국')}</b>, 이중 취약 <b>{at30('이중 취약')}</b> (그래프 위에 마우스를 올리면 분별 값)</>
          : <>{hover}분 안: {SERIES.map((s) => <span key={s.name}>{s.name} <b>{(data.비율[s.name][hover] * 100).toFixed(1)}%</b> </span>)}</>}
      </p>
      <p className="hint">행정동 3,557곳의 인구로 가중한 자동차 주행시간 기준입니다. 섬 등 근사값 지역은 실제로 더 오래 걸릴 수 있고, 시뮬레이션은 반영하지 않습니다.</p>
    </section>
  )
}

export default memo(AccessCurve)
