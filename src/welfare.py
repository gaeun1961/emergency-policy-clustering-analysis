"""복지로 기초생활보장 수급자 통계 -> 시군구 수급자 비율 (참고·검증 지표)

이중 취약 판정·점수·등급에는 쓰지 않는다. 대시보드 지역 상세의 참고 한 줄과 README 검증 절에만 쓴다.

실행: 레포 루트에서 python -m src.welfare
입력: data/raw/welfare/*.csv (cp949, 통계연월·통계시도명·통계시군구명·수급자구분·연령구간·성별·수급자수)
      data/processed/population_sigungu_{기준연월}.csv (기준 코드표·주민등록인구, src/config.py)
      검증용: data/processed/sigungu_table.csv (고령·독거 비율), outputs/sigungu_scores.csv (등급)
출력: data/processed/welfare_rate.csv
"""
from pathlib import Path

import pandas as pd

from .config import YM
from .regions import attach_code, load_mapping, rollup

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data' / 'raw' / 'welfare'
OUT = ROOT / 'data' / 'processed' / 'welfare_rate.csv'
POP_CSV = ROOT / 'data' / 'processed' / f'population_sigungu_{YM}.csv'
KINDS = ['일반수급자', '시설수급자']


def read_file(path):
    """연령·성별 행을 시군구 x 수급자구분으로 합친다 -> 시도, 시군구, 일반수급자, 시설수급자, 수급자수, 기준연월"""
    df = pd.read_csv(path, encoding='cp949', dtype={'통계연월': str})
    months = df['통계연월'].unique()
    assert len(months) == 1, f'통계연월이 여러 개: {months}'
    wide = (df.pivot_table(index=['통계시도명', '통계시군구명'], columns='수급자구분', values='수급자수', aggfunc='sum')
            .reindex(columns=KINDS).fillna(0).astype(int).reset_index()
            .rename(columns={'통계시도명': '시도', '통계시군구명': '시군구'}))
    wide.columns.name = None
    wide['수급자수'] = wide[KINDS].sum(axis=1)
    return wide, months[0]


def build(raw=RAW, out=OUT, pop_csv=POP_CSV, mapping_file=ROOT / 'data' / 'region_mapping.csv'):
    files = sorted(Path(raw).glob('*.csv'))
    if not files:
        raise FileNotFoundError(f'{raw} 에 csv 가 없음 (data/README.md 4-2 참고)')
    df, month = read_file(files[0])
    if month != YM:
        print(f'[경고] 수급자 통계 기준월 {month} 이 인구 기준월 {YM} 과 다름')

    pop = pd.read_csv(pop_csv, dtype={'행정기관코드': str}).fillna({'시군구': ''})
    master = pop.rename(columns={'행정기관코드': 'code'})[['code', '시도', '시군구']].assign(unit=lambda m: m['code'])
    hit, miss = attach_code(df, master, load_mapping(mapping_file))
    # 일반구 행(수원시장안구 등)이 있으면 상위 시로 합친다. attach_code 는 이런 행의 code 자리에 구 이름을 넣는다
    gu = hit.loc[~hit['code'].isin(master['code']), ['시도', '시군구', 'unit']]

    units = master.set_index('code')[['시도', '시군구']]
    for c in KINDS + ['수급자수']:
        units[c] = rollup(hit, c, 'sum', has_subtotals=True)
    units['총인구'] = pop.set_index('행정기관코드')['총인구']
    units['수급자비율'] = units['수급자수'] / units['총인구']
    units['수급자비율_순위'] = units['수급자비율'].rank(ascending=False, method='min').astype('Int64')  # 1위 = 비율 가장 높음
    units['기준연월'] = month
    units.index.name = '행정기관코드'

    ok = validate(units, miss, gu, int(df['수급자수'].sum()))
    out.parent.mkdir(parents=True, exist_ok=True)
    units.to_csv(out, encoding='utf-8-sig')
    print(f'-> {out}')
    return units, ok


def validate(units, miss, gu, file_total):
    total = units['수급자수'].sum()
    lack = units[units['수급자수'].isna()]
    print(f'\n[welfare] 최종 행 수: {len(units)}개 시군구 (값 있는 곳 {len(units) - len(lack)}개)')
    print(f'전국 합계: {int(total):,}명 (파일 합계 {file_total:,})', '일치' if total == file_total else '불일치')
    print('일반구 -> 상위 시 합산: 없음 (파일이 시 단위)' if gu.empty else f'일반구 -> 상위 시 합산:\n{gu.to_string()}')
    print('매칭 실패(파일 -> 코드표): 없음' if miss.empty else f'매칭 실패(파일 -> 코드표):\n{miss.to_string()}')
    print('값 없는 시군구(코드표 -> 파일): 없음' if lack.empty else f'값 없는 시군구(코드표 -> 파일):\n{lack.to_string()}')
    return total == file_total and miss.empty and lack.empty


def compare(units, table=ROOT / 'data' / 'processed' / 'sigungu_table.csv', scores=ROOT / 'outputs' / 'sigungu_scores.csv'):
    """검증: 이중 취약 시군구의 수급자 비율 평균 vs 전체, 고령·독거 비율과의 상관 (README 검증 절)"""
    t = pd.read_csv(table, dtype={'code': str}).set_index('code')
    s = pd.read_csv(scores, dtype={'code': str}).set_index('code').fillna({'등급': ''})
    d = pd.DataFrame({'수급자비율': units['수급자비율'], '고령인구비율': t['65세이상인구'] / t['총인구'],
                      '독거노인비율': t['독거노인비율'], '등급': s['등급']})
    dv = d[d['등급'] == '이중 취약']
    res = {
        '이중취약_수': len(dv), '이중취약_평균': dv['수급자비율'].mean(), '전체_평균': d['수급자비율'].mean(),
        '이중취약_중앙값': dv['수급자비율'].median(), '전체_중앙값': d['수급자비율'].median(),
        **{f'상관_{k}_{m}': d['수급자비율'].corr(d[k], method=m) for k in ['고령인구비율', '독거노인비율'] for m in ['spearman', 'pearson']},
    }
    print(f"\n[검증] 이중 취약 {res['이중취약_수']}곳 수급자 비율 평균 {res['이중취약_평균']:.2%} (중앙값 {res['이중취약_중앙값']:.2%})"
          f" vs 전체 229곳 평균 {res['전체_평균']:.2%} (중앙값 {res['전체_중앙값']:.2%})")
    for k in ['고령인구비율', '독거노인비율']:
        print(f"수급자 비율과 {k} 상관: 스피어만 {res[f'상관_{k}_spearman']:.2f}, 피어슨 {res[f'상관_{k}_pearson']:.2f}")
    return res


if __name__ == '__main__':
    u, _ = build()
    compare(u)
