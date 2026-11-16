import { describe, expect, it } from 'vitest'
import { fromQuery, toQuery } from './sim/scenario'
import { pickRegion, readView, withView } from './view'

describe('보던 지역·탭 링크 (?r=&tab=)', () => {
  it('지역·탭을 쓰고 읽으면 그대로 돌아온다', () => {
    const q = withView('', '47770', 'list', false)
    expect(q).toBe('?r=47770&tab=list')
    expect(readView(q, false)).toEqual({ r: '47770', tab: 'list' })
  })

  it('기본 탭은 URL 에 쓰지 않는다 (꺼짐: 지역 상세, 켜짐: 시뮬레이터)', () => {
    expect(withView('', '47770', 'detail', false)).toBe('?r=47770')
    expect(withView('?sim=1', '47770', 'sim', true)).toBe('?sim=1&r=47770')
    expect(withView('', null, 'detail', false)).toBe('')
    expect(readView('', false)).toEqual({ r: null, tab: 'dist' })          // 처음 열면(지역 미선택) 분포 탭
    expect(readView('?r=47770', false)).toEqual({ r: '47770', tab: 'detail' }) // 지역 링크는 지역 상세
    expect(readView('?sim=1', true)).toEqual({ r: null, tab: 'sim' })
  })

  it('시뮬레이션 파라미터와 공존: 시나리오가 그대로 읽히고 링크 형식도 같다', () => {
    const scenario = { added: [{ grade: 'G006' as const, lat: 34.57391, lon: 126.59964 }], removed: ['A1'], upgraded: ['E2800380'] }
    const sim = toQuery(true, scenario)
    const q = withView(sim, '46820', 'dist', true)
    expect(q).toBe(`${sim}&r=46820&tab=dist`)
    expect(fromQuery(q)).toEqual({ on: true, scenario })
    expect(readView(q, true)).toEqual({ r: '46820', tab: 'dist' })
  })

  it('잘못된 값은 버리고 기본 화면', () => {
    expect(readView('?r=abc&tab=nope', false)).toEqual({ r: null, tab: 'detail' })
    expect(readView('?r=477701&tab=', false)).toEqual({ r: null, tab: 'detail' })
    expect(readView('?tab=sim', false).tab).toBe('detail') // 시뮬레이션이 꺼져 있으면 시뮬레이터 탭 없음
    expect(readView('?sim=1&tab=sim', true).tab).toBe('sim')
    const has = (c: string) => ['47770', '11110'].includes(c)
    expect(pickRegion('11110', has, '47770')).toBe('11110')
    expect(pickRegion('99999', has, '47770')).toBe('47770') // 5자리지만 없는 코드
    expect(pickRegion(null, has, '47770')).toBe('47770')
  })
})
