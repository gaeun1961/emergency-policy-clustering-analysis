/**
 * 색 테마 (청록·남색). 등급·점수·거리·클러스터를 모두 한 색상 계열의 진하기로 표현한다.
 * 모든 램프는 dataviz 검증 스크립트 --ordinal 통과(한 색상, 명도 단조, 가장 연한 칸도 배경 대비 2:1 이상),
 * 등급 3색(해당 없음·준·이중)은 --pairs all 색각 이상 구분 통과 (최소 ΔE 13.3, 정상 시각 16.5).
 */
export const T = {
  ramp: ['#80bbc3', '#5aa1ad', '#33808f', '#1b6073', '#0d4256'],   // 5단계, 연한 -> 진한 (진할수록 취약)
  grade: { double: '#14506a', near: '#7db9c1', none: '#dcdfde' },
  cluster: ['#d3dbdb', '#6aafb8', '#1a5970'] as [string, string, string], // 0 도시(중립) / 1 센터 원거리 / 2 응급의료 취약
  accent: '#14506a',
  accentSoft: '#e8f2f3',
  marker: '#2b3640',   // 응급의료기관 마커: 보조 정보라 차분한 진회색
  bg: '#f4f6f6',
  surface: '#fcfdfd',
  ink: '#15202a',
  ink2: '#52606b',
  line: '#dfe5e6',
}

/** 연한 배경(준 이중 취약 등) 위 글자는 어두운 색 */
export const textOn = (bg: string) => (bg === T.grade.near || bg === T.grade.none || bg === T.cluster[0] ? T.ink : '#fff')
