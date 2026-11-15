/**
 * 응급의료기관 진료과목 (참고 표시). 기본정보 API 의 dgidIdName 을 수집 시점에 한 번 받은 정적 정보라,
 * 그 과가 있다는 뜻이지 지금 진료할 수 있다는 뜻이 아니다. 판정·점수·시뮬레이터에는 쓰지 않는다
 */
/** 응급 상황에서 자주 찾는 과: 응급 전담, 소아·분만, 뇌(출혈·뇌졸중), 심장 */
export const KEY_DEPARTMENTS = ['응급의학과', '소아청소년과', '산부인과', '신경외과', '신경과', '심장혈관흉부외과'] as const

/** 주요 과 보유 여부. 진료과목 정보가 없는 기관(가상 기관, 미수집)은 null */
export const keyDepartments = (list?: string[]) => (list ? KEY_DEPARTMENTS.map((name) => ({ name, has: list.includes(name) })) : null)

export const DEPT_NOTE = (ym?: string | null) => `진료과목 보유 정보이며 실시간 진료 가능 여부가 아닙니다${ym ? ` (기준 ${ym})` : ''}.`
