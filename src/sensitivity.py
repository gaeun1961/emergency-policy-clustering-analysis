"""이중 취약 판정 민감도: 기준선·지표 구성·가중치를 바꿔도 같은 지역이 고르게 나오는지

판정(notebooks/sigungu_clustering.ipynb)과 같은 계산을 다시 한다: 지표마다 전국 백분위(작을수록 취약한 30분 내 기관 수는 뒤집음)
-> 접근성 점수(최근접 응급의료기관·센터 주행시간, 30분 내 기관 수)와 복지 점수(고령·독거·장애 비율)는 백분위 평균
-> 두 점수가 모두 상위 TOP 이면 이중 취약. 기본(25%, 같은 가중치)이 기존 36곳을 그대로 재현하는지부터 확인한다.

실행: 레포 루트에서 python -m src.sensitivity
입력: data/processed/sigungu_table.csv, outputs/sigungu_scores.csv (기존 등급)
출력: 화면 표 (변형별 이중 취약 수, 기존 36곳 중 유지 수)
"""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
WELFARE = ['고령인구비율', '독거노인비율', '장애인비율']
ACCESS = ['최근접_응급의료기관_분', '최근접_권역지역센터_분', '30분내_응급의료기관수']
REVERSE = ['30분내_응급의료기관수']


def load(table=ROOT / 'data' / 'processed' / 'sigungu_table.csv'):
    t = pd.read_csv(table, dtype={'code': str}).set_index('code')
    t['고령인구비율'] = t['65세이상인구'] / t['총인구']
    pct = t[WELFARE + ACCESS].copy()
    pct[REVERSE] = -pct[REVERSE]
    return pct.rank(pct=True) * 100


def double(pct, top=0.25, access=ACCESS, welfare=WELFARE, weights=None):
    """이중 취약 시군구 코드 집합 (weights: 지표 -> 가중치, 없으면 1)"""
    w = pd.Series(1.0, index=pct.columns) if weights is None else pd.Series(weights).reindex(pct.columns).fillna(1.0)
    score = lambda cols: (pct[cols] * w[cols]).sum(axis=1) / w[cols].sum()
    a, b = score(list(access)), score(list(welfare))
    return set(pct.index[(a >= a.quantile(1 - top)) & (b >= b.quantile(1 - top))])


def variants():
    yield '기본 (상위 25%, 같은 가중치)', {}
    for top in (0.20, 0.30):
        yield f'기준선 상위 {top:.0%}', {'top': top}
    for f in ACCESS:
        yield f'접근성에서 {f} 빼기', {'access': [x for x in ACCESS if x != f]}
    for f in WELFARE:
        yield f'복지에서 {f} 빼기', {'welfare': [x for x in WELFARE if x != f]}
    yield '독거노인비율 가중치 2배', {'weights': {'독거노인비율': 2}}
    yield '최근접 응급의료기관 주행시간 가중치 2배', {'weights': {'최근접_응급의료기관_분': 2}}


def run(scores=ROOT / 'outputs' / 'sigungu_scores.csv'):
    s = pd.read_csv(scores, dtype={'code': str}).set_index('code').fillna({'등급': ''})
    base = set(s.index[s['등급'] == '이중 취약'])
    pct = load()
    rows = []
    for name, kw in variants():
        d = double(pct, **kw)
        rows.append({'변형': name, '이중 취약': len(d), '기존 36곳 중 유지': len(d & base),
                     '유지율': len(d & base) / len(base), '새로 들어온 곳': len(d - base)})
    out = pd.DataFrame(rows)
    assert double(pct) == base, '기본 설정이 기존 판정과 다름 (계산 정의 확인)'
    print(out.to_string(index=False, formatters={'유지율': '{:.0%}'.format}))
    core = set.intersection(*[double(pct, **kw) for _, kw in variants() if 'top' not in kw])
    print(f'\n기준선이 같은 모든 변형(지표 빼기·가중치)에서 계속 이중 취약인 곳: {len(core)}곳 / 기존 {len(base)}곳')
    return out, core, base


if __name__ == '__main__':
    run()
