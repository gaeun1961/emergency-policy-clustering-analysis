"""행정동 인구 수집: 행정안전부_법정동별(행정동 통반단위) 성/연령별 주민등록 인구수 OpenAPI (공공데이터포털 15108074)

실행: 레포 루트에서 python -m src.fetch_emd_population [기준연월, 기본 src/config.py YM]
필요: .env 의 DATA_GO_KR_SERVICE_KEY 또는 KR_SERVICE_KEY (이 API 활용신청 필요, src.fetch_emergency.service_key)
출력: data/processed/emd_population_{기준연월}.csv  (행정동코드, 행정동명, 시도명, 시군구명, 총인구)
캐시: data/raw/emd_population/{기준연월}/*.json  (법정 읍면동별 응답. 중간에 끊겨도 이어 받음, gitignore)

API는 행정동 코드(admmCd)를 통·반 단위(lv=4)에서만 주고, lv=4는 법정 읍면동 코드 하나씩만 조회된다. 그래서
  1) 시도별 lv=2 -> 시군구 목록 (일반구가 있는 시는 구만 사용해 중복 방지)
  2) 시군구별 lv=3 -> 법정 리·동 코드 -> 법정 읍면동 코드(앞 8자리 + '00')
  3) 법정 읍면동별 lv=4 -> 통·반 행을 admmCd(행정동)별로 합산
regSeCd=1(전체: 거주자 + 거주불명자 + 재외국민)이라 행안부 연령별 인구현황의 총 인구수와 같은 기준이다.
"""
import json
import os
import sys
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
import requests
from . import fetch_emergency
from .config import YM

ROOT = Path(__file__).resolve().parents[1]
URL = 'https://apis.data.go.kr/1741000/stdgSexdAgePpltn/selectStdgSexdAgePpltn'
ROWS = 5000      # 한 번에 받을 행 수 (문서상 100이지만 더 크게 받아짐)
CALLS = Counter()  # 요청 수 집계: 요청(재시도 포함), 재시도, 실패
_lock = threading.Lock()
WORKERS = int(os.getenv('EMD_WORKERS', '4'))  # 동시 요청 수. 응답이 느리면 EMD_WORKERS=10 정도로 (과하게 늘리지 않음)


service_key = fetch_emergency.service_key  # DATA_GO_KR_SERVICE_KEY 우선, 없으면 KR_SERVICE_KEY. URL 인코딩은 풀어 둠


def call(key, ym, stdg, lv):
    """모든 페이지를 받아 item 목록. 데이터 없음(NODATA)은 빈 목록"""
    items, page = [], 1
    while True:
        for attempt in range(4):
            with _lock:
                CALLS['요청'] += 1
                CALLS['재시도'] += attempt > 0
            try:
                r = requests.get(URL, params={'serviceKey': key, 'stdgCd': stdg, 'srchFrYm': ym, 'srchToYm': ym, 'lv': lv,
                                              'regSeCd': 1, 'type': 'JSON', 'numOfRows': ROWS, 'pageNo': page}, timeout=60)
                body = r.json()
                break
            except (requests.RequestException, ValueError):
                time.sleep(2 * (attempt + 1))
        else:
            with _lock:
                CALLS['실패'] += 1
            raise RuntimeError(f'{stdg} lv{lv} 요청 실패')
        if 'OpenAPI_ServiceResponse' in body:
            raise RuntimeError(f'API 오류: {body["OpenAPI_ServiceResponse"]["cmmMsgHeader"]}')
        res = body['Response']
        head = res['head']
        if head.get('resultCode') not in ('0', '00'):
            if 'NODATA' in head.get('resultMsg', ''):
                return items
            raise RuntimeError(f'API 오류 {stdg} lv{lv}: {head}')
        got = (res.get('items') or {}).get('item', [])
        items += got if isinstance(got, list) else [got]
        if len(items) >= int(head['totalCount']) or not got:
            return items
        page += 1


def sigungu_codes(key, ym):
    """시군구 목록. 일반구가 있는 시(포항시)는 빼고 구(포항시 남구, 포항시 북구)만.
    상위 시 판정은 이름으로: 다른 시군구 이름이 '포항시 '로 시작하면 포항시는 상위 시 (코드만 보면 영동군 43740과 증평군 43745를 헷갈림)"""
    sido = [x['stdgCd'] for x in call(key, ym, '1100000000', 1)]
    rows = [(x['stdgCd'], x.get('sggNm', '')) for s in sido for x in call(key, ym, s, 2)]
    parents = {c for c, n in rows if n and any(o.startswith(n + ' ') for _, o in rows)}
    return [c for c, _ in rows if c not in parents]


def main(ym=YM):
    key = service_key()
    cache = ROOT / 'data' / 'raw' / 'emd_population' / ym
    cache.mkdir(parents=True, exist_ok=True)

    sgg = sigungu_codes(key, ym)
    print(f'[{ym}] 시군구 {len(sgg)}개')
    with ThreadPoolExecutor(WORKERS) as ex:
        emd_lists = list(ex.map(lambda s: {x['stdgCd'][:8] + '00' for x in call(key, ym, s, 3)}, sgg))
    emds = sorted(set().union(*emd_lists))
    todo = [e for e in emds if not (cache / f'{e}.json').exists()]
    print(f'법정 읍면동 {len(emds)}개 중 캐시 {len(emds) - len(todo)}개, 새로 받기 {len(todo)}개')

    def fetch(e):
        items = call(key, ym, e, 4)
        (cache / f'{e}.json').write_text(json.dumps(items, ensure_ascii=False), encoding='utf-8')
    done = 0
    with ThreadPoolExecutor(WORKERS) as ex:
        for _ in ex.map(fetch, todo):
            done += 1
            if done % 250 == 0:
                print(f'  {done}/{len(todo)}', flush=True)

    total = defaultdict(int)
    names = {}
    for e in emds:
        for x in json.loads((cache / f'{e}.json').read_text(encoding='utf-8')):
            total[x['admmCd']] += int(x['totNmprCnt'])
            names[x['admmCd']] = (x.get('dongNm', ''), x.get('ctpvNm', ''), x.get('sggNm', ''))  # 세종 등은 시군구명 없음
    df = pd.DataFrame([{'행정동코드': c, '행정동명': names[c][0], '시도명': names[c][1], '시군구명': names[c][2], '총인구': n}
                       for c, n in sorted(total.items())])
    out = ROOT / 'data' / 'processed' / f'emd_population_{ym}.csv'
    df.to_csv(out, index=False, encoding='utf-8-sig')
    print(f'행정동 {len(df)}개, 총인구 {df["총인구"].sum():,}명 -> {out}')
    print(f'API 호출: 요청 {CALLS["요청"]}회 (재시도 {CALLS["재시도"]}회 포함), 실패 {CALLS["실패"]}회')
    return df


if __name__ == '__main__':
    main(*sys.argv[1:2])
