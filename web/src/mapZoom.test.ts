import { describe, expect, it } from 'vitest'
import { TOUCH_FACILITY_K, canZoom, facilityTapEnabled, zoomFilter } from './mapZoom'

describe('지도 확대·터치 규칙 (#64)', () => {
  it('d3-zoom 필터: 터치는 두 손가락부터, 한 손가락은 지도 대신 탭·페이지 스크롤', () => {
    expect(zoomFilter({ type: 'touchstart', touches: { length: 1 } })).toBe(false)
    expect(zoomFilter({ type: 'touchstart', touches: { length: 2 } })).toBe(true)
    expect(zoomFilter({ type: 'touchmove', touches: { length: 3 } })).toBe(true)
  })

  it('데스크톱은 그대로: 왼쪽 버튼 드래그·휠(ctrl+휠 포함)은 지도, 오른쪽 버튼·ctrl+클릭은 아님', () => {
    expect(zoomFilter({ type: 'mousedown', button: 0 })).toBe(true)
    expect(zoomFilter({ type: 'wheel', button: 0 })).toBe(true)
    expect(zoomFilter({ type: 'wheel', ctrlKey: true, button: 0 })).toBe(true)
    expect(zoomFilter({ type: 'mousedown', button: 2 })).toBe(false)
    expect(zoomFilter({ type: 'mousedown', ctrlKey: true, button: 0 })).toBe(false)
  })

  it('기관 점 탭: 데스크톱은 항상, 터치는 확대했을 때만 (전국 화면에선 지역 탭이 우선)', () => {
    expect(facilityTapEnabled(false, 1)).toBe(true)
    expect(facilityTapEnabled(true, 1)).toBe(false)
    expect(facilityTapEnabled(true, TOUCH_FACILITY_K - 0.01)).toBe(false)
    expect(facilityTapEnabled(true, TOUCH_FACILITY_K)).toBe(true)
  })

  it('+/- 버튼: 최소 배율이면 축소 불가, 최대 배율이면 확대 불가', () => {
    expect(canZoom(1, [1, 14])).toEqual({ in: true, out: false })
    expect(canZoom(5, [1, 14])).toEqual({ in: true, out: true })
    expect(canZoom(14, [1, 14])).toEqual({ in: false, out: true })
  })
})
