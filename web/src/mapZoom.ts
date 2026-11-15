/**
 * 지도 확대·터치 규칙 (MapView). 데스크톱(정밀 포인터)은 바꾸지 않는다.
 * - 터치: 한 손가락 = 탭 선택·페이지 스크롤, 두 손가락 = 핀치 확대·이동 (d3-zoom 필터)
 * - 터치 기기의 기관 점 히트 영역(반지름 22px)은 전국 화면에서 육지의 약 90%를 덮어 지역을 누르면 기관 팝업이 떴다.
 *   그래서 터치에서는 TOUCH_FACILITY_K 배 이상 확대했을 때만 기관 점을 누를 수 있다
 */
export const TOUCH_FACILITY_K = 3
export const ZOOM_STEP = 1.6 // +/- 버튼 한 번에 바뀌는 배율

export const facilityTapEnabled = (coarse: boolean, k: number) => !coarse || k >= TOUCH_FACILITY_K

/** d3-zoom 필터: 터치는 두 손가락부터(한 손가락은 페이지 스크롤·탭), 마우스는 왼쪽 버튼(ctrl+클릭 제외)과 휠 */
export function zoomFilter(e: { type: string; touches?: { length: number }; ctrlKey?: boolean; button?: number }) {
  if (e.type.startsWith('touch')) return (e.touches?.length ?? 0) >= 2
  return (!e.ctrlKey || e.type === 'wheel') && !e.button
}

/** +/- 버튼을 누를 수 있는지 (현재 배율, 확대 범위) */
export const canZoom = (k: number, [min, max]: [number, number]) => ({ in: k < max - 1e-6, out: k > min + 1e-6 })
