"""대시보드용 지표 JSON 내보내기

실행: 레포 루트에서 python scripts/export_web_data.py
입력: outputs/sigungu_scores.csv, outputs/double_vulnerable.csv (notebooks/sigungu_clustering.ipynb)
      data/processed/sigungu_table.csv (총인구), data/processed/emergency_facilities.csv (수집일자)
출력: web/public/data/sigungu_metrics.json, web/public/data/meta.json
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'web' / 'public' / 'data'
FIELDS = {  # 내보낼 이름: 원래 컬럼
    '코드': 'code', '시도': '시도', '시군구': '시군구', '총인구': '총인구',
    '고령인구비율': '고령인구비율', '독거노인비율': '독거노인비율', '장애인비율': '장애인비율',
    '최근접_응급의료기관_km': '최근접_응급의료기관_km', '최근접_권역지역센터_km': '최근접_권역지역센터_km',
    '반경30km_기관수': '반경30km_응급의료기관수',
    '접근성점수': '접근성취약점수', '복지점수': '복지취약점수', '등급': '등급',
    '클러스터': '클러스터', '클러스터라벨': '유형', '접근성순위': '접근성순위', '복지순위': '복지순위', '합산점수': '합산점수',
}
SOURCES = [
    {'이름': '행정안전부 주민등록 인구통계 (연령별 인구현황, 성/연령별 1인세대수)', 'url': 'https://jumin.mois.go.kr', '기준': '2025-12'},
    {'이름': '보건복지부 장애인현황 (KOSIS DT_11761_N009)', 'url': 'https://kosis.kr/statHtml/statHtml.do?orgId=117&tblId=DT_11761_N009', '기준': '2025 연말'},
    {'이름': '국립중앙의료원 응급의료정보조회 서비스 (공공데이터포털 OpenAPI)', 'url': 'https://www.data.go.kr', '기준': None},
    {'이름': '카카오 로컬 API (시군구청 좌표)', 'url': 'https://developers.kakao.com', '기준': None},
    {'이름': '행정동 경계 vuski/admdongkor ver20251231 (CC BY 4.0)', 'url': 'https://github.com/vuski/admdongkor', '기준': '2025-12-31'},
    {'이름': '통계청 SGIS 행정구역 경계 (admdongkor 원자료)', 'url': 'https://sgis.kostat.go.kr', '기준': None},
]


def main():
    s = pd.read_csv(ROOT / 'outputs' / 'sigungu_scores.csv', dtype={'code': str}).fillna({'시군구': '', '등급': ''})
    dv = pd.read_csv(ROOT / 'outputs' / 'double_vulnerable.csv', dtype={'code': str})[['code', '합산점수']]
    pop = pd.read_csv(ROOT / 'data' / 'processed' / 'sigungu_table.csv', dtype={'code': str})[['code', '총인구']]
    df = s.merge(dv, on='code', how='left').merge(pop, on='code', how='left')
    assert len(df) == 229 and df['총인구'].notna().all(), '시군구 229개와 총인구가 모두 있어야 함'

    df = df[list(FIELDS.values())].set_axis(list(FIELDS), axis=1).round(4)
    records = [{k: (None if pd.isna(v) else v) for k, v in r.items()} for r in df.to_dict('records')]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'sigungu_metrics.json').write_text(json.dumps(records, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')

    collected = pd.read_csv(ROOT / 'data' / 'processed' / 'emergency_facilities.csv', usecols=['수집일자'])['수집일자'].iloc[0]
    SOURCES[2]['기준'] = collected
    counts = df['등급'].value_counts()
    meta = {
        '기준시점': {'인구·복지': '2025-12', '응급의료기관': collected, '경계': '2025-12-31 (2026.7 인천·광주전남 개편 이전)'},
        '시군구수': len(df),
        '이중취약수': int(counts.get('이중 취약', 0)),
        '준이중취약수': int(counts.get('준 이중 취약', 0)),
        '클러스터': df.groupby('클러스터')['클러스터라벨'].first().to_dict(),
        '출처': SOURCES,
        '생성일시': datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds'),
    }
    (OUT / 'meta.json').write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f'sigungu_metrics.json {len(records)}개, meta: 이중 {meta["이중취약수"]} / 준 {meta["준이중취약수"]}, '
          f'응급의료기관 수집일 {collected}')


if __name__ == '__main__':
    main()
