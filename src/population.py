"""행안부 주민등록 연령별 인구현황(시도별 xlsx) -> 시군구 인구 기준 코드표

실행: 레포 루트에서 python -m src.population
입력: data/raw/population/{YM}_{YM}_연령별인구현황_{지역}.xlsx (지역별 + 검증용 '전국')
출력: data/processed/population_sigungu_{YM}.csv
"""
from pathlib import Path

import pandas as pd

from .loaders import clean_col_name
from .regions import age_start, build_master, rollup

ROOT = Path(__file__).resolve().parents[1]
YM = '202512'
RAW = ROOT / 'data' / 'raw' / 'population'
OUT = ROOT / 'data' / 'processed' / f'population_sigungu_{YM}.csv'
NATIONAL_TOTAL = 51_117_378  # 전국 파일의 2025.12 총인구


def read_file(path):
    """3행(0-index)이 헤더, 계/남/여 블록이 반복되므로 첫 블록(계)만 쓴다."""
    df = pd.read_excel(path, header=3, dtype=str)
    end = next((i for i, c in enumerate(df.columns) if c.startswith('남 인구수')), len(df.columns))
    df = df.iloc[:, :end]
    df.columns = [clean_col_name(c) for c in df.columns]
    return df


def to_num(s):
    return pd.to_numeric(s.astype(str).str.replace(',', '').str.strip(), errors='coerce')


def age_sum(df, start):
    """start세 이상 인구 합. 해당 연령 컬럼이 파일에 없으면 NaN"""
    cols = [c for c in df.columns if (age_start(c) or -1) >= start]
    if start not in {age_start(c) for c in df.columns}:
        return pd.Series(float('nan'), index=df.index)
    return df[cols].apply(to_num).sum(axis=1, min_count=len(cols))  # 연령 칸이 빈 파일의 행은 0이 아니라 NaN


def build(raw=RAW, out=OUT, ym=YM):
    files = sorted(Path(raw).glob(f'{ym}_{ym}_연령별인구현황_*.xlsx'))
    national = [f for f in files if f.stem.endswith('_전국')]
    regional = [f for f in files if f not in national]
    if not regional or not national:
        raise FileNotFoundError(f'{raw} 에 지역별 파일과 전국 파일이 모두 있어야 함 (data/README.md 참고)')

    parts = []
    for f in regional:
        df = read_file(f)
        no_age = [s for s in (65, 80) if s not in {age_start(c) for c in df.columns}]
        if no_age:
            print(f'[경고] {f.name}: {no_age}세 시작 연령 컬럼 없음 -> 해당 값 NaN. 5세 단위 0~100세 이상 전체로 다시 받아야 함')
        parts.append(df)
    pop = pd.concat(parts, ignore_index=True)

    master = build_master(pop)  # 시도 합계 행 제외, 일반구 -> 상위 시 unit
    pop = master.join(pd.DataFrame({'총인구': to_num(pop['총인구수']),
                                    '65세이상인구': age_sum(pop, 65),
                                    '80세이상인구': age_sum(pop, 80)}))
    units = master[master['code'] == master['unit']].set_index('code')[['시도', '시군구']]
    for col in ('총인구', '65세이상인구', '80세이상인구'):
        units[col] = rollup(pop, col, lambda s: s.sum(min_count=len(s)), has_subtotals=True)  # NaN 있으면 NaN 유지
    units = units.sort_index()
    units.index.name = '행정기관코드'

    ok = validate(units, read_file(national[0]))
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    units.to_csv(out, encoding='utf-8-sig')
    print(f'-> {out}')
    return units, ok


def validate(units, national):
    """시도별 시군구 합 == 전국 파일 시도 총인구, 전국 합 == NATIONAL_TOTAL"""
    code = national['행정기관코드'].astype(str).str.zfill(10)
    is_sido = code.str[2:] == '00000000'  # 전국(00)과 시도 합계 행
    sido_total = pd.Series(to_num(national['총인구수'])[is_sido].values, index=code[is_sido].str[:2])
    nat_total = sido_total.pop('00')

    got = units.groupby(units.index.str[:2])['총인구'].sum()
    cmp = pd.DataFrame({'시도': units.groupby(units.index.str[:2])['시도'].first(),
                        '시군구합': got, '전국파일': sido_total}).fillna({'시군구합': 0})
    cmp['차이'] = cmp['시군구합'] - cmp['전국파일']
    bad = cmp[cmp['차이'] != 0]

    print(f'\n최종 행 수: {len(units)}개 시군구')
    print(f'전국 합계: {int(got.sum()):,}명 (전국 파일 {int(nat_total):,}, 기대값 {NATIONAL_TOTAL:,})',
          '일치' if got.sum() == nat_total == NATIONAL_TOTAL else '불일치')
    print('시도별 합계: 모두 일치' if bad.empty else f'시도별 불일치:\n{bad.to_string()}')
    missing = units[units[['65세이상인구', '80세이상인구']].isna().any(axis=1)]
    if len(missing):
        print(f'65세/80세 이상 인구 없음: {len(missing)}개 ({", ".join(missing["시도"].unique())})')
    return bad.empty and got.sum() == nat_total == NATIONAL_TOTAL and missing.empty


if __name__ == '__main__':
    build()
