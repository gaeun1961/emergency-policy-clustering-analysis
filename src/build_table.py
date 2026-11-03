"""시군구 통합 테이블 생성

실행: 레포 루트에서 python -m src.build_table
입력: data/processed/population_sigungu_202512.csv (기준 코드표), single_household_sigungu_202512.csv
      (둘 다 python -m src.population),
      data/raw/ (data/README.md 참고), data/region_mapping.csv
출력: data/processed/sigungu_table.csv, data/processed/unmatched.csv
"""
from pathlib import Path

import pandas as pd

from .loaders import load_and_validate_file
from .regions import attach_code, load_mapping, rollup

ROOT = Path(__file__).resolve().parents[1]

# 출처별 설정. 받은 파일의 컬럼명이 다르면 여기만 고친다 (컬럼명은 clean_col_name 적용 후 기준: 공백·괄호 제거).
# value=None 이면 행 개수(기관 수)를 센다. how: 일반구를 상위 시로 합칠 때 집계 방법.
SOURCES = {
    '응급의료기관수': dict(file='emergency/institutions', header=[4, 3, 0], sido='지역', sgg='시군구', value=None, how='sum'),
    '응급의료시설수': dict(file='emergency/facilities', header=[3, 4, 0], sido='지역', sgg='시군구', value=None, how='sum'),
    # ponytail: 일반구만 있는 시는 단순 평균, 정확히 하려면 인구 가중 평균
    '응급의료시설_평균접근거리_km': dict(file='accessibility/ngii_emergency_access', sido='시도', sgg='시군구', value='평균거리', how='mean'),
    '등록장애인수': dict(file='welfare/disabled', sido='시도', sgg='시군구', value='등록장애인수', how='sum'),
    '기초수급자수': dict(file='welfare/basic_livelihood', sido='시도', sgg='시군구', value='수급자수', how='sum'),
}
# python -m src.population 으로 생성. 코드가 같아서 매핑 없이 바로 붙인다
POP_FILE = ROOT / 'data' / 'processed' / 'population_sigungu_202512.csv'
SINGLE_FILE = ROOT / 'data' / 'processed' / 'single_household_sigungu_202512.csv'


def find(raw, stem):
    hits = [p for ext in ('.csv', '.xlsx') for p in [raw / f'{stem}{ext}'] if p.exists()]
    if not hits:
        raise FileNotFoundError(f'{raw / stem}.csv 또는 .xlsx 가 없음. data/README.md 참고')
    return hits[0]


def to_num(s):
    return pd.to_numeric(s.astype(str).str.replace(',', '').str.strip(), errors='coerce')


def read_processed(path):
    if not Path(path).exists():
        raise FileNotFoundError(f'{path} 가 없음. 먼저 python -m src.population 실행')
    df = pd.read_csv(path, dtype={'행정기관코드': str}).fillna({'시군구': ''})
    return df.rename(columns={'행정기관코드': 'code'}).set_index('code')


def load_population(pop_file, single_file):
    """시군구 인구 기준 코드표 + 1인세대 -> (master, 통합 테이블 뼈대)"""
    units = read_processed(pop_file)
    master = units[['시도', '시군구']].reset_index().assign(unit=lambda m: m['code'])
    units = units.join(read_processed(single_file).drop(columns=['시도', '시군구']))
    units['독거노인비율'] = units['65세이상1인세대수'] / units['65세이상인구']
    return master, units


def load_source(raw, name, cfg, master, mapping):
    req = [c for c in (cfg['sido'], cfg['sgg'], cfg['value']) if c]
    df = load_and_validate_file(find(raw, cfg['file']), cfg.get('header', [0, 1, 2, 3]), req)
    if df is None:
        raise ValueError(f'{name}: 필수 컬럼 {req} 를 못 찾음. SOURCES 설정을 파일에 맞게 고쳐줘')
    df = df.rename(columns={cfg['sido']: '시도', cfg['sgg']: '시군구'})
    df[name] = 1 if cfg['value'] is None else to_num(df[cfg['value']])
    hit, miss = attach_code(df, master, mapping)
    return rollup(hit, name, cfg['how'], has_subtotals=cfg['value'] is not None), miss.assign(출처=name)


def main(raw=ROOT / 'data' / 'raw', out=ROOT / 'data' / 'processed',
         mapping_file=ROOT / 'data' / 'region_mapping.csv', pop_file=POP_FILE, single_file=SINGLE_FILE):
    raw, out = Path(raw), Path(out)
    mapping = load_mapping(mapping_file)
    master, table = load_population(pop_file, single_file)

    misses = []
    for name, cfg in SOURCES.items():
        try:
            table[name], miss = load_source(raw, name, cfg, master, mapping)
            if cfg['value'] is None:  # 기관이 없는 시군구는 0개
                table[name] = table[name].fillna(0).astype(int)
        except FileNotFoundError as e:
            print(f'[건너뜀] {name}: {e}')
            continue
        misses.append(miss[['출처', '시도', '시군구']])

    out.mkdir(parents=True, exist_ok=True)
    table.index.name = 'code'
    table.to_csv(out / 'sigungu_table.csv', encoding='utf-8-sig')

    unmatched = pd.concat(misses) if misses else pd.DataFrame(columns=['출처', '시도', '시군구'])
    unmatched = unmatched.value_counts().rename('행수').reset_index()
    unmatched.to_csv(out / 'unmatched.csv', index=False, encoding='utf-8-sig')

    print(f'\n시군구 {len(table)}개 -> {out / "sigungu_table.csv"}')
    print(f'\n[매칭 안 된 출처 행] {len(unmatched)}건 (region_mapping.csv에 추가해서 해결)')
    print(unmatched.to_string(index=False) if len(unmatched) else '없음')
    empty = table[table.isna().any(axis=1)]
    print(f'\n[값이 빠진 시군구] {len(empty)}개')
    print(empty.to_string() if len(empty) else '없음')
    return table, unmatched


if __name__ == '__main__':
    main()
