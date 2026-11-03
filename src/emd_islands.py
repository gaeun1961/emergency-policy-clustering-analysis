"""섬으로 나뉜 읍·면: 리(섬) 단위 기준점

실행: 레포 루트에서 python -m src.emd_islands [기준연월, 기본 202512]
입력: data/raw/emd_population/{연월}/*.json (src.fetch_emd_population 캐시, 통·반 행에 리 이름 포함)
      data/raw/boundary/HangJeongDong_ver20251231.geojson, data/processed/emd_centers.csv
      data/emd_li_weighted.csv: 리 단위 인구가중으로 바꿀 행정동 목록 (직접 관리)
출력: data/processed/emd_li_points.csv: 리 좌표·인구·섬 조각 번호 (캐시: 이미 받은 리는 다시 호출 안 함)
      data/processed/island_eupmyeon.csv: 경계가 여러 섬 조각이고 면사무소와 다른 섬에 사람이 사는 읍·면 목록

리 좌표: 카카오 주소 검색('전북특별자치도 군산시 옥도면 선유도리')으로 받고, 그 읍·면 경계의 어느 섬 조각 안인지 확인
"""
import json
import math
import os
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

from .emd_centers import OUT as EMD_CENTERS, RAW, in_polygon, km_to_polygon

ROOT = Path(__file__).resolve().parents[1]
LI_POINTS = ROOT / 'data' / 'processed' / 'emd_li_points.csv'
SURVEY = ROOT / 'data' / 'processed' / 'island_eupmyeon.csv'
LI_WEIGHTED = ROOT / 'data' / 'emd_li_weighted.csv'
ADDRESS_URL = 'https://dapi.kakao.com/v2/local/search/address.json'
MIN_PIECE_KM2 = 0.05  # 이보다 작은 조각(바위·간출지)은 섬으로 세지 않음
SNAP_KM = 1.0         # 리 좌표가 섬 조각에서 이보다 멀면(카카오 리 대표점이 바다에 찍힌 경우) 해안선 위 가장 가까운 점으로 옮김


def km(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * 6371.0088 * math.asin(math.sqrt(a))


def pieces(geom):
    """섬 조각(바깥 고리 기준) 목록과 면적(km², 평면 근사)"""
    polys = geom['coordinates'] if geom['type'] == 'MultiPolygon' else [geom['coordinates']]
    out = []
    for poly in polys:
        ring = poly[0]
        lat0 = sum(y for _, y in ring) / len(ring)
        kx, ky = 111.32 * math.cos(math.radians(lat0)), 110.57
        area = abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(ring, ring[1:]))) / 2 * kx * ky
        out.append({'geometry': {'type': 'Polygon', 'coordinates': poly}, 'km2': area})
    return out


def piece_of(lon, lat, ps):
    """점이 들어 있는 조각 번호. 없으면 가장 가까운 조각과 거리"""
    for i, p in enumerate(ps):
        if in_polygon(lon, lat, p['geometry']):
            return i, 0.0
    d = [km_to_polygon(lon, lat, p['geometry']) for p in ps]
    i = min(range(len(ps)), key=d.__getitem__)
    return i, d[i]


def nearest_on_boundary(lon, lat, geom):
    """점에서 가장 가까운 경계(해안선) 위의 점 (위경도)"""
    kx, ky = 111.32 * math.cos(math.radians(lat)), 110.57
    best = (math.inf, lon, lat)
    for ring in geom['coordinates']:
        for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
            ax, ay, bx, by = (x1 - lon) * kx, (y1 - lat) * ky, (x2 - lon) * kx, (y2 - lat) * ky
            dx, dy = bx - ax, by - ay
            t = max(0.0, min(1.0, -(ax * dx + ay * dy) / (dx * dx + dy * dy or 1)))
            d = math.hypot(ax + t * dx, ay + t * dy)
            if d < best[0]:
                best = (d, x1 + t * (x2 - x1), y1 + t * (y2 - y1))
    return best[1], best[2]


def li_population(ym):
    """API 캐시(통·반 행) -> (행정동코드, 리) 인구. 출장소 행은 소속 행정동으로 (src.emd_centers --population 이 정한 대응)"""
    m = pd.read_csv(ROOT / 'data' / 'processed' / f'emd_population_{ym}.csv', dtype={'행정동코드': str, '소속행정동코드': str})
    parent = dict(zip(m['행정동코드'], m['소속행정동코드']))
    pop = defaultdict(int)
    for f in (ROOT / 'data' / 'raw' / 'emd_population' / ym).glob('*.json'):
        for x in json.loads(f.read_text(encoding='utf-8')):
            if x.get('liNm'):
                pop[(parent.get(x['admmCd'], x['admmCd']), x['liNm'])] += int(x['totNmprCnt'])
    return pop


def geocode_li(targets, names):
    """리 주소 -> 좌표 (캐시). targets: [(행정동코드, 리)]"""
    load_dotenv(ROOT / '.env')
    key = os.getenv('KAKAO_REST_API_KEY')
    cache = pd.read_csv(LI_POINTS, dtype={'행정동코드': str}) if LI_POINTS.exists() else pd.DataFrame(columns=['행정동코드', '리', '위도', '경도'])
    cache = cache.dropna(subset=['위도'])  # 좌표를 못 받은 리는 다시 시도
    have = set(zip(cache['행정동코드'], cache['리']))
    rows = []
    for code, li in targets:
        if (code, li) in have:
            continue
        parts = names[code].split()  # ['제주특별자치도', '제주시', '한경면']
        hit = None
        for q in (' '.join(parts + [li]), ' '.join(parts[1:] + [li]), f'{parts[-1]} {li}'):  # 시도를 빼면 찾는 경우가 있음
            r = requests.get(ADDRESS_URL, params={'query': q}, headers={'Authorization': f'KakaoAK {key}'}, timeout=10)
            r.raise_for_status()
            docs = [d for d in r.json()['documents'] if d['address_name'].split()[-1] == li]
            if docs:
                hit = docs[0]
                break
        rows.append({'행정동코드': code, '리': li, '위도': float(hit['y']) if hit else None, '경도': float(hit['x']) if hit else None})
    out = pd.concat([cache[['행정동코드', '리', '위도', '경도']], pd.DataFrame(rows)], ignore_index=True) if rows else cache[['행정동코드', '리', '위도', '경도']]
    return out


def main(ym='202512'):
    feats = {f['properties']['adm_cd2']: f for f in json.loads(RAW.read_text(encoding='utf-8'))['features']}
    names = {k: f['properties']['adm_nm'] for k, f in feats.items()}
    centers = pd.read_csv(EMD_CENTERS, dtype={'코드': str}).set_index('코드')
    pop = li_population(ym)

    # 대상: 읍·면이고, 바위보다 큰 조각이 2개 이상
    cand = {}
    for code, f in feats.items():
        if not names[code].endswith(('읍', '면')):
            continue
        ps = [p for p in pieces(f['geometry']) if p['km2'] >= MIN_PIECE_KM2]
        if len(ps) >= 2:
            cand[code] = ps
    li_w = set(pd.read_csv(LI_WEIGHTED, dtype={'행정동코드': str})['행정동코드']) if LI_WEIGHTED.exists() else set()
    targets = [(c, li) for (c, li), n in pop.items() if n > 0 and (c in cand or c in li_w)]
    print(f'섬 조각이 2개 이상인 읍·면 {len(cand)}곳, 좌표가 필요한 유인 리 {len(targets)}곳')
    pts = geocode_li(targets, names)

    rows, survey = [], []
    for code in sorted(set(cand) | li_w):
        ps = cand.get(code) or [p for p in pieces(feats[code]['geometry']) if p['km2'] >= MIN_PIECE_KM2]
        office = centers.loc[code]
        o_piece, _ = piece_of(office['경도'], office['위도'], ps)
        lis = []
        for (c, li), n in pop.items():
            if c != code or n <= 0:
                continue
            p = pts[(pts['행정동코드'] == c) & (pts['리'] == li)]
            if p.empty or pd.isna(p['위도'].iloc[0]):
                print(f'  [경고] 리 좌표 없음: {names[c]} {li}')
                continue
            lat, lon = p['위도'].iloc[0], p['경도'].iloc[0]
            k, off = piece_of(lon, lat, ps)
            if off > SNAP_KM:
                print(f'  [보정] {names[c]} {li}: 섬 조각에서 {off:.2f}km 떨어진 좌표 -> 해안선 위 점으로')
                lon, lat = nearest_on_boundary(lon, lat, ps[k]['geometry'])
            lis.append({'행정동코드': c, '리': li, '위도': lat, '경도': lon, '인구': n, '섬조각': k, '경계밖km': round(off, 2),
                        '면사무소거리km': round(km(office['위도'], office['경도'], lat, lon), 1)})
        rows += lis
        away = [x for x in lis if x['섬조각'] != o_piece]
        if away:
            far = max(away, key=lambda x: x['면사무소거리km'])
            survey.append({'행정동코드': code, '이름': names[code], '섬조각수': len(ps),
                           '유인섬수': len({x['섬조각'] for x in lis}), '인구': sum(x['인구'] for x in lis),
                           '면사무소와_다른섬_인구': sum(x['인구'] for x in away), '기준점': office['장소명'] or office['좌표출처'],
                           '가장먼유인도_리': far['리'], '가장먼유인도_km': far['면사무소거리km']})

    pd.DataFrame(rows).to_csv(LI_POINTS, index=False, encoding='utf-8-sig')
    s = pd.DataFrame(survey).sort_values('가장먼유인도_km', ascending=False)
    s.to_csv(SURVEY, index=False, encoding='utf-8-sig')
    print(f'리 좌표 {len(rows)}곳 -> {LI_POINTS}')
    off = [r for r in rows if r['경계밖km'] > 0]
    print(f'리 좌표가 읍·면 경계 밖인 곳 {len(off)}곳 (가장 가까운 조각으로 배정):', [(names[r['행정동코드']].split()[-1], r['리'], r['경계밖km']) for r in off][:20])
    print(f'면사무소와 다른 섬에 사람이 사는 읍·면 {len(s)}곳 -> {SURVEY}')
    return s


if __name__ == '__main__':
    main(*sys.argv[1:2])
