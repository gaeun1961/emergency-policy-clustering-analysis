"""KOSIS 등록장애인(DT_11761_N009, 시군구별·장애정도별·성별) -> 시군구 등록장애인 수

실행: 레포 루트에서 python -m src.disability
입력: data/raw/disability/*.xlsx (시트 '데이터'), data/processed/population_sigungu_202512.csv (기준 코드표)
출력: data/processed/disability_sigungu_2025.csv
"""
from pathlib import Path

import pandas as pd

from .regions import attach_code, load_mapping, rollup

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data' / 'raw' / 'disability'
OUT = ROOT / 'data' / 'processed' / 'disability_sigungu_2025.csv'
POP_CSV = ROOT / 'data' / 'processed' / 'population_sigungu_202512.csv'
NATIONAL_TOTAL = 2_627_761  # 2025년 연말 전국 등록장애인


def read_file(path):
    """0~2행 머리글, 열 = 시도 / 시군구 / 등록장애인수(장애정도 합계, 성별 계)"""
    df = pd.read_excel(path, sheet_name='데이터', header=None, skiprows=3, dtype=str).iloc[:, :3]
    df.columns = ['시도', '시군구', '등록장애인수']
    df['시도'] = df['시도'].ffill()
    df['등록장애인수'] = pd.to_numeric(df['등록장애인수'].str.replace(',', ''), errors='coerce')
    # 세종처럼 시군구 행 없이 '소계'만 있는 시도는 소계가 곧 시군구 값
    only_subtotal = df.groupby('시도')['시군구'].transform('size') == 1
    df.loc[only_subtotal, '시군구'] = df.loc[only_subtotal, '시도']
    return df


def build(raw=RAW, out=OUT, pop_csv=POP_CSV, mapping_file=ROOT / 'data' / 'region_mapping.csv'):
    files = sorted(Path(raw).glob('*.xlsx'))
    if not files:
        raise FileNotFoundError(f'{raw} 에 xlsx 가 없음 (data/README.md 참고)')
    df = read_file(files[0])
    file_total = df.loc[df['시도'] == '전국', '등록장애인수'].sum()

    pop = pd.read_csv(pop_csv, dtype={'행정기관코드': str}).fillna({'시군구': ''})
    master = pop.rename(columns={'행정기관코드': 'code'})[['code', '시도', '시군구']].assign(unit=lambda m: m['code'])
    hit, miss = attach_code(df, master, load_mapping(mapping_file))  # 소계·전국 행은 여기서 빠짐
    # 일반구(수원시장안구 등)만 있고 시 합계 행이 없음 -> 구 행을 합쳐 상위 시로
    units = master.set_index('code')[['시도', '시군구']]
    units['등록장애인수'] = rollup(hit, '등록장애인수', 'sum', has_subtotals=True)
    units.index.name = '행정기관코드'

    ok = validate(units, miss, file_total)
    out.parent.mkdir(parents=True, exist_ok=True)
    units.to_csv(out, encoding='utf-8-sig')
    print(f'-> {out}')
    return units, ok


def validate(units, miss, file_total):
    total = units['등록장애인수'].sum()
    lack = units[units['등록장애인수'].isna()]
    print(f'\n[disability] 최종 행 수: {len(units)}개 시군구 (값 있는 곳 {len(units) - len(lack)}개)')
    print(f'전국 합계: {int(total):,}명 (파일 전국 소계 {int(file_total):,}, 기대값 {NATIONAL_TOTAL:,})',
          '일치' if total == file_total == NATIONAL_TOTAL else '불일치')
    print('매칭 실패(파일 -> 코드표): 없음' if miss.empty else f'매칭 실패(파일 -> 코드표):\n{miss.to_string()}')
    print('값 없는 시군구(코드표 -> 파일): 없음' if lack.empty else f'값 없는 시군구(코드표 -> 파일):\n{lack.to_string()}')
    return total == file_total == NATIONAL_TOTAL and miss.empty and lack.empty


if __name__ == '__main__':
    build()
