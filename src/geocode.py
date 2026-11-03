"""시군구 기준점(시청·군청·구청) 좌표: 카카오 로컬 검색

실행: 레포 루트에서 python -m src.geocode
필요: .env 의 KAKAO_REST_API_KEY
입력: data/processed/population_sigungu_202512.csv, data/sigungu_center_overrides.csv (예외 기준점)
출력: data/processed/sigungu_centers.csv (캐시: 같은 시군구·검색어로 이미 받은 좌표는 다시 호출하지 않음)

방식
- keyword (기본): '경기도 수원시청' 키워드 검색. 일반구를 합친 시는 시청, 세종은 세종특별자치시청
- address (예외): 예외 테이블의 도로명주소를 주소 검색
- weighted (예외): 예외 테이블의 지점(';' 구분) 여러 개를 각각 키워드 검색. 거리는 accessibility에서 가중평균
"""
import os
import sys
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

from .loaders import clean_sido_name

ROOT = Path(__file__).resolve().parents[1]
POP_CSV = ROOT / 'data' / 'processed' / 'population_sigungu_202512.csv'
OVERRIDES = ROOT / 'data' / 'sigungu_center_overrides.csv'
OUT = ROOT / 'data' / 'processed' / 'sigungu_centers.csv'
KEYWORD_URL = 'https://dapi.kakao.com/v2/local/search/keyword.json'
ADDRESS_URL = 'https://dapi.kakao.com/v2/local/search/address.json'
SIDO_FULL = {'서울': '서울특별시', '부산': '부산광역시', '대구': '대구광역시', '인천': '인천광역시', '광주': '광주광역시',
             '대전': '대전광역시', '울산': '울산광역시', '세종': '세종특별자치시', '경기': '경기도', '강원': '강원특별자치도',
             '충북': '충청북도', '충남': '충청남도', '전북': '전북특별자치도', '전남': '전라남도', '경북': '경상북도',
             '경남': '경상남도', '제주': '제주특별자치도'}
COLS = ['행정기관코드', '시도', '시군구', '방식', '지점', 'query', 'place_name', 'address', 'lat', 'lon', '시군구안']


def in_region(address, sido, sgg):
    """검색 결과 주소가 해당 시도·시군구 안인지 (주소 예: '경기 수원시 팔달구 효원로 241')"""
    parts = str(address).split()
    if len(parts) < 2:
        return False
    a_sido = clean_sido_name(parts[0])
    if a_sido == '전남광주통합':  # 2026 광주·전남 통합 이후 주소 표기
        a_sido = sido if sido in ('광주', '전남') else a_sido
    return a_sido == sido and (not sgg or parts[1] == sgg)


def kakao(url, key, q):
    r = requests.get(url, params={'query': q, 'size': 15} if url == KEYWORD_URL else {'query': q},
                     headers={'Authorization': f'KakaoAK {key}'}, timeout=10)
    r.raise_for_status()
    return r.json()['documents']


def bare_name(name):
    """'부산광역시중구청', '전남광주통합특별시 서구청' -> '중구청', '서구청'"""
    for s in [*SIDO_FULL.values(), '전남광주통합특별시']:
        if name.startswith(s):
            return name[len(s):].strip()
    return name


def keyword(key, q, place, sido, sgg):
    """카카오 분류가 '지방행정기관'(시청·군청·구청·면사무소)이고 이름이 지점명으로 시작하는 결과만 후보.
    주차장·은행·교차로 등은 분류가 달라서 빠진다. 해당 시군구 안 > 완공 '예정' 청사 아님 > 이름 정확히 일치 순.
    밖이면 시군구안=False"""
    names = lambda d: (d['place_name'], bare_name(d['place_name']))  # 세종특별자치시청은 원래 이름으로 맞춰야 함
    docs = [d for d in kakao(KEYWORD_URL, key, q)
            if '지방행정기관' in d['category_name'] and any(n.startswith(place) for n in names(d))]
    docs.sort(key=lambda d: (not in_region(d['address_name'], sido, sgg), '예정' in d['place_name'],
                             place not in names(d)))
    best = docs[0] if docs else None
    if best is None:
        return dict(place_name=None, address=None, lat=None, lon=None, 시군구안=False)
    return dict(place_name=best['place_name'], address=best['address_name'], lat=float(best['y']),
                lon=float(best['x']), 시군구안=in_region(best['address_name'], sido, sgg))


def address(key, q):
    docs = kakao(ADDRESS_URL, key, q)
    if not docs:
        return dict(place_name=None, address=None, lat=None, lon=None, 시군구안=False)
    # 주소 검색은 예외 테이블에 사람이 직접 넣은 2025년 기준 주소라 시군구 안으로 본다
    return dict(place_name=q, address=docs[0]['address_name'], lat=float(docs[0]['y']), lon=float(docs[0]['x']), 시군구안=True)


def plan(pop, overrides):
    """시군구별 검색할 지점 목록"""
    ov = {(r.시도, r.시군구): r for r in overrides.itertuples()}
    rows = []
    for r in pop.itertuples():
        o = ov.get((r.시도, r.시군구))
        base = dict(행정기관코드=r.행정기관코드, 시도=r.시도, 시군구=r.시군구)
        if o is None:
            q = f'{SIDO_FULL[r.시도]}청' if not r.시군구 else f'{SIDO_FULL[r.시도]} {r.시군구}청'
            rows.append(dict(base, 방식='keyword', 지점=q.split()[-1], query=q))
        elif o.방식 == 'address':
            rows.append(dict(base, 방식='address', 지점=o.값, query=o.값))
        else:  # weighted
            rows += [dict(base, 방식='weighted', 지점=p, query=f'{SIDO_FULL[r.시도]} {r.시군구} {p}') for p in o.값.split(';')]
    return pd.DataFrame(rows)


def main(out=OUT):
    load_dotenv(ROOT / '.env')
    key = os.getenv('KAKAO_REST_API_KEY')
    if not key:
        sys.exit('.env 에 KAKAO_REST_API_KEY 가 없음')
    pop = pd.read_csv(POP_CSV, dtype={'행정기관코드': str}).fillna({'시군구': ''})
    todo = plan(pop, pd.read_csv(OVERRIDES).fillna({'시군구': ''}))

    cache = pd.read_csv(out, dtype={'행정기관코드': str}).dropna(subset=['lat']) if out.exists() else None
    if cache is not None and not cache.empty:
        todo = todo.merge(cache.drop(columns=['방식', '지점', '시도', '시군구']), on=['행정기관코드', 'query'], how='left')
    todo = todo.reindex(columns=COLS).astype({'place_name': object, 'address': object, '시군구안': object})
    new = todo['lat'].isna()
    print(f'지점 {len(todo)}개 중 캐시 {(~new).sum()}개, 새로 검색 {new.sum()}개')

    found = [address(key, r.query) if r.방식 == 'address' else keyword(key, r.query, r.지점, r.시도, r.시군구)
             for r in todo[new].itertuples()]
    if found:
        todo.loc[new, list(found[0])] = pd.DataFrame(found, index=todo.index[new])
    centers = todo[COLS].sort_values(['행정기관코드', '지점'])
    out.parent.mkdir(parents=True, exist_ok=True)
    centers.to_csv(out, index=False, encoding='utf-8-sig')

    fail = centers[centers['lat'].isna()]
    outside = centers[centers['lat'].notna() & ~centers['시군구안'].astype(bool)]
    print(f'{centers["행정기관코드"].nunique()}개 시군구, 좌표 {len(centers) - len(fail)}/{len(centers)}개 -> {out}')
    print('실패: 없음' if fail.empty else f'실패:\n{fail[["시도", "시군구", "query"]].to_string()}')
    if len(outside):
        print(f'[경고] 기준점이 해당 시군구 밖 -> sigungu_center_overrides.csv 에 예외 추가 필요:\n'
              f'{outside[["시도", "시군구", "place_name", "address"]].to_string()}')
    return centers


if __name__ == '__main__':
    main()
