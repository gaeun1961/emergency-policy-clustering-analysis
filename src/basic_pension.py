"""보건복지부 기초연금 수급 현황 -> 시군구 기초연금 수급률 (참고·검증 지표)

이중 취약 판정·점수·등급에는 쓰지 않는다. 대시보드 지역 상세·보고서의 참고 한 줄과 README 검증 절에만 쓴다.
기초연금은 65세 이상 중 소득·재산 하위 약 70%가 받으므로, 수급률이 높을수록 노인 빈곤층이 두텁다.

실행: 레포 루트에서 python -m src.basic_pension [--download]
입력: data/raw/basic_pension/*.csv (공공데이터포털 15161618 「보건복지부_기초연금인구수급율현황」, cp949,
      통계연월·행정동명(실제로는 '시도 시군구')·65세이상 인구수·수급자수·수급비율, 2025-01~12 월별)
      --download: 공공데이터포털 파일 다운로드(인증키 불필요, 이용허락범위 제한 없음)로 위 폴더에 받는다
      data/processed/population_sigungu_{기준연월}.csv (기준 코드표, src/config.py)
      검증용: sigungu_table.csv, outputs/sigungu_scores.csv, data/processed/welfare_rate.csv
출력: data/processed/basic_pension_rate.csv
"""
import sys
from pathlib import Path

import pandas as pd

from .config import YM, YM_LABEL
from .regions import attach_code, load_mapping, rollup

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data' / 'raw' / 'basic_pension'
OUT = ROOT / 'data' / 'processed' / 'basic_pension_rate.csv'
POP_CSV = ROOT / 'data' / 'processed' / f'population_sigungu_{YM}.csv'
DATASET = ('15161618', 'uddi:4ab07535-f2e7-4be5-a8e3-e3dba26de890')  # 공공데이터포털 파일데이터 (번호, 상세 키)


def download(raw=RAW):
    """공공데이터포털 파일데이터 다운로드 (페이지의 다운로드 버튼과 같은 요청, 인증키 없음)"""
    import requests
    s = requests.Session()
    s.headers['User-Agent'] = 'Mozilla/5.0 (emergency-policy-clustering-analysis)'
    info = s.post('https://www.data.go.kr/tcs/dss/selectFileDataDownload.do', timeout=60,
                  data={'publicDataPk': DATASET[0], 'publicDataDetailPk': DATASET[1], 'fileDetailSn': '1', 'publicDataHistSn': '1'}).json()
    r = s.get('https://www.data.go.kr/cmm/cmm/fileDownload.do', timeout=120,
              params={'atchFileId': info['atchFileId'], 'fileDetailSn': info['fileDetailSn'], 'insertDataPrcus': 'N'})
    r.raise_for_status()
    raw.mkdir(parents=True, exist_ok=True)
    out = raw / f"{info['dataSetFileDetailInfo']['dataNm']}.csv"
    out.write_bytes(r.content)
    print(f'-> {out} ({len(r.content) / 1e3:.0f}KB)')
    return out


def read_file(path, month=YM_LABEL):
    """기준월 행만, '서울특별시 종로구' -> 시도·시군구"""
    df = pd.read_csv(path, encoding='cp949', dtype={'통계연월': str})
    months = sorted(df['통계연월'].unique())
    if month not in months:
        raise SystemExit(f'{path.name} 에 기준월 {month} 이 없음 (있는 달: {months[0]}~{months[-1]})')
    df = df[df['통계연월'] == month]
    name = df['행정동명'].str.split(n=1)
    return pd.DataFrame({'시도': name.str[0], '시군구': name.str[1].fillna(''),
                         '65세이상인구': df['65세이상 인구수'].astype(int), '기초연금수급자수': df['수급자수'].astype(int)}), month


def build(raw=RAW, out=OUT, pop_csv=POP_CSV, mapping_file=ROOT / 'data' / 'region_mapping.csv'):
    files = sorted(Path(raw).glob('*.csv'))
    if not files:
        raise FileNotFoundError(f'{raw} 에 csv 가 없음 (python -m src.basic_pension --download)')
    df, month = read_file(files[-1])
    pop = pd.read_csv(pop_csv, dtype={'행정기관코드': str}).fillna({'시군구': ''})
    master = pop.rename(columns={'행정기관코드': 'code'})[['code', '시도', '시군구']].assign(unit=lambda m: m['code'])
    hit, miss = attach_code(df, master, load_mapping(mapping_file))
    gu = hit.loc[~hit['code'].isin(master['code']), ['시도', '시군구', 'unit']]  # 일반구 행이 있으면 상위 시로 합침

    units = master.set_index('code')[['시도', '시군구']]
    for c in ('65세이상인구', '기초연금수급자수'):
        units[c] = rollup(hit, c, 'sum', has_subtotals=True)
    units['기초연금수급률'] = units['기초연금수급자수'] / units['65세이상인구']
    units['기초연금수급률_순위'] = units['기초연금수급률'].rank(ascending=False, method='min').astype('Int64')  # 1위 = 가장 높음
    units['기준연월'] = month
    units.index.name = '행정기관코드'

    total, file_total = units['기초연금수급자수'].sum(), int(df['기초연금수급자수'].sum())
    lack = units[units['기초연금수급자수'].isna()]
    print(f'\n[basic_pension] {month} 시군구 {len(units)}곳 (값 있는 곳 {len(units) - len(lack)}곳), 수급자 {int(total):,}명 (파일 합계 {file_total:,})',
          '일치' if total == file_total else '불일치')
    print('일반구 -> 상위 시 합산: 없음 (파일이 시 단위)' if gu.empty else f'일반구 -> 상위 시 합산:\n{gu.to_string()}')
    print('매칭 실패(파일 -> 코드표): 없음' if miss.empty else f'매칭 실패(파일 -> 코드표):\n{miss.to_string()}')
    print('값 없는 시군구(코드표 -> 파일): 없음' if lack.empty else f'값 없는 시군구(코드표 -> 파일):\n{lack.to_string()}')
    out.parent.mkdir(parents=True, exist_ok=True)
    units.to_csv(out, encoding='utf-8-sig')
    print(f'-> {out}')
    return units, total == file_total and miss.empty and lack.empty


def compare(units, table=ROOT / 'data' / 'processed' / 'sigungu_table.csv', scores=ROOT / 'outputs' / 'sigungu_scores.csv',
            welfare=ROOT / 'data' / 'processed' / 'welfare_rate.csv'):
    """검증: 이중 취약 시군구의 기초연금 수급률 평균 vs 전체, 복지 취약 점수·고령·독거·기초생활수급자 비율과의 상관"""
    t = pd.read_csv(table, dtype={'code': str}).set_index('code')
    s = pd.read_csv(scores, dtype={'code': str}).set_index('code').fillna({'등급': ''})
    w = pd.read_csv(welfare, dtype={'행정기관코드': str}).set_index('행정기관코드')
    d = pd.DataFrame({'기초연금수급률': units['기초연금수급률'], '복지취약점수': s['복지취약점수'], '고령인구비율': t['65세이상인구'] / t['총인구'],
                      '독거노인비율': t['독거노인비율'], '기초생활수급자비율': w['수급자비율'], '등급': s['등급']})
    dv = d[d['등급'] == '이중 취약']
    res = {'이중취약_평균': dv['기초연금수급률'].mean(), '전체_평균': d['기초연금수급률'].mean(),
           '이중취약_중앙값': dv['기초연금수급률'].median(), '전체_중앙값': d['기초연금수급률'].median(),
           **{f'상관_{k}': d['기초연금수급률'].corr(d[k], method='spearman') for k in ('복지취약점수', '고령인구비율', '독거노인비율', '기초생활수급자비율')}}
    print(f"\n[검증] 이중 취약 {len(dv)}곳 기초연금 수급률 평균 {res['이중취약_평균']:.1%} (중앙값 {res['이중취약_중앙값']:.1%})"
          f" vs 전체 평균 {res['전체_평균']:.1%} (중앙값 {res['전체_중앙값']:.1%})")
    print('스피어만 상관: ' + ', '.join(f"{k} {res[f'상관_{k}']:.2f}" for k in ('복지취약점수', '고령인구비율', '독거노인비율', '기초생활수급자비율')))
    return res


if __name__ == '__main__':
    if '--download' in sys.argv:
        download()
    u, _ = build()
    compare(u)
