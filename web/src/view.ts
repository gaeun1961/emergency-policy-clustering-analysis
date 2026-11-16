/**
 * 보던 화면을 URL 로: 선택 시군구(r)와 탭(tab). 시뮬레이션 파라미터(sim·add·rm·up, scenario.toQuery)와 함께 쓴다.
 * 예: ?r=47770&tab=list, ?sim=1&add=G006:34.57391,126.59964&r=46820
 * 잘못된 값은 버리고 기본 화면. 기본 탭(시뮬레이션이 꺼져 있으면 지역 상세, 켜져 있으면 시뮬레이터)은 URL 에 쓰지 않는다.
 * 아무 파라미터 없이 처음 열면(지역을 고르지 않음) 전국 분포 탭부터 보여 준다
 */
export type Tab = 'detail' | 'dist' | 'list' | 'sim' | 'about'
export const TAB_IDS: Tab[] = ['detail', 'dist', 'list', 'sim', 'about']
export const defaultTab = (sim: boolean): Tab => (sim ? 'sim' : 'detail')

/** URL 에서 r·tab 읽기. r 은 5자리 숫자만(실제 있는 코드인지는 데이터를 불러온 뒤 pickRegion), tab=sim 은 시뮬레이션이 켜졌을 때만 */
export function readView(search: string, sim: boolean): { r: string | null; tab: Tab } {
  const p = new URLSearchParams(search)
  const r = p.get('r')
  const tab = p.get('tab') as Tab | null
  return {
    r: r && /^\d{5}$/.test(r) ? r : null,
    tab: tab && TAB_IDS.includes(tab) && (tab !== 'sim' || sim) ? tab : !r && !sim && !p.has('tab') ? 'dist' : defaultTab(sim),
  }
}

/** URL 의 시군구가 데이터에 있으면 그것, 없으면 기본 선택 */
export const pickRegion = (r: string | null, has: (code: string) => boolean, fallback: string) => (r && has(r) ? r : fallback)

/** 시뮬레이션 쿼리(toQuery 결과, 꺼져 있으면 '') 뒤에 r·tab 을 붙인다 */
export function withView(simQuery: string, r: string | null, tab: Tab, sim: boolean): string {
  const p = new URLSearchParams(simQuery)
  if (r) p.set('r', r)
  if (tab !== defaultTab(sim)) p.set('tab', tab)
  const q = p.toString().replace(/%3A/g, ':').replace(/%2C/g, ',').replace(/%3B/g, ';')
  return q ? `?${q}` : ''
}
