"""시군구별 응급의료 접근성 (자동차 주행시간 + 하버사인 직선거리)

실행: 레포 루트에서 python -m src.accessibility
입력: data/processed/emergency_facilities.csv (python -m src.fetch_emergency)
      data/processed/emd_centers.csv: 행정동 기준점(행정복지센터·읍면사무소)과 인구 (python -m src.emd_centers, --population)
      data/processed/drivetime_pairs.csv: 기준점 × 가까운 기관 주행시간 (python -m src.drivetime, 로컬 OSRM)
      data/processed/population_sigungu_202512.csv, data/region_mapping.csv
출력: data/processed/accessibility_sigungu.csv
      data/processed/facility_usage.csv: 시군구별 "주민이 가장 가깝게 이용하는 기관" 비율 (대시보드 지역 상세와 같은 집계, vitest 검증용)

기준점: 전국 행정동 약 3,557곳. 시군구 지표 = 행정동별 지표의 인구가중 평균
(예전의 시군구청 1곳 기준점과 섬 지역 예외는 이 방식으로 대체됨)

주행시간(분): 기준점마다 직선거리 가까운 응급의료기관 10곳 + 센터 10곳은 OSRM 실주행시간.
그 밖의 기관과 도로로 닿지 않는 쌍(연륙 안 된 섬 등)은 직선거리 × 시군구 우회계수(분/직선km)로 근사하고,
근사값은 도로로 잰 주행시간의 99백분위(APPROX_CAP_Q)를 넘지 않게 자른다(바다 건너 수백 분 같은 값이 점수·범례·K-means를 끌지 않게).
자르기 전 값은 *_원값 컬럼에 남긴다.
웹 시뮬레이터(web/src/sim/model.ts)도 같은 규칙이다.
"""
from pathlib import Path

import numpy as np
import pandas as pd

from .loaders import clean_sido_name
from .regions import attach_code, load_mapping

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / 'data' / 'processed'
FACILITIES = PROC / 'emergency_facilities.csv'
EMD_CENTERS = PROC / 'emd_centers.csv'
LI_POINTS = PROC / 'emd_li_points.csv'
LI_WEIGHTED = ROOT / 'data' / 'emd_li_weighted.csv'
POP_CSV = PROC / 'population_sigungu_202512.csv'
MAPPING = ROOT / 'data' / 'region_mapping.csv'
OUT = PROC / 'accessibility_sigungu.csv'
MOHW_CSV = ROOT / 'data' / 'raw' / 'emergency' / '보건복지부_응급의료기관 수_시도별_20241231.csv'

# dutyEmcls -> 등급. 보건복지부 2024 시도별 등급별 수와 비교해 확정 (전문응급의료센터 전용 코드는 없음)
GRADE = {'G001': '권역응급의료센터', 'G006': '지역응급의료센터', 'G007': '지역응급의료기관', 'G009': '응급실운영신고기관'}
EMERGENCY = ['G001', 'G006', 'G007']  # 응급의료법상 응급의료기관. G009(응급실운영신고기관)는 제외
CENTER = ['G001', 'G006']             # 권역·지역응급의료센터
RADIUS_KM = 30
MINUTES = 30                          # 주행시간 기준 기관 수: 30분 안
APPROX_CAP_Q = 99                     # 근사값 상한: 도로로 잰 주행시간(쌍)의 99백분위
DRIVE_PAIRS = PROC / 'drivetime_pairs.csv'
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


def load_centers(path=None):
    """행정동 기준점 -> 계산용 표 (행정기관코드=시군구, lat, lon, 가중치=인구)"""
    c = pd.read_csv(path or EMD_CENTERS, dtype={'코드': str, '시군구코드': str})
    if '인구' not in c:
        raise ValueError('emd_centers.csv 에 인구가 없음. 먼저 python -m src.emd_centers --population 실행')
    pts = pd.DataFrame({'행정기관코드': c['시군구코드'], '행정동코드': c['코드'], '기준점ID': c['코드'], '지점': c['이름'], 'lat': c['위도'], 'lon': c['경도'],
                        '가중치': c['인구'].astype(float), '가중방식': '행정동 인구가중'})
    # 섬으로 나뉜 읍·면(data/emd_li_weighted.csv)은 행정동 1점 대신 리(섬)별 좌표·인구로 나눈다 (src.emd_islands)
    if LI_WEIGHTED.exists() and LI_POINTS.exists():
        codes = set(pd.read_csv(LI_WEIGHTED, dtype={'행정동코드': str})['행정동코드'])
        li = pd.read_csv(LI_POINTS, dtype={'행정동코드': str})
        li = li[li['행정동코드'].isin(codes)]
        sgg = dict(zip(c['코드'], c['시군구코드']))
        pts = pd.concat([pts[~pts['행정동코드'].isin(set(li['행정동코드']))], pd.DataFrame({
            '행정기관코드': li['행정동코드'].map(sgg), '행정동코드': li['행정동코드'], '기준점ID': li['행정동코드'] + '-' + li['리'], '지점': li['리'], 'lat': li['위도'], 'lon': li['경도'],
            '가중치': li['인구'].astype(float), '가중방식': '행정동 인구가중(섬 읍·면은 리 단위)'})], ignore_index=True)
    return pts.drop(columns='행정동코드')


def drive_minutes(centers, em, d_em):
    """기준점 × 응급의료기관 주행시간(분) 행렬(근사값 상한 적용), 상한 전 행렬, 근사 여부 행렬, 시군구 우회계수(분/직선km), 상한(분)

    우회계수: 기준점마다 도로로 닿는 기관 중 직선거리 가장 가까운 곳(1km 이상)의 주행분/직선km, 시군구 중앙값.
    값이 없는 시군구는 전국 중앙값. 소수 3자리(출력 CSV 정밀도)로 반올림해 웹과 같은 값을 쓴다
    """
    pairs = pd.read_csv(DRIVE_PAIRS, dtype={'기준점ID': str, 'hpid': str}).dropna(subset=['주행시간초'])
    row = pd.Series(range(len(centers)), index=centers['기준점ID'])
    col = pd.Series(range(len(em)), index=em['hpid'].astype(str).to_numpy())
    pairs = pairs[pairs['hpid'].isin(col.index)]
    ri, ci = row[pairs['기준점ID']].to_numpy(), col[pairs['hpid']].to_numpy()

    near = pairs.assign(km=d_em[ri, ci], sgg=centers['행정기관코드'].to_numpy()[ri]).sort_values('km').drop_duplicates('기준점ID')
    near = near[near['km'] >= 1]
    ratio = (near['주행시간초'] / 60 / near['km']).groupby(near['sgg']).median()
    factor = ratio.reindex(centers['행정기관코드'].unique()).fillna(ratio.median()).round(3)

    real = pairs['주행시간초'].to_numpy() / 60
    cap = round(float(np.percentile(real, APPROX_CAP_Q)), 1)
    raw = d_em * factor[centers['행정기관코드']].to_numpy()[:, None]
    raw[ri, ci] = real
    approx = np.ones(raw.shape, bool)
    approx[ri, ci] = False
    t = np.where(approx, np.minimum(raw, cap), raw)
    return t, raw, approx, factor, cap


def facility_usage(centers, em, t, d_em, approx, ie, ic):
    """기준점마다 주행시간 최근접 기관(ie)·센터(ic)를 정하고, 시군구 인구 기준 기관별 이용 주민 비율을 집계한다.
    평균주행분·평균직선km 는 그 기관을 이용하는 주민 기준 가중평균. 근사포함: 근사값(도로 미연결·10곳 밖)인 기준점이 섞임
    """
    rows = np.arange(len(centers))
    w = centers['가중치'].to_numpy()
    out = []
    for kind, idx in [('응급의료기관', ie), ('권역지역센터', ic)]:
        u = pd.DataFrame({'행정기관코드': centers['행정기관코드'].to_numpy(), 'hpid': em['hpid'].astype(str).to_numpy()[idx],
                          'w': w, 'wm': w * t[rows, idx], 'wk': w * d_em[rows, idx], 'approx': approx[rows, idx]})
        g = u.groupby(['행정기관코드', 'hpid'])
        a = g[['w', 'wm', 'wk']].sum().join(g['approx'].any())
        total = u.groupby('행정기관코드')['w'].sum()
        a = a.assign(주민비율=a['w'] / total.reindex(a.index.get_level_values(0)).to_numpy(),
                     평균주행분=a['wm'] / a['w'], 평균직선km=a['wk'] / a['w'], 구분=kind).rename(columns={'approx': '근사포함'})
        out.append(a.reset_index())
    u = pd.concat(out).sort_values(['행정기관코드', '구분', '주민비율', '평균주행분'], ascending=[True, True, False, True])
    return u[['행정기관코드', '구분', 'hpid', '주민비율', '평균주행분', '평균직선km', '근사포함']]


def load_facilities():
    """기준 코드표(시군구 인구 표)와 시군구 코드가 붙은 기관 목록 (매칭 실패 목록 포함)"""
    pop = pd.read_csv(POP_CSV, dtype={'행정기관코드': str}).fillna({'시군구': ''})
    master = pop.rename(columns={'행정기관코드': 'code'})[['code', '시도', '시군구']].assign(unit=lambda m: m['code'])
    fac, miss = facilities_with_code(master, load_mapping(MAPPING))
    return pop, fac, miss


def build(out=OUT):
    pop, fac, miss = load_facilities()
    em, ctr = fac[fac['dutyEmcls'].isin(EMERGENCY)], fac[fac['dutyEmcls'].isin(CENTER)]

    centers = load_centers()
    d_em = haversine(centers['lat'], centers['lon'], em['wgs84Lat'], em['wgs84Lon'])
    d_ctr = haversine(centers['lat'], centers['lon'], ctr['wgs84Lat'], ctr['wgs84Lon'])
    centers['최근접_응급의료기관_km'] = d_em.min(axis=1)
    centers['최근접_권역지역센터_km'] = d_ctr.min(axis=1)
    centers[f'반경{RADIUS_KM}km_응급의료기관수'] = (d_em <= RADIUS_KM).sum(axis=1)
    t, raw, approx, factor, cap = drive_minutes(centers, em.reset_index(drop=True), d_em)
    is_ctr = em['dutyEmcls'].isin(CENTER).to_numpy()
    rows = np.arange(len(centers))
    # 최근접 기관: 주행시간 최소. 상한(cap)에 걸려 같은 값이 여럿이면 자르기 전 값(raw)이 작은 기관
    nearest = lambda tt, rr: np.where(tt == tt.min(axis=1, keepdims=True), rr, np.inf).argmin(axis=1)  # noqa: E731
    ie, ic = nearest(t, raw), np.flatnonzero(is_ctr)[nearest(t[:, is_ctr], raw[:, is_ctr])]
    centers['최근접_응급의료기관_분'] = t[rows, ie]
    centers['최근접_권역지역센터_분'] = t[rows, ic]
    centers[f'{MINUTES}분내_응급의료기관수'] = (t <= MINUTES).sum(axis=1)
    centers['최근접_응급의료기관_분_원값'] = raw.min(axis=1)
    centers['최근접_권역지역센터_분_원값'] = raw[:, is_ctr].min(axis=1)
    # 최근접 기관 또는 최근접 센터가 근사값(도로 미연결·10곳 밖)인 기준점의 인구 비율
    centers['근사반영_인구비율'] = (approx[rows, ie] | approx[rows, ic]).astype(float)

    metrics = ['최근접_응급의료기관_분', '최근접_권역지역센터_분', f'{MINUTES}분내_응급의료기관수',
               '최근접_응급의료기관_분_원값', '최근접_권역지역센터_분_원값', '근사반영_인구비율',
               '최근접_응급의료기관_km', '최근접_권역지역센터_km', f'반경{RADIUS_KM}km_응급의료기관수']
    wsum = centers.groupby('행정기관코드')['가중치'].sum()
    acc = centers[metrics].mul(centers['가중치'], axis=0).groupby(centers['행정기관코드']).sum().div(wsum, axis=0)
    # 섬 읍·면을 리 단위로 나눈 시군구는 그렇게 표시
    acc.insert(0, '기준점방식', centers.groupby('행정기관코드')['가중방식'].agg(lambda v: max(v, key=len)))
    acc['우회계수_분per직선km'] = factor
    acc['근사상한_분'] = cap

    table = pop.set_index('행정기관코드')[['시도', '시군구', '총인구']].join(acc)
    table['응급의료기관수'] = em['행정기관코드'].value_counts().reindex(table.index, fill_value=0)
    table['인구10만명당_응급의료기관수'] = table['응급의료기관수'] / table['총인구'] * 1e5
    table = table.drop(columns='총인구')

    report(fac, miss, centers, table)
    out.parent.mkdir(parents=True, exist_ok=True)
    table.round(3).to_csv(out, encoding='utf-8-sig')
    usage = facility_usage(centers, em, t, d_em, approx, ie, ic)
    usage.round(6).to_csv(out.parent / 'facility_usage.csv', index=False, encoding='utf-8-sig')
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

    cols = ['시도', '시군구', '최근접_응급의료기관_분', '최근접_권역지역센터_분', f'{MINUTES}분내_응급의료기관수',
            '최근접_권역지역센터_분_원값', '우회계수_분per직선km', '근사반영_인구비율']
    s = table.sort_values('최근접_응급의료기관_분', ascending=False)[cols].round(2)
    print(f'\n[최근접 응급의료기관 주행시간 상위 10]\n{s.head(10).to_string()}')
    print(f'\n[하위 10]\n{s.tail(10).to_string()}')


if __name__ == '__main__':
    build()
