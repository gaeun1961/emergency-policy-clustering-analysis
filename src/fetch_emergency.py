"""국립중앙의료원 응급의료정보조회 OpenAPI -> 전국 응급의료기관 목록

실행: 레포 루트에서 python -m src.fetch_emergency
필요: .env 의 DATA_GO_KR_SERVICE_KEY (공공데이터포털 일반 인증키, Encoding/Decoding 어느 쪽이든 됨)
출력: data/processed/emergency_facilities.csv
"""
import os
import sys
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path
from urllib.parse import unquote

import pandas as pd
import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data' / 'processed' / 'emergency_facilities.csv'
URL = 'http://apis.data.go.kr/B552657/ErmctInfoInqireService/getEgytListInfoInqire'
FIELDS = ['hpid', 'dutyName', 'dutyAddr', 'dutyTel1', 'dutyTel3', 'dutyEmcls', 'dutyEmclsName', 'wgs84Lat', 'wgs84Lon']  # dutyTel1 대표전화, dutyTel3 응급실
SIDO = ['서울특별시', '부산광역시', '대구광역시', '인천광역시', '광주광역시', '대전광역시', '울산광역시', '세종특별자치시',
        '경기도', '강원특별자치도', '충청북도', '충청남도', '전북특별자치도', '전라남도', '경상북도', '경상남도', '제주특별자치도']
PAGE = 1000


def service_key():
    load_dotenv(ROOT / '.env')
    key = os.getenv('DATA_GO_KR_SERVICE_KEY')
    if not key:
        sys.exit('.env 에 DATA_GO_KR_SERVICE_KEY 가 없음')
    return unquote(key)  # Encoding 키를 넣어도 한 번 풀어서, requests가 한 번만 인코딩하게 (이중 인코딩 방지)


def fetch_page(key, page, q0=None):
    params = {'serviceKey': key, 'pageNo': page, 'numOfRows': PAGE}
    if q0:
        params['Q0'] = q0
    r = requests.get(URL, params=params, timeout=30)
    r.raise_for_status()
    try:
        root = ET.fromstring(r.content)
    except ET.ParseError:
        raise RuntimeError(f'XML 아님 (키 미등록/활성화 전일 수 있음): {r.text[:300]}')
    code = root.findtext('.//resultCode') or root.findtext('.//returnReasonCode')
    if code not in ('00', '0000'):
        msg = root.findtext('.//resultMsg') or root.findtext('.//returnAuthMsg') or root.findtext('.//errMsg')
        raise RuntimeError(f'API 오류 {code}: {msg}')
    items = [{f: it.findtext(f) for f in FIELDS} for it in root.iter('item')]
    return items, int(root.findtext('.//totalCount') or 0)


def fetch_all(key, q0=None):
    items, total = fetch_page(key, 1, q0)
    page = 1
    while len(items) < total:
        page += 1
        more, _ = fetch_page(key, page, q0)
        if not more:
            break
        items += more
    return items, total


def main(out=OUT):
    key = service_key()
    items, total = fetch_all(key)
    print(f'전국 조회: {len(items)}건 / totalCount {total}')
    if total == 0 or len(items) < total:
        print('전국 한 번에 안 나와서 시도별(Q0)로 다시 수집')
        items = []
        for s in SIDO:
            got, t = fetch_all(key, s)
            print(f'  {s}: {len(got)}/{t}')
            items += got
    df = pd.DataFrame(items, columns=FIELDS).drop_duplicates('hpid')
    df[['wgs84Lat', 'wgs84Lon']] = df[['wgs84Lat', 'wgs84Lon']].apply(pd.to_numeric, errors='coerce')
    df['수집일자'] = date.today().isoformat()
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False, encoding='utf-8-sig')
    print(f'{len(df)}개 기관 -> {out}')
    return df


if __name__ == '__main__':
    main()
