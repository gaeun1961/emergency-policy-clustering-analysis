"""시군구별 응급의료 접근성 (하버사인 직선거리)

실행: 레포 루트에서 python -m src.accessibility
입력: data/processed/emergency_facilities.csv (python -m src.fetch_emergency)
      data/processed/sigungu_centers.csv (python -m src.geocode)
      data/processed/population_sigungu_202512.csv, data/region_mapping.csv
      (선택) data/raw/eupmyeondong/*.xlsx: 행안부 연령별 인구현황 읍면동 단위. 여러 지점 기준점(옹진군)의 인구 가중치
출력: data/processed/accessibility_sigungu.csv
"""
from pathlib import Path

import numpy as np
import pandas as pd

from . import population
from .loaders import clean_sido_name
from .regions import attach_code, load_mapping

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / 'data' / 'processed'
FACILITIES = PROC / 'emergency_facilities.csv'
CENTERS = PROC / 'sigungu_centers.csv'
POP_CSV = PROC / 'population_sigungu_202512.csv'
EMD_RAW = ROOT / 'data' / 'raw' / 'eupmyeondong'
MAPPING = ROOT / 'data' / 'region_mapping.csv'
OUT = PROC / 'accessibility_sigungu.csv'
MOHW_CSV = ROOT / 'data' / 'raw' / 'emergency' / '보건복지부_응급의료기관 수_시도별_20241231.csv'

# dutyEmcls -> 등급. 보건복지부 2024 시도별 등급별 수와 비교해 확정 (전문응급의료센터 전용 코드는 없음)
GRADE = {'G001': '권역응급의료센터', 'G006': '지역응급의료센터', 'G007': '지역응급의료기관', 'G009': '응급실운영신고기관'}
EMERGENCY = ['G001', 'G006', 'G007']  # 응급의료법상 응급의료기관. G009(응급실운영신고기관)는 제외
CENTER = ['G001', 'G006']             # 권역·지역응급의료센터
RADIUS_KM = 30
KOREA = dict(lat=(33.0, 38.7), lon=(124.5, 132.0))  # 독도(131.9)까지 포함하는 대략 범위


def haversine(lat1, lon1, lat2, lon2):
    """(n,) x (m,) -> (n, m) km"""
    lat1, lon1, lat2, lon2 = (np.radians(np.asarray(a, float)) for a in (lat1, lon1, lat2, lon2))
    dlat = lat2[None, :] - lat1[:, None]
    dlon = lon2[None, :] - lon1[:, None]
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1)[:, None] * np.cos(lat2)[None, :] * np.sin(dlon / 2) ** 2
    return 2 * 6371.0088 * np.arcsin(np.sqrt(a))


def facilities_with_code(master, mapping):
    """dutyAddr '경기도 수원시 팔달구 …' -> 시도/시군구 -> 기준 코드표. 일반구는 상위 시로"""
    f = pd.read_csv(FACILITIES)
    parts = f['dutyAddr'].str.split()
    f['시도'], f['시군구'] = parts.str[0], parts.str[1]
    hit, miss = attach_code(f, master, mapping)
    return hit.rename(columns={'unit': '행정기관코드'}), miss


def point_weights(centers):
    """여러 지점 기준점(weighted)의 가중치. 읍면동 인구 파일이 있으면 인구, 없으면 1(단순평균)"""
    centers = centers.assign(가중치=1.0, 가중방식=centers['방식'])
    multi = centers['방식'] == 'weighted'
    if not multi.any():
        return centers
    files = sorted(EMD_RAW.glob('*.xlsx'))
    if not files:
        print(f'[임시] {EMD_RAW} 에 읍면동 인구 파일 없음 -> {centers.loc[multi, "시군구"].unique().tolist()} 단순평균')
        centers.loc[multi, '가중방식'] = 'weighted(단순평균_임시)'
        return centers
    emd = pd.concat([population.read_file(p) for p in files])
    names = emd['행정기관'].str.split()  # '인천광역시 옹진군 북도면' -> (옹진군, 북도면). 다른 군의 같은 이름 읍면과 섞이지 않게
    # '북도면장봉출장소' 같은 출장소는 별도 행이고 면 인구에 안 들어 있음 -> 소속 읍면에 더한다
    emd_name = names.str[-1].str.extract(r'^(.+?[읍면])(?:\S*출장소)?$')[0]
    emd_pop = population.to_num(emd['총인구수']).groupby([names.str[-2], emd_name]).sum().to_dict()
    m = centers[multi]
    w = pd.Series([emd_pop.get((g, p.removesuffix('사무소'))) for g, p in zip(m['시군구'], m['지점'])], index=m.index, dtype=float)
    if w.isna().any():
        print(f'[경고] 읍면동 인구 없는 지점 -> 단순평균: {centers.loc[multi][w.isna()]["지점"].tolist()}')
        centers.loc[multi, '가중방식'] = 'weighted(단순평균_임시)'
        return centers
    centers.loc[multi, '가중치'] = w
    centers.loc[multi, '가중방식'] = 'weighted(인구가중)'
    return centers


def build(out=OUT):
    pop = pd.read_csv(POP_CSV, dtype={'행정기관코드': str}).fillna({'시군구': ''})
    master = pop.rename(columns={'행정기관코드': 'code'})[['code', '시도', '시군구']].assign(unit=lambda m: m['code'])
    fac, miss = facilities_with_code(master, load_mapping(MAPPING))
    em, ctr = fac[fac['dutyEmcls'].isin(EMERGENCY)], fac[fac['dutyEmcls'].isin(CENTER)]

    centers = point_weights(pd.read_csv(CENTERS, dtype={'행정기관코드': str}))
    d_em = haversine(centers['lat'], centers['lon'], em['wgs84Lat'], em['wgs84Lon'])
    d_ctr = haversine(centers['lat'], centers['lon'], ctr['wgs84Lat'], ctr['wgs84Lon'])
    centers['최근접_응급의료기관_km'] = d_em.min(axis=1)
    centers['최근접_권역지역센터_km'] = d_ctr.min(axis=1)
    centers[f'반경{RADIUS_KM}km_응급의료기관수'] = (d_em <= RADIUS_KM).sum(axis=1)

    metrics = ['최근접_응급의료기관_km', '최근접_권역지역센터_km', f'반경{RADIUS_KM}km_응급의료기관수']
    wsum = centers.groupby('행정기관코드')['가중치'].sum()
    acc = centers[metrics].mul(centers['가중치'], axis=0).groupby(centers['행정기관코드']).sum().div(wsum, axis=0)
    acc.insert(0, '기준점방식', centers.groupby('행정기관코드')['가중방식'].first())

    table = pop.set_index('행정기관코드')[['시도', '시군구', '총인구']].join(acc)
    table['응급의료기관수'] = em['행정기관코드'].value_counts().reindex(table.index, fill_value=0)
    table['인구10만명당_응급의료기관수'] = table['응급의료기관수'] / table['총인구'] * 1e5
    table = table.drop(columns='총인구')

    report(fac, miss, centers, table)
    out.parent.mkdir(parents=True, exist_ok=True)
    table.round(3).to_csv(out, encoding='utf-8-sig')
    print(f'\n-> {out}')
    return table


def report(fac, miss, centers, table):
    print(f'[수집] 기관 {len(fac) + len(miss)}개, 수집일자 {fac["수집일자"].iloc[0]}')
    print(pd.Series(GRADE).to_frame('등급').join(fac['dutyEmcls'].value_counts().rename('개수')).to_string())
    print('\n[기관 -> 시군구 매칭] 실패 없음' if miss.empty else f'\n[기관 -> 시군구 매칭] 실패 {len(miss)}개:\n'
          f'{miss[["dutyName", "dutyAddr"]].to_string()}')

    # 보건복지부 2024 시도별 등급별 수와 비교 (기준 시점 차이 있음)
    fac = fac.assign(시도=fac['행정기관코드'].map(dict(zip(table.index, table['시도']))))
    api = fac.pivot_table(index='시도', columns='dutyEmcls', values='hpid', aggfunc='size', fill_value=0)
    if MOHW_CSV.exists():
        m = pd.read_csv(MOHW_CSV, encoding='cp949')
        m = m[m['연도'] == 2024].assign(시도=lambda d: d['시도'].str.split().str[0].map(clean_sido_name)).set_index('시도')
        cmp = pd.DataFrame({
            'API_G001': api['G001'], '복지부_권역': m['권역응급의료센터'],
            'API_G006': api['G006'], '복지부_지역센터': m['지역응급의료센터'],
            'API_G007': api['G007'], '복지부_지역기관': m['지역응급의료기관'], '복지부_전문': m['전문응급의료센터'],
            'API_응급의료기관': api[EMERGENCY].sum(axis=1), '복지부_합계': m.iloc[:, 1:].sum(axis=1)})
        cmp['차이'] = cmp['API_응급의료기관'] - cmp['복지부_합계']
        cmp.loc['합계'] = cmp.sum()
        print(f'\n[보건복지부 2024 비교] (복지부_합계 = 권역+전문+지역센터+지역기관)\n{cmp.to_string()}')

    print(f'\n[legacy 비교] legacy 2025.4: 응급의료기관 414 + 응급의료시설 113 = 527 / '
          f'API: 응급의료기관 {fac["dutyEmcls"].isin(EMERGENCY).sum()} + 응급실운영신고기관 {(fac["dutyEmcls"] == "G009").sum()} = {len(fac)}')

    for name, lat, lon in [('기관', fac['wgs84Lat'], fac['wgs84Lon']), ('기준점', centers['lat'], centers['lon'])]:
        out = ~(lat.between(*KOREA['lat']) & lon.between(*KOREA['lon']))
        print(f'[좌표 범위] {name} {len(lat)}개 중 한국 범위 밖 {out.sum()}개')

    cols = ['시도', '시군구', '기준점방식', '최근접_응급의료기관_km', '최근접_권역지역센터_km', f'반경{RADIUS_KM}km_응급의료기관수']
    s = table.sort_values('최근접_응급의료기관_km', ascending=False)[cols].round(1)
    print(f'\n[최근접 응급의료기관 거리 상위 10]\n{s.head(10).to_string()}')
    print(f'\n[하위 10]\n{s.tail(10).to_string()}')


if __name__ == '__main__':
    build()
