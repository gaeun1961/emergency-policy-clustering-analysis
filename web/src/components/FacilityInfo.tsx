import { useEffect, useRef } from 'react'
import { fmt } from '../metrics'
import type { Facility } from '../sim/model'
import { GRADE_NAME } from '../sim/scenario'

export const isVirtual = (f: Facility) => f.hpid.startsWith('SIM-')

/** 기관 이름·종류·주소·전화. 시뮬레이터로 추가한 기관은 '가상 기관' */
export function FacilityLines({ f }: { f: Facility }) {
  const tel = (n: string) => <a href={`tel:${n.replace(/[^\d]/g, '')}`}>{n}</a>
  return (
    <>
      <div className="fac-name"><strong>{f.기관명}</strong>{isVirtual(f) && <span className="badge virtual">가상 기관</span>}</div>
      <div className="small muted">{GRADE_NAME[f.등급]}</div>
      {isVirtual(f) ? <div className="small muted">시뮬레이터에서 추가한 가상 기관 (주소·전화 없음)</div> : (
        <>
          {f.주소 && <div className="small">{f.주소}</div>}
          {f.응급실전화 && <div className="small">응급실 {tel(f.응급실전화)}
            {f.대표전화 && f.대표전화 !== f.응급실전화 && <> · 대표 {tel(f.대표전화)}</>}</div>}
        </>
      )}
    </>
  )
}

/** 지도 기관 마커를 눌렀을 때 뜨는 팝업. 시뮬레이션 중에는 제거 버튼 */
interface PopupTime { region: string; min: number; km: number; approx: boolean; capped: boolean; use?: { share: number; min: number; capped: boolean; center: boolean } }
export function FacilityPopup({ f, x, y, time, onRemove, onClose }: { f: Facility; x: number; y: number; time?: PopupTime; onRemove?: () => void; onClose: () => void }) {
  // 팝업 밖을 누르거나 Esc 면 닫힘. 다른 기관 점을 누르면 닫힌 뒤 그 기관 팝업이 새로 열린다
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const down = (e: PointerEvent) => { if (!ref.current?.contains(e.target as Node)) onClose() }
    const key = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('pointerdown', down)
    document.addEventListener('keydown', key)
    return () => { document.removeEventListener('pointerdown', down); document.removeEventListener('keydown', key) }
  }, [onClose])
  return (
    <div ref={ref} className="chooser fac-popup" style={{ left: Math.max(8, Math.min(x, window.innerWidth - 268)), top: Math.min(y + 8, window.innerHeight - 170) }}
      role="dialog" aria-label={`${f.기관명} 정보`}>
      <FacilityLines f={f} />
      {time?.use && <div className="small fac-time">{time.region} 주민 {fmt.pct(time.use.share)}의 가장 가까운 {time.use.center ? '센터' : '응급의료기관'} ·
        이용 주민 기준 <strong>{time.use.capped ? `≥ ${fmt.min(time.use.min)} (근사)` : fmt.min(time.use.min)}</strong></div>}
      {time && <div className="small fac-time">{time.region} 전체 주민 평균 자동차 {time.use ? '' : <strong>{time.capped ? `≥ ${fmt.min(time.min)}` : fmt.min(time.min)}</strong>}
        {time.use && (time.capped ? `≥ ${fmt.min(time.min)}` : fmt.min(time.min))} · 직선 {fmt.km(time.km)}
        {time.approx && <span className="muted">{isVirtual(f) ? ' (근사값: 직선거리 × 우회계수)' : ' (일부 근사값)'}</span>}</div>}
      {onRemove && <button type="button" onClick={onRemove}>이 기관 제거</button>}
      <button type="button" className="link" onClick={onClose}>닫기</button>
    </div>
  )
}
