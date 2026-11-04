"""행안부 주민등록 통계(시도별 xlsx, 5세 단위) -> 시군구 표

- population: 연령별 인구현황 -> 시군구 인구 기준 코드표
- single_household: 성/연령별 주민등록 1인세대수 -> 시군구 1인세대 (65세 이상 = 독거노인)

실행: 레포 루트에서 python -m src.population [population|single_household]  (생략하면 둘 다)
입력: data/raw/{이름}/{YM}_{YM}_..._{지역}.xlsx (지역별 + 검증용 '전국')
출력: data/processed/{이름}_sigungu_{YM}.csv
"""
import sys
from pathlib import Path

import pandas as pd

from .config import YM  # 기준연월
from .loaders import clean_col_name
from .regions import age_start, build_master, rollup

ROOT = Path(__file__).resolve().parents[1]
DATASETS = {
    'population': dict(pattern='연령별인구현황', total='총인구수',
                       cols=('총인구', '65세이상인구', '80세이상인구'), national_total=51_117_378),
    'single_household': dict(pattern='1인세대수', total='총세대수',
                             cols=('1인세대수', '65세이상1인세대수', '80세이상1인세대수'), national_total=None),
}
POP_CSV = ROOT / 'data' / 'processed' / f'population_sigungu_{YM}.csv'


def read_file(path):
    """3행(0-index)이 헤더, 계/남(자)/여(자) 블록이 반복되므로 첫 블록(계)만 쓴다."""
    df = pd.read_excel(path, header=3, dtype=str)
    end = next((i for i, c in enumerate(df.columns) if i > 1 and c.startswith('남')), len(df.columns))
    df = df.iloc[:, :end]
    df.columns = [clean_col_name(c) for c in df.columns]
    return df


def to_num(s):
    return pd.to_numeric(s.astype(str).str.replace(',', '').str.strip(), errors='coerce')


def age_sum(df, start):
    """start세 이상 합. 해당 연령 컬럼이 파일에 없으면 NaN"""
    cols = [c for c in df.columns if (age_start(c) or -1) >= start]
    if start not in {age_start(c) for c in df.columns}:
        return pd.Series(float('nan'), index=df.index)
    return df[cols].apply(to_num).sum(axis=1, min_count=len(cols))  # 연령 칸이 빈 파일의 행은 0이 아니라 NaN


def sido_rows(df, total):
    """시도 합계 행(코드 뒤 8자리 0) -> {시도코드 2자리: 총계}. 전국은 '00'"""
    code = df['행정기관코드'].astype(str).str.zfill(10)
    is_sido = code.str[2:] == '00000000'
    key = code.str[:2].where(df['행정기관'].str.strip() != '전국', '00')  # 전국 코드가 파일마다 다름(0000000000, 1000000000)
    return pd.Series(to_num(df[total])[is_sido].values, index=key[is_sido])


def build(name, raw=None, out=None, ym=YM, ref_codes=None):
    cfg = DATASETS[name]
    raw = Path(raw or ROOT / 'data' / 'raw' / name)
    out = Path(out or ROOT / 'data' / 'processed' / f'{name}_sigungu_{ym}.csv')
    files = sorted(raw.glob(f'{ym}_{ym}_*{cfg["pattern"]}_*.xlsx'))
    national = [f for f in files if f.stem.endswith('_전국')]
    regional = [f for f in files if f not in national]
    if not regional:
        raise FileNotFoundError(f'{raw} 에 {ym} {cfg["pattern"]} 지역별 파일이 없음 (data/README.md 참고)')

    parts = []
    for f in regional:
        df = read_file(f)
        no_age = [s for s in (65, 80) if s not in {age_start(c) for c in df.columns}]
        if no_age:
            print(f'[경고] {f.name}: {no_age}세 시작 연령 컬럼 없음 -> 해당 값 NaN. 5세 단위 0~100세 이상 전체로 다시 받아야 함')
        parts.append(df)
    raw_df = pd.concat(parts, ignore_index=True)

    total_col, old65, old80 = cfg['cols']
    master = build_master(raw_df)  # 시도 합계 행 제외, 일반구 -> 상위 시 unit
    rows = master.join(pd.DataFrame({total_col: to_num(raw_df[cfg['total']]),
                                     old65: age_sum(raw_df, 65), old80: age_sum(raw_df, 80)}))
    units = master[master['code'] == master['unit']].set_index('code')[['시도', '시군구']]
    for col in cfg['cols']:
        units[col] = rollup(rows, col, lambda s: s.sum(min_count=len(s)), has_subtotals=True)  # NaN 있으면 NaN 유지
    units = units.sort_index()
    units.index.name = '행정기관코드'

    print(f'\n[{name}] 최종 행 수: {len(units)}개 시군구')
    if national:
        ref, ref_name = sido_rows(read_file(national[0]), cfg['total']), '전국파일'
    else:
        print('[경고] 전국 파일 없음 -> 지역별 파일 안의 시도 합계 행으로 대신 검증')
        ref, ref_name = sido_rows(raw_df, cfg['total']), '시도합계행'
    ok = validate(units, total_col, ref, ref_name, cfg['national_total'])
    if ref_codes is not None:
        ok &= same_regions(units, ref_codes)
    ok &= bool(national)

    out.parent.mkdir(parents=True, exist_ok=True)
    units.to_csv(out, encoding='utf-8-sig')
    print(f'-> {out}')
    return units, ok


def validate(units, col, ref, ref_name, expected_total=None):
    """시도별 시군구 합 == 기준 시도 총계, 전국 합 == expected_total"""
    nat_total = ref.pop('00') if '00' in ref else None
    got = units.groupby(units.index.str[:2])[col].sum()
    cmp = pd.DataFrame({'시도': units.groupby(units.index.str[:2])['시도'].first(),
                        '시군구합': got, ref_name: ref}).fillna({'시군구합': 0})
    cmp['차이'] = cmp['시군구합'] - cmp[ref_name]
    bad = cmp[cmp['차이'] != 0]
    ok = bad.empty

    msg = f'전국 합계: {int(got.sum()):,}'
    if nat_total is not None:
        msg += f' (전국 파일 {int(nat_total):,})'
        ok &= got.sum() == nat_total
    if expected_total is not None:
        msg += f' (기대값 {expected_total:,})'
        ok &= got.sum() == expected_total
    print(msg)
    print(f'시도별 합계({ref_name} 기준): {len(cmp)}개 시도 모두 일치' if bad.empty else f'시도별 불일치:\n{bad.to_string()}')
    missing = units[units.drop(columns=['시도', '시군구']).isna().any(axis=1)]
    if len(missing):
        print(f'65세/80세 이상 값 없음: {len(missing)}개 ({", ".join(missing["시도"].unique())})')
    return ok and missing.empty


def same_regions(units, ref_codes):
    """시군구 목록이 기준 코드표와 같은지. 다르면 누락/추가 출력"""
    lack, extra = sorted(set(ref_codes) - set(units.index)), sorted(set(units.index) - set(ref_codes))
    print('시군구 목록: 인구 기준 코드표와 동일' if not (lack or extra) else f'시군구 목록 불일치 - 누락 {lack}, 추가 {extra}')
    return not (lack or extra)


if __name__ == '__main__':
    names = sys.argv[1:] or list(DATASETS)
    if 'population' in names:
        build('population')
    if 'single_household' in names:
        ref = pd.read_csv(POP_CSV, dtype={'행정기관코드': str})['행정기관코드']
        build('single_household', ref_codes=ref)
