"""보건복지부 응급안전안심서비스 이용자 -> 시군구 이용률·서비스 공백 (참고 지표)

이중 취약 판정·점수·등급에는 쓰지 않는다. 판정이 고른 지역에 서비스가 실제로 닿았는지 보는 데 쓴다.
이용률 = 65세 이상 이용자 / 65세 이상 1인세대 (이용 대상은 독거노인 외 노인 2인 가구·조손가구 등도 포함되므로 100%를 넘을 수 있는 근사 지표).
서비스 공백 = 이중 취약이면서 이용률이 이중 취약 시군구 중 하위 25%.

실행: 레포 루트에서 python -m src.emergency_safety [--download]
입력: data/raw/emergency_safety/*.csv (공공데이터포털 15128127 「보건복지부_응급안전안심 서비스 대상자 기본정보」,
      cp949, 이용자 1명 1행: 시도·시군구·성별·나이, 기준 2024-05-20, 이용허락범위 제한 없음)
      data/processed/population_sigungu_{기준연월}.csv (기준 코드표), sigungu_table.csv (65세이상1인세대수), outputs/sigungu_scores.csv (등급)
출력: data/processed/emergency_safety_rate.csv
한계: 서울은 원본에 7개 구만 있고 이용자 수도 매우 적어(자체 체계 운영 등으로 보임, 미확인) 서울 전체를 '자료 없음'으로 둔다.
      인천 중구·강화군·옹진군도 원본에 없다. 이용자 기준일(2024-05)과 1인세대 기준일(2025-12)이 다르다.
"""
import sys
from pathlib import Path

import pandas as pd

from .config import YM
from .regions import attach_code, load_mapping

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data' / 'raw' / 'emergency_safety'
OUT = ROOT / 'data' / 'processed' / 'emergency_safety_rate.csv'
POP_CSV = ROOT / 'data' / 'processed' / f'population_sigungu_{YM}.csv'
DATASET = ('15128127', 'uddi:20fcd1d4-1718-4aa4-a5ec-a688f3844f63')  # 공공데이터포털 파일데이터 (번호, 상세 키)
BASE_DATE = '2024-05-20'
NO_DATA_SIDO = ('서울특별시',)  # 원본이 일부 구만 담고 있어 시도 전체를 자료 없음으로


def download(raw=RAW):
    """공공데이터포털 파일데이터 다운로드 (페이지의 다운로드 버튼과 같은 요청, 인증키 없음)"""
    import requests
    s = requests.Session()
    s.headers['User-Agent'] = 'Mozilla/5.0 (emergency-policy-clustering-analysis)'
    info = s.post('https://www.data.go.kr/tcs/dss/selectFileDataDownload.do', timeout=60,
                  data={'publicDataPk': DATASET[0], 'publicDataDetailPk': DATASET[1], 'fileDetailSn': '1', 'publicDataHistSn': '1'}).json()
    r = s.get('https://www.data.go.kr/cmm/cmm/fileDownload.do', timeout=300,
              params={'atchFileId': info['atchFileId'], 'fileDetailSn': info['fileDetailSn'], 'insertDataPrcus': 'N'})
    r.raise_for_status()
    raw.mkdir(parents=True, exist_ok=True)
    out = raw / 'emergency_safety_users.csv'
    out.write_bytes(r.content)
    print(f'-> {out} ({len(r.content) / 1e6:.1f}MB)')
    return out


def count_users(df):
    """이용자 1명 1행 -> 시도·시군구별 이용자 수, 65세 이상 이용자 수 (나이 결측은 노인 집계에서 뺌)"""
    age = pd.to_numeric(df['나이'].str.extract(r'^(\d+)')[0], errors='coerce')
    return (df.assign(노인=age >= 65).groupby(['시도', '시군구'])
              .agg(이용자=('시도', 'size'), 노인이용자=('노인', 'sum')).reset_index())


def gaps(units):
    """서비스 공백: 이중 취약이면서 이용률이 (자료 있는) 이중 취약 시군구 중 하위 25%"""
    dv = units[(units['등급'] == '이중 취약') & units['이용률'].notna()]
    cut = dv['이용률'].quantile(0.25)
    return (units['등급'] == '이중 취약') & (units['이용률'] <= cut), cut


def build(raw=RAW, out=OUT, pop_csv=POP_CSV, table=ROOT / 'data' / 'processed' / 'sigungu_table.csv',
          scores=ROOT / 'outputs' / 'sigungu_scores.csv', mapping_file=ROOT / 'data' / 'region_mapping.csv'):
    files = sorted(Path(raw).glob('*.csv'))
    if not files:
        raise FileNotFoundError(f'{raw} 에 csv 가 없음 (python -m src.emergency_safety --download)')
    df = pd.read_csv(files[-1], encoding='cp949')
    g = count_users(df)
    pop = pd.read_csv(pop_csv, dtype={'행정기관코드': str}).fillna({'시군구': ''})
    master = pop.rename(columns={'행정기관코드': 'code'})[['code', '시도', '시군구']].assign(unit=lambda m: m['code'])
    hit, miss = attach_code(g, master, load_mapping(mapping_file))
    hit = hit[~hit['시도'].isin(NO_DATA_SIDO)]

    units = master.set_index('code')[['시도', '시군구']]
    agg = hit.groupby('unit')[['이용자', '노인이용자']].sum()  # 일반구는 attach_code 가 상위 시(unit)로
    units = units.join(agg)
    t = pd.read_csv(table, dtype={'code': str}).set_index('code')
    s = pd.read_csv(scores, dtype={'code': str}).set_index('code').fillna({'등급': ''})
    units['65세이상1인세대수'] = t['65세이상1인세대수']
    units['등급'] = s['등급']
    units['이용률'] = units['노인이용자'] / units['65세이상1인세대수']
    units['이용률_순위'] = units['이용률'].rank(ascending=True, method='min').astype('Int64')  # 1위 = 가장 낮음(공백에 가까움)
    units['서비스공백'], cut = gaps(units)
    units['기준일'] = BASE_DATE
    units.index.name = '행정기관코드'

    lack = units[units['이용자'].isna()]
    n_file = len(df) - int(df['시도'].isin(NO_DATA_SIDO).sum())
    print(f'\n[emergency_safety] 기준 {BASE_DATE}, 이용자 {len(df):,}명 (서울 제외 {n_file:,}명, 집계 {int(units["이용자"].sum()):,}명)',
          '일치' if int(units['이용자'].sum()) == n_file else '불일치')
    print('매칭 실패(파일 -> 코드표): 없음' if miss.empty else f'매칭 실패(파일 -> 코드표):\n{miss.to_string()}')
    print(f'자료 없음 {len(lack)}곳: ' + ', '.join(f'{r.시도} {r.시군구}' for r in lack.itertuples()))
    print(f'서비스 공백 기준: 이중 취약 이용률 하위 25% = {cut:.1%} 이하 -> {int(units["서비스공백"].sum())}곳')
    out.parent.mkdir(parents=True, exist_ok=True)
    units.drop(columns=['등급']).to_csv(out, encoding='utf-8-sig')
    print(f'-> {out}')
    return units, int(units['이용자'].sum()) == n_file and miss.empty


def compare(units, scores=ROOT / 'outputs' / 'sigungu_scores.csv'):
    """검증: 등급별 합산 이용률, 복지·접근성 취약 점수와의 상관, 서비스 공백 목록"""
    s = pd.read_csv(scores, dtype={'code': str}).set_index('code')
    d = units[units['이용률'].notna()].join(s[['복지취약점수', '접근성취약점수']])
    by = d.groupby(d['등급'].replace('', '해당 없음'))[['노인이용자', '65세이상1인세대수']].sum()
    res = (by['노인이용자'] / by['65세이상1인세대수']).to_dict()
    print('\n[검증] 등급별 합산 이용률(65세 이상 이용자 / 65세 이상 1인세대): ' + ', '.join(f'{k} {v:.1%}' for k, v in res.items()))
    for k in ('복지취약점수', '접근성취약점수'):
        print(f'스피어만 상관 이용률 vs {k}: {d["이용률"].corr(d[k], method="spearman"):.2f}')
    gap = units[units['서비스공백']].sort_values('이용률')
    print('서비스 공백: ' + ', '.join(f'{r.시도} {r.시군구} {r.이용률:.1%}' for r in gap.itertuples()))
    return res


if __name__ == '__main__':
    if '--download' in sys.argv:
        download()
    u, _ = build()
    compare(u)
