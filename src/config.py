"""데이터 기준 시점 (한 곳에서 바꾼다)

기준월을 갱신할 때는 이 파일만 고치고, 실행 순서(README)대로 다시 만든다.
- YM: 주민등록 인구·1인세대·행정동 인구 API 기준연월 (raw 파일명과 processed 파일명에 들어감)
- BOUNDARY_VERSION: vuski/admdongkor 행정동 경계 버전 (기준연월과 같은 시점의 행정구역)
- DISABILITY_YEAR: KOSIS 등록장애인 기준연도 (연 1회, 연말 기준)
"""
YM = '202512'
BOUNDARY_VERSION = 'ver20251231'
BOUNDARY_NOTE = '2026.7 인천·광주전남 개편 이전'  # 대시보드 meta 의 경계 설명
DISABILITY_YEAR = '2025'

YM_LABEL = f'{YM[:4]}-{YM[4:]}'                                                       # '2025-12'
BOUNDARY_DATE = f'{BOUNDARY_VERSION[3:7]}-{BOUNDARY_VERSION[7:9]}-{BOUNDARY_VERSION[9:]}'  # '2025-12-31'
