"""읍면동(행정동) 드릴다운 지표: 시군구 판정은 그대로 두고, 시군구 안 행정동별 접근성 편차를 본다

실행: 레포 루트에서 python -m src.emd_metrics [기준연월, 기본 src/config.py YM]   (python -m src.accessibility 다음)
입력: data/processed/accessibility_points.csv (기준점별 지표·최근접 기관, 섬 읍·면은 리 단위)
      data/raw/emd_population/{연월}/*.json (행정동 인구 API 캐시, 10세 단위 연령), emd_population_{연월}.csv (출장소 -> 소속 행정동)
      data/processed/population_sigungu_{연월}.csv (시군구 65세 이상 인구)
출력: data/processed/emd_metrics.csv: 행정동별 인구·고령 비율·주행시간 지표·전국 접근성 점수와 구간
      data/processed/emd_li_metrics.csv: 섬 읍·면의 리별 인구·고령 비율 (주행시간은 웹이 기준점에서 계산)
      data/processed/emd_usage.csv: 행정동별 이용 기관 비율 (src.accessibility.facility_usage, 섬 읍·면은 리 인구로)

고령(65세 이상): API는 10세 단위라 60대를 나눠야 한다. 시군구마다 r = (시군구 65세 이상 - 70세 이상) / 60대 를 구해
  행정동 65세 이상 = 70세 이상 + 60대 × r 로 추정한다(행정동 합 = 시군구 65세 이상).
접근성 점수: 시군구와 같은 3개 지표(최근접 응급의료기관·센터 주행분, 30분 내 기관 수)의 전국 행정동 3,557곳 백분위 평균.
  구간은 점수 사분위: '하위 25%'(가장 취약) / '하위 25~50%' / '상위 25~50%' / '상위 25%'
독거노인·장애인 비율은 행정동 단위 공개 통계가 없어 시군구 값만 쓴다.
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

from .accessibility import MINUTES, facility_usage
from .config import YM

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / 'data' / 'processed'
POINTS = PROC / 'accessibility_points.csv'
ACCESS = ['최근접_응급의료기관_분', '최근접_권역지역센터_분', f'{MINUTES}분내_응급의료기관수']
REVERSE = [f'{MINUTES}분내_응급의료기관수']
RAW = ['최근접_응급의료기관_분_원값', '최근접_권역지역센터_분_원값']
BANDS = ['상위 25%', '상위 25~50%', '하위 25~50%', '하위 25%']  # 접근성 좋은 순. 점수가 높을수록 취약


def age_counts(ym):
    """API 캐시 -> (행정동코드, 리) 별 총인구·60대·70세 이상. 리가 없는 동은 리=''"""
    m = pd.read_csv(PROC / f'emd_population_{ym}.csv', dtype={'행정동코드': str, '소속행정동코드': str})
    parent = dict(zip(m['행정동코드'], m['소속행정동코드']))
    cnt = defaultdict(lambda: np.zeros(3))
    for f in (ROOT / 'data' / 'raw' / 'emd_population' / ym).glob('*.json'):
        for x in json.loads(f.read_text(encoding='utf-8')):
            n = lambda k: int(x.get(f'male{k}AgeNmprCnt', 0)) + int(x.get(f'feml{k}AgeNmprCnt', 0))  # noqa: E731
            cnt[(parent.get(x['admmCd'], x['admmCd']), x.get('liNm') or '')] += [int(x['totNmprCnt']), n(60),
                                                                                 sum(n(a) for a in (70, 80, 90, 100))]
    return pd.DataFrame([(c, li, *v) for (c, li), v in cnt.items()], columns=['행정동코드', '리', '인구', '60대', '70세이상'])


def main(ym=YM):
    pts = pd.read_csv(POINTS, dtype={'기준점ID': str, '행정동코드': str, '행정기관코드': str})
    sgg_of = pts.drop_duplicates('행정동코드').set_index('행정동코드')['행정기관코드']

    # 고령: 60대를 시군구별 비율로 나눠 65세 이상 추정
    a = age_counts(ym)
    a['시군구'] = a['행정동코드'].map(sgg_of)
    assert a['시군구'].notna().all(), a[a['시군구'].isna()]
    sgg = a.groupby('시군구')[['60대', '70세이상']].sum()
    pop65 = pd.read_csv(PROC / f'population_sigungu_{ym}.csv', dtype={'행정기관코드': str}).set_index('행정기관코드')['65세이상인구']
    r = ((pop65.reindex(sgg.index) - sgg['70세이상']) / sgg['60대']).clip(0, 1)
    a['65세이상'] = a['70세이상'] + a['60대'] * a['시군구'].map(r)
    emd_age = a.groupby('행정동코드')[['인구', '65세이상']].sum()

    # 주행시간 지표: 기준점(섬 읍·면은 리) -> 행정동 인구가중 (시군구와 같은 방식, 소수 3자리)
    w = pts.groupby('행정동코드')['가중치'].sum()
    t = pts[ACCESS + RAW].mul(pts['가중치'], axis=0).groupby(pts['행정동코드']).sum().div(w, axis=0).round(3)
    approx = (pts['최근접기관_근사'] | pts['최근접센터_근사']).astype(float)
    t['근사반영_인구비율'] = (approx * pts['가중치']).groupby(pts['행정동코드']).sum().div(w).round(6)
    t['기준점수'] = pts.groupby('행정동코드').size()

    X = t[ACCESS].copy()
    X[REVERSE] = -X[REVERSE]
    t['접근성점수'] = (X.rank(pct=True) * 100).mean(axis=1)
    cuts = t['접근성점수'].quantile([0.25, 0.5, 0.75]).to_numpy()
    t['접근성구간'] = [BANDS[int((v >= cuts - 1e-9).sum())] for v in t['접근성점수']]  # 경계값은 위 구간 (웹과 같은 비교)

    names = pts.drop_duplicates('행정동코드').set_index('행정동코드')['지점']
    # 인구는 API 합계(행정동 전체). 주행시간 가중치(w)는 좌표가 있는 기준점만이라 섬에서 몇 명 적을 수 있다
    out = pd.DataFrame({'시군구코드': sgg_of, '이름': names.str.split().str[-1]}).join(emd_age)
    out['고령인구비율'] = out['65세이상'] / out['인구']
    print(f'[가중치] 기준점 인구가 API 인구와 다른 행정동: {(w.reindex(out.index) != out["인구"]).sum()}곳 '
          f'(차이 합 {int((out["인구"] - w.reindex(out.index)).sum())}명, 좌표 없는 섬 리)')
    out = out.join(t).drop(columns='65세이상')
    out.index.name = '행정동코드'
    out.round(6).to_csv(PROC / 'emd_metrics.csv', encoding='utf-8-sig')

    # 섬 읍·면 리별 인구·고령 (리 기준점이 있는 곳만)
    li = pts[pts['기준점ID'].str.contains('-')].assign(리=lambda d: d['기준점ID'].str.split('-').str[1])
    li = li[['행정동코드', '리', '가중치']].merge(a[['행정동코드', '리', '65세이상']], on=['행정동코드', '리'], how='left')
    li['고령인구비율'] = li['65세이상'] / li['가중치']
    li.rename(columns={'가중치': '인구'}).drop(columns='65세이상').round(6).to_csv(PROC / 'emd_li_metrics.csv', index=False, encoding='utf-8-sig')

    facility_usage(pts, '행정동코드').round(6).to_csv(PROC / 'emd_usage.csv', index=False, encoding='utf-8-sig')

    # 검증·요약
    chk = out.groupby('시군구코드')['인구'].sum()
    pop = pd.read_csv(PROC / f'population_sigungu_{ym}.csv', dtype={'행정기관코드': str}).set_index('행정기관코드')['총인구']
    print(f'[행정동] {len(out)}곳, 인구 합 {int(out["인구"].sum()):,}명, 시군구 합계 불일치 {(chk != pop.reindex(chk.index)).sum()}곳')
    e65 = (out['고령인구비율'] * out['인구']).groupby(out['시군구코드']).sum()
    print(f'[고령] 행정동 65세 이상 합 - 시군구 65세 이상 최대 차이 {abs(e65 - pop65.reindex(e65.index)).max():.3f}명, '
          f'60대 중 65~69세 비율 r: {r.min():.3f}~{r.max():.3f} (중앙값 {r.median():.3f})')
    print(f'[구간] 점수 사분위 {cuts.round(2).tolist()}, 하위 25% {(out["접근성구간"] == BANDS[-1]).sum()}곳')
    small = (out['인구'] < 500).sum()
    print(f'[인구 500명 미만] {small}곳, 근사 반영 행정동 {(out["근사반영_인구비율"] > 0).sum()}곳')
    return out, cuts


if __name__ == '__main__':
    main(*sys.argv[1:2])
