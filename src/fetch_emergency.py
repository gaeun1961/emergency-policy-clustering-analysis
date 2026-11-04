"""국립중앙의료원 응급의료정보조회 OpenAPI -> 전국 응급의료기관 목록

실행: 레포 루트에서 python -m src.fetch_emergency            (기관 목록)
      python -m src.fetch_emergency --capacity (응급의료기관 G001·G006·G007 병상 수, 2SFCA 공급량)
필요: .env 또는 환경변수의 DATA_GO_KR_SERVICE_KEY (없으면 KR_SERVICE_KEY). 공공데이터포털 일반 인증키, Encoding/Decoding 어느 쪽이든 됨
출력: data/processed/emergency_facilities.csv
      data/processed/emergency_capacity.csv: hpid, 응급실병상수(hperyn), 총병상수(hpbdn), 수집일자 (기본정보 API, 기관당 1회 호출)
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


KEY_NAMES = ('DATA_GO_KR_SERVICE_KEY', 'KR_SERVICE_KEY')  # 앞 이름 우선


def service_key():
    """공공데이터포털 키 (응급의료기관·행정동 인구 API 공용). 값은 출력하지 않는다"""
    load_dotenv(ROOT / '.env')
    key = next((v for n in KEY_NAMES if (v := os.getenv(n))), None)
    if not key:
        sys.exit(f'.env 또는 환경변수에 {" / ".join(KEY_NAMES)} 가 없음')
    return unquote(key)  # Encoding 키를 넣어도 한 번 풀어서, requests가 한 번만 인코딩하게 (이중 인코딩 방지)


def get(url, params, retries=3):
    """requests.get 인데, 실패하면 URL(serviceKey 포함)이 없는 메시지로 바꿔 올린다.
    requests 예외·raise_for_status 메시지에는 키가 든 전체 URL이 들어가 로그에 키가 남기 때문"""
    import time
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, timeout=30)
            if r.status_code >= 500:
                raise requests.HTTPError(f'HTTP {r.status_code}')
            return r
        except requests.RequestException as e:
            last = f'{type(e).__name__} ({url.rsplit("/", 1)[-1]})'
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f'요청 실패 {retries}회: {last}') from None


def fetch_page(key, page, q0=None):
    params = {'serviceKey': key, 'pageNo': page, 'numOfRows': PAGE}
    if q0:
        params['Q0'] = q0
    r = get(URL, params)
    if r.status_code != 200:
        raise RuntimeError(f'HTTP {r.status_code} (getEgytListInfoInqire)')
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


CAPACITY = ROOT / 'data' / 'processed' / 'emergency_capacity.csv'
BASS_URL = 'http://apis.data.go.kr/B552657/ErmctInfoInqireService/getEgytBassInfoInqire'


def fetch_capacity(out=CAPACITY):
    """응급의료기관(G001·G006·G007)마다 기본정보 API로 응급실 병상(hperyn)·총 병상(hpbdn)을 받는다.
    실시간 가용 병상(hvec)은 시시각각 바뀌어 쓰지 않는다. 초당 요청 제한(429)이 있어 하나씩 보내고, 걸리면 기다렸다 다시 보낸다.
    이미 받은 기관은 다시 호출하지 않는다(캐시)
    """
    import time
    key = service_key()
    fac = pd.read_csv(OUT, dtype={'hpid': str})
    hp = fac.loc[fac['dutyEmcls'].isin(['G001', 'G006', 'G007']), 'hpid'].tolist()
    have = pd.read_csv(out, dtype={'hpid': str}).dropna(subset=['응급실병상수']) if out.exists() else pd.DataFrame()
    done = dict(zip(have['hpid'], have.to_dict('records'))) if len(have) else {}

    def one(h):
        for attempt in range(6):
            r = get(BASS_URL, {'serviceKey': key, 'HPID': h})
            if r.status_code == 429 or b'LIMITED_NUMBER' in r.content:
                time.sleep(10 * (attempt + 1))  # 제한에 걸리면 한동안 풀리지 않아 길게 기다림
                continue
            it = ET.fromstring(r.content).find('.//item')
            num = lambda tag: pd.to_numeric(it.findtext(tag) if it is not None else None, errors='coerce')  # noqa: E731
            return {'hpid': h, '응급실병상수': num('hperyn'), '총병상수': num('hpbdn')}
        raise RuntimeError(f'{h}: 요청 제한이 계속됨')

    rows = []
    save = lambda: pd.DataFrame(rows).assign(수집일자=date.today().isoformat()).to_csv(out, index=False, encoding='utf-8-sig')  # noqa: E731
    for n, h in enumerate(hp, 1):
        if h in done:
            rows.append({k: done[h][k] for k in ('hpid', '응급실병상수', '총병상수')})
            continue
        rows.append(one(h))
        if n % 25 == 0:
            save()  # 중간에 끊겨도 받은 만큼은 남긴다 (다시 실행하면 이어서)
        time.sleep(1.0)  # 초당 요청 제한
    save()
    df = pd.read_csv(out, dtype={'hpid': str})
    bad = df['응급실병상수'].isna() | (df['응급실병상수'] <= 0)
    print(f'{len(df)}개 기관 병상 -> {out}. 응급실 병상 없음·0: {bad.sum()}곳, 응급실 병상 합 {int(df["응급실병상수"].sum()):,}')
    return df


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
    fetch_capacity() if '--capacity' in sys.argv else main()
