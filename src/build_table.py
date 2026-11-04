"""시군구 통합 테이블 생성

실행: 레포 루트에서 python -m src.build_table
입력: data/processed/ 의 시군구 표 (모두 같은 행정기관코드 5자리, 각 스크립트가 매칭·검증을 마친 결과)
      population_sigungu_{기준연월}.csv (기준 코드표), single_household_sigungu_{기준연월}.csv  <- python -m src.population
      disability_sigungu_{장애인 기준연도}.csv  <- python -m src.disability   (기준 시점은 src/config.py)
      accessibility_sigungu.csv    <- python -m src.fetch_emergency, src.emd_centers, src.accessibility
출력: data/processed/sigungu_table.csv
"""
from pathlib import Path

import pandas as pd

from .config import DISABILITY_YEAR, YM

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / 'data' / 'processed'
POP_FILE = PROC / f'population_sigungu_{YM}.csv'
SINGLE_FILE = PROC / f'single_household_sigungu_{YM}.csv'
DISABILITY_FILE = PROC / f'disability_sigungu_{DISABILITY_YEAR}.csv'
ACCESS_FILE = PROC / 'accessibility_sigungu.csv'


def read_processed(path):
    if not Path(path).exists():
        raise FileNotFoundError(f'{path} 가 없음. data/README.md 실행 순서 참고')
    df = pd.read_csv(path, dtype={'행정기관코드': str}).fillna({'시군구': ''})
    return df.rename(columns={'행정기관코드': 'code'}).set_index('code')


def main(out=PROC, pop_file=POP_FILE, single_file=SINGLE_FILE, disability_file=DISABILITY_FILE, access_file=ACCESS_FILE):
    table = read_processed(pop_file)
    for f in (single_file, disability_file, access_file):
        table = table.join(read_processed(f).drop(columns=['시도', '시군구']))
    table['독거노인비율'] = table['65세이상1인세대수'] / table['65세이상인구']
    table['장애인비율'] = table['등록장애인수'] / table['총인구']

    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    table.to_csv(out / 'sigungu_table.csv', encoding='utf-8-sig')
    empty = table[table.isna().any(axis=1)]
    print(f'시군구 {len(table)}개, 컬럼 {len(table.columns)}개 -> {out / "sigungu_table.csv"}')
    print(f'[값이 빠진 시군구] {len(empty)}개' + (f'\n{empty.to_string()}' if len(empty) else ''))
    return table


if __name__ == '__main__':
    main()
