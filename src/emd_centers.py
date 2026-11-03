"""행정동 기준점: 행정복지센터·읍면사무소 좌표 (카카오 로컬 키워드 검색)

실행: 레포 루트에서 python -m src.emd_centers
필요: .env 의 KAKAO_REST_API_KEY, node(npx) (mapshaper로 행정동 내부 대표점 계산)
입력: data/raw/boundary/HangJeongDong_ver20251231.geojson (scripts/build_boundaries.py 가 받음)
      data/processed/population_sigungu_202512.csv (기준 코드표, 일반구 -> 상위 시)
출력: data/processed/emd_centers.csv (캐시: 이미 받은 행정동은 다시 호출하지 않음)
      컬럼: 코드(행정동 10자리), 시군구코드, 이름, 위도, 경도, 좌표출처(kakao / inner), 장소명
      인구 컬럼은 src.emd_population 이 붙인다
"""
import csv
import re
import json
import math
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import requests
from dotenv import load_dotenv

from .loaders import clean_sido_name
from .regions import parent_city

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data' / 'raw' / 'boundary' / 'HangJeongDong_ver20251231.geojson'
POP_CSV = ROOT / 'data' / 'processed' / 'population_sigungu_202512.csv'
OUT = ROOT / 'data' / 'processed' / 'emd_centers.csv'
OVERRIDES = ROOT / 'data' / 'emd_center_overrides.csv'
KEYWORD_URL = 'https://dapi.kakao.com/v2/local/search/keyword.json'
MAPSHAPER = 'mapshaper@0.7.101'
COLS = ['코드', '시군구코드', '이름', '위도', '경도', '좌표출처', '장소명']


def unit_codes():
    """행정동 adm_cd2 앞 5자리 -> 기준 코드표 시군구 코드 (일반구는 상위 시)"""
    with open(POP_CSV, encoding='utf-8-sig') as f:
        units = {r['행정기관코드']: (r['시도'], r['시군구']) for r in csv.DictReader(f)}
    by_name = {v: k for k, v in units.items()}

    def code(p):
        c = p['adm_cd2'][:5]
        if c in units:
            return c
        return by_name.get(parent_city((clean_sido_name(p['sidonm']), p['sggnm'].replace(' ', ''))))
    return code


def in_polygon(lon, lat, geom):
    """점이 (Multi)Polygon 안인지: 짝홀 규칙 광선 투사. 구멍은 짝홀로 자연히 처리"""
    polys = geom['coordinates'] if geom['type'] == 'MultiPolygon' else [geom['coordinates']]
    inside = False
    for poly in polys:
        for ring in poly:
            for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
                if (y1 > lat) != (y2 > lat) and lon < (x2 - x1) * (lat - y1) / (y2 - y1) + x1:
                    inside = not inside
    return inside


def inner_points(features):
    """mapshaper -points inner: 폴리곤 내부에 반드시 들어가는 대표점 (pointOnSurface에 해당)"""
    with tempfile.TemporaryDirectory() as d:
        src, out = Path(d) / 'dong.geojson', Path(d) / 'inner.geojson'
        slim = [{'type': 'Feature', 'properties': {'code': f['properties']['adm_cd2']}, 'geometry': f['geometry']} for f in features]
        src.write_text(json.dumps({'type': 'FeatureCollection', 'features': slim}), encoding='utf-8')
        subprocess.run(['npx', '-y', MAPSHAPER, str(src), '-points', 'inner', '-o', str(out), 'format=geojson'],
                       check=True, shell=sys.platform == 'win32', capture_output=True)
        pts = json.loads(out.read_text(encoding='utf-8'))['features']
    return {p['properties']['code']: p['geometry']['coordinates'] for p in pts}


def norm(name):
    """'종로1·2·3·4가동' 과 '종로1.2.3.4가동주민센터' 를 같은 이름으로 비교"""
    return re.sub(r'[·.,\s]', '', name)


def search(key, props, geom):
    """'경상북도 영덕군 영덕읍 행정복지센터' 등으로 검색해, 이름에 동명이 들어가고 행정동 경계 안인 지방행정기관"""
    dong = props['adm_nm'].split()[-1]
    region = ' '.join(props['adm_nm'].split()[:-1])
    for suffix in ('행정복지센터', '주민센터', '사무소'):
        r = requests.get(KEYWORD_URL, params={'query': f'{region} {dong} {suffix}', 'size': 15},
                         headers={'Authorization': f'KakaoAK {key}'}, timeout=10)
        r.raise_for_status()
        for d in r.json()['documents']:
            if '지방행정기관' not in d['category_name'] or norm(dong) not in norm(d['place_name']):
                continue
            lon, lat = float(d['x']), float(d['y'])
            if in_polygon(lon, lat, geom):
                return lat, lon, d['place_name']
    return None


def main():
    load_dotenv(ROOT / '.env')
    key = os.getenv('KAKAO_REST_API_KEY')
    if not key:
        sys.exit('.env 에 KAKAO_REST_API_KEY 가 없음')
    if not RAW.exists():
        sys.exit(f'{RAW} 가 없음. 먼저 python scripts/build_boundaries.py 실행')
    features = json.loads(RAW.read_text(encoding='utf-8'))['features']
    unit = unit_codes()

    cache = {}
    if OUT.exists():
        with open(OUT, encoding='utf-8-sig') as f:
            cache = {r['코드']: r for r in csv.DictReader(f) if r['좌표출처'] != 'inner'}  # inner 대체분은 다시 시도
    todo = [f for f in features if f['properties']['adm_cd2'] not in cache]
    print(f'행정동 {len(features)}개 중 캐시 {len(features) - len(todo)}개, 새로 검색 {len(todo)}개')

    inner = inner_points(features)
    rows, fallback = [], []
    for i, f in enumerate(features):
        p = f['properties']
        if p['adm_cd2'] in cache:
            rows.append({k: cache[p['adm_cd2']][k] for k in COLS})
            continue
        hit = search(key, p, f['geometry'])
        base = {'코드': p['adm_cd2'], '시군구코드': unit(p), '이름': p['adm_nm']}
        if hit:
            rows.append({**base, '위도': hit[0], '경도': hit[1], '좌표출처': 'kakao', '장소명': hit[2]})
        else:
            lon, lat = inner[p['adm_cd2']]
            rows.append({**base, '위도': lat, '경도': lon, '좌표출처': 'inner', '장소명': ''})
            fallback.append(p['adm_nm'])
        if (i + 1) % 200 == 0:
            print(f'  {i + 1}/{len(features)}', flush=True)

    rows.sort(key=lambda r: r['코드'])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        w.writerows(rows)

    n_inner = sum(r['좌표출처'] == 'inner' for r in rows)
    print(f'\n{len(rows)}개 -> {OUT}')
    print(f'카카오 {len(rows) - n_inner}개, 내부 대표점 대체 {n_inner}개 (이번 실행에서 새로 대체 {len(fallback)}개)')
    if fallback:
        print('대체 목록:', ', '.join(fallback))
    missing = [r['이름'] for r in rows if not r['시군구코드']]
    print('시군구 코드 매칭 실패:', missing or '없음')
    refine_eupmyeon()   # 읍·면 대체분 2차 검색 (near)
    apply_overrides()   # 이름이 바뀐 청사 예외 (override)


NEAR_KM = 3  # 읍·면 2차 검색: 경계에서 이 거리 안이면 채택


def km_to_polygon(lon, lat, geom):
    """점에서 (Multi)Polygon까지 거리(km). 안이면 0. 짧은 거리라 위도 보정 평면 근사"""
    if in_polygon(lon, lat, geom):
        return 0.0
    kx, ky = 111.32 * math.cos(math.radians(lat)), 110.57
    best = math.inf
    polys = geom['coordinates'] if geom['type'] == 'MultiPolygon' else [geom['coordinates']]
    for poly in polys:
        for ring in poly:
            for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
                ax, ay, bx, by = (x1 - lon) * kx, (y1 - lat) * ky, (x2 - lon) * kx, (y2 - lat) * ky
                dx, dy = bx - ax, by - ay
                t = max(0.0, min(1.0, -(ax * dx + ay * dy) / (dx * dx + dy * dy or 1)))
                best = min(best, math.hypot(ax + t * dx, ay + t * dy))
    return best


def refine_eupmyeon():
    """1차에서 내부 대표점으로 대체된 읍·면만 2차 검색.
    '{읍면}사무소', '{읍면} 행정복지센터' (시군구명 없이)로 찾아 이름이 정확히 같고 그 읍면 경계에서 NEAR_KM 이내면 채택(좌표출처 near).
    청사가 경계 바로 밖에 있는 경우를 살린다. 못 찾으면 내부 대표점 유지. 동 지역은 대상 아님"""
    import pandas as pd
    load_dotenv(ROOT / '.env')
    key = os.getenv('KAKAO_REST_API_KEY')
    c = pd.read_csv(OUT, dtype={'코드': str, '시군구코드': str})
    geom = {f['properties']['adm_cd2']: f['geometry'] for f in json.loads(RAW.read_text(encoding='utf-8'))['features']}
    target = c[(c['좌표출처'] == 'inner') & c['이름'].str.split().str[-1].str.endswith(('읍', '면'))]
    print(f'[읍·면 2차 검색] 대상 {len(target)}곳')
    for i, r in target.iterrows():
        emd = r['이름'].split()[-1]
        names = {norm(emd + '사무소'), norm(emd + '행정복지센터')}
        best = None
        for q in (f'{emd}사무소', f'{emd} 행정복지센터'):
            res = requests.get(KEYWORD_URL, params={'query': q, 'size': 15}, headers={'Authorization': f'KakaoAK {key}'}, timeout=10)
            res.raise_for_status()
            for d in res.json()['documents']:
                if norm(d['place_name']) not in names:
                    continue
                lon, lat = float(d['x']), float(d['y'])
                km = km_to_polygon(lon, lat, geom[r['코드']])
                if km <= NEAR_KM and (best is None or km < best[0]):
                    best = (km, lat, lon, d['place_name'], d['address_name'])
        if best:
            c.loc[i, ['위도', '경도', '좌표출처', '장소명']] = [best[1], best[2], 'near', best[3]]
            print(f'  채택 {r["이름"]}: {best[3]} ({best[4]}), 경계에서 {best[0]:.2f}km')
        else:
            print(f'  유지(내부 대표점) {r["이름"]}')
    c.to_csv(OUT, index=False, encoding='utf-8-sig')
    print(c['좌표출처'].value_counts().to_string())
    return c


def apply_overrides():
    """예외 목록(data/emd_center_overrides.csv)의 행정동은 지정한 카카오 장소로 기준점을 정한다 (좌표출처 override).
    일반 규칙(이름에 동명 포함)으로 못 잡는 이름 변경(면→읍 승격, 통합 청사 등)만 여기에 둔다.
    지정한 장소가 그 행정동 경계 안일 때만 채택"""
    import pandas as pd
    load_dotenv(ROOT / '.env')
    key = os.getenv('KAKAO_REST_API_KEY')
    c = pd.read_csv(OUT, dtype={'코드': str, '시군구코드': str})
    ov = pd.read_csv(OVERRIDES, dtype={'행정동코드': str})
    geom = {f['properties']['adm_cd2']: f['geometry'] for f in json.loads(RAW.read_text(encoding='utf-8'))['features']}
    for r in ov.itertuples():
        row = c.index[c['코드'] == r.행정동코드]
        region = ' '.join(c.loc[row[0], '이름'].split()[:-1])
        docs = requests.get(KEYWORD_URL, params={'query': f'{region} {r.카카오장소명}', 'size': 15},
                            headers={'Authorization': f'KakaoAK {key}'}, timeout=10).json()['documents']
        hit = next((d for d in docs if norm(d['place_name']) == norm(r.카카오장소명)
                    and in_polygon(float(d['x']), float(d['y']), geom[r.행정동코드])), None)
        if hit:
            c.loc[row, ['위도', '경도', '좌표출처', '장소명']] = [float(hit['y']), float(hit['x']), 'override', hit['place_name']]
            print(f'  예외 적용 {c.loc[row[0], "이름"]}: {hit["place_name"]} ({hit["address_name"]})')
        else:
            print(f'  [경고] 예외 장소를 경계 안에서 못 찾음: {r.행정동코드} {r.카카오장소명}')
    c.to_csv(OUT, index=False, encoding='utf-8-sig')
    return c


def attach_population(ym='202512'):
    """emd_centers.csv 에 행정동 인구(src.fetch_emd_population 결과)를 붙이고 검증한다.
    - 행정동 코드(10자리) = 경계 adm_cd2 로 바로 매칭
    - 경계가 없는 출장소는 소속 행정동에 더한다. 순서대로
      1) 이름 앞부분이 같은 읍면 (북도면장봉출장소 -> 북도면, 기존 규칙과 같음)
      2) 같은 법정 읍면동의 주 행정동 (원산출장소 -> 오천면, 삼랑진임천출장소 -> 삼랑진읍)
      3) 법정동 주소의 카카오 좌표가 들어 있는 행정동 (신수출장소: 법정 신수동에 출장소뿐)
    - 시군구별 합이 population_sigungu_{ym}.csv 총인구와 같은지 확인
    """
    import pandas as pd
    from collections import Counter
    c = pd.read_csv(OUT, dtype={'코드': str, '시군구코드': str})
    p = pd.read_csv(ROOT / 'data' / 'processed' / f'emd_population_{ym}.csv', dtype={'행정동코드': str})
    name = dict(zip(c['코드'], c['이름'].str.split().str[-1]))
    cache = ROOT / 'data' / 'raw' / 'emd_population' / ym
    geom = None

    def rows_of(code):
        return [x for f in cache.glob(f'{code[:5]}*.json') for x in json.loads(f.read_text(encoding='utf-8')) if x['admmCd'] == code]

    def target(code, dong):
        nonlocal geom
        if code in name:
            return code
        if not dong.endswith('출장소'):
            return None
        hit = next((k for k, v in name.items() if k[:5] == code[:5] and dong.startswith(v)), None)
        if hit:
            return hit
        rows = rows_of(code)
        for s8 in {x['stdgCd'][:8] for x in rows}:
            main = Counter(x['admmCd'] for x in json.loads((cache / f'{s8}00.json').read_text(encoding='utf-8')) if x['admmCd'] in name)
            if main:
                return main.most_common(1)[0][0]
        if rows:  # 법정동 주소 좌표가 들어 있는 행정동
            load_dotenv(ROOT / '.env')
            x = rows[0]
            q = ' '.join(v for v in (x.get('ctpvNm'), x.get('sggNm'), x.get('stdgNm'), x.get('liNm')) if v)
            docs = requests.get('https://dapi.kakao.com/v2/local/search/address.json', params={'query': q},
                                headers={'Authorization': f'KakaoAK {os.getenv("KAKAO_REST_API_KEY")}'}, timeout=10).json()['documents']
            if docs:
                geom = geom or {f['properties']['adm_cd2']: f['geometry'] for f in json.loads(RAW.read_text(encoding='utf-8'))['features']}
                lon, lat = float(docs[0]['x']), float(docs[0]['y'])
                return next((k for k in name if k[:5] == code[:5] and in_polygon(lon, lat, geom[k])), None)
        return None
    p['매칭코드'] = [target(k, d) for k, d in zip(p['행정동코드'], p['행정동명'])]
    miss = p[p['매칭코드'].isna()]
    branch = p[p['매칭코드'].notna() & (p['매칭코드'] != p['행정동코드'])]
    c['인구'] = c['코드'].map(p.groupby('매칭코드')['총인구'].sum()).fillna(0).astype(int)
    no_pop = c[c['인구'] == 0]

    sgg = pd.read_csv(POP_CSV, dtype={'행정기관코드': str}).set_index('행정기관코드')['총인구']
    got = c.groupby('시군구코드')['인구'].sum()
    diff = (got - sgg).dropna()
    bad = diff[diff != 0]

    print(f'[인구 매칭] 행정동 인구 {len(p)}행 -> 경계 행정동 {len(c)}개')
    print(f'  출장소 -> 소속 읍면 합산 {len(branch)}곳: ' + ', '.join(f'{d}->{name[t]}' for d, t in zip(branch['행정동명'], branch['매칭코드'])))
    print('  매칭 실패(경계 없음):', miss[['행정동코드', '행정동명', '총인구']].values.tolist() or '없음')
    print('  인구 0인 경계 행정동:', no_pop['이름'].tolist() or '없음')
    print(f'  시군구별 합 vs 기준 코드표: {len(got)}개 중 불일치 {len(bad)}개', bad.to_dict() if len(bad) else '')
    print(f'  전국 합 {int(c["인구"].sum()):,} / 기준 {int(sgg.sum()):,}')
    c.to_csv(OUT, index=False, encoding='utf-8-sig')
    # 출장소 -> 소속 행정동 대응을 남겨 리 단위(src.emd_islands)에서도 같은 규칙으로 쓴다
    p.rename(columns={'매칭코드': '소속행정동코드'}).to_csv(ROOT / 'data' / 'processed' / f'emd_population_{ym}.csv', index=False, encoding='utf-8-sig')
    return c


if __name__ == '__main__':
    if sys.argv[1:2] == ['--population']:
        attach_population(*sys.argv[2:3])
    elif sys.argv[1:2] == ['--refine']:
        refine_eupmyeon()
    elif sys.argv[1:2] == ['--overrides']:
        apply_overrides()
    else:
        main()
