"""원천 데이터 변경 감지 (GitHub Actions data-watch.yml 이 월 1회 실행, 로컬 실행도 가능)

실행: 레포 루트에서 python scripts/check_data_updates.py [출력 폴더, 기본 data-watch]
필요: 환경변수 또는 .env 의 DATA_GO_KR_SERVICE_KEY (없으면 KR_SERVICE_KEY). Actions 에서는 GitHub Secrets
출력: {출력 폴더}/facilities.md  응급의료기관 변경 목록 (변경 있을 때만)
      {출력 폴더}/population.md  행정동 인구 새 기준월 안내 (새 달이 있을 때만)
      GITHUB_OUTPUT 이 있으면 facilities_changed=true/false, population_ym=YYYYMM(없으면 빈 값)

비교 기준
- 응급의료기관: web/public/data/facilities.json (분석에 쓰는 G001·G006·G007) vs 지금 API.
  추가·삭제·등급·이름 변경(공백만 다른 것은 무시)과 좌표 이동(MOVE_M 이상)을 찾는다
- 행정동 인구: data/processed/emd_population_{YYYYMM}.csv 중 최신 달 vs API에 데이터가 있는 가장 최근 달
키는 출력하지 않는다. 오류 메시지에서도 키(원문·URL 인코딩)를 지운다
"""
import json
import os
import sys
from datetime import date
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src import fetch_emd_population, fetch_emergency  # noqa: E402
from src.accessibility import EMERGENCY, GRADE, haversine  # noqa: E402

FACILITIES = ROOT / 'web' / 'public' / 'data' / 'facilities.json'
MOVE_M = 50  # 이보다 적게 움직인 좌표는 같은 위치로 본다 (API 좌표 소수점 차이)


def safe(e, key):
    """예외 메시지에서 키를 지운다 (requests 오류에는 serviceKey 가 든 URL이 들어감)"""
    msg = f'{type(e).__name__}: {e}'
    for k in {key, quote(key, safe=''), quote(key)}:
        msg = msg.replace(k, '***')
    return msg


def facility_changes(key):
    old = {f['hpid']: f for f in json.loads(FACILITIES.read_text(encoding='utf-8'))}
    items, _ = fetch_emergency.fetch_all(key)
    new = {x['hpid']: x for x in items if x['dutyEmcls'] in EMERGENCY}
    rows = []
    for h in sorted(new.keys() - old.keys()):
        x = new[h]
        rows.append(f'| 추가 | {x["dutyName"]} | {GRADE[x["dutyEmcls"]]} | {x["dutyAddr"]} |')
    for h in sorted(old.keys() - new.keys()):
        f = old[h]
        rows.append(f'| 삭제(또는 G009로 변경) | {f["기관명"]} | {GRADE[f["등급"]]} | {f.get("주소", "")} |')
    for h in sorted(old.keys() & new.keys()):
        f, x = old[h], new[h]
        what = []
        if f['등급'] != x['dutyEmcls']:
            what.append(f'등급 {GRADE[f["등급"]]} → {GRADE[x["dutyEmcls"]]}')
        if f['기관명'].replace(' ', '') != x['dutyName'].replace(' ', ''):
            what.append(f'이름 {f["기관명"]} → {x["dutyName"]}')
        m = haversine([f['위도']], [f['경도']], [float(x['wgs84Lat'])], [float(x['wgs84Lon'])])[0, 0] * 1000
        if m >= MOVE_M:
            what.append(f'좌표 {m:,.0f}m 이동')
        if what:
            rows.append(f'| 변경 | {x["dutyName"]} | {", ".join(what)} | {x["dutyAddr"]} |')
    return rows, len(old), len(new)


def months_after(ym, until):
    y, m = int(ym[:4]), int(ym[4:])
    while True:
        m += 1
        if m > 12:
            y, m = y + 1, 1
        if (y, m) > until:
            return
        yield f'{y}{m:02d}'


def latest_population_month(key, used):
    """used 다음 달부터 지난달까지, API에 시도 목록이 나오는 가장 최근 달과 시도 수 (없으면 None, None)
    이번 달은 아직 집계 전이라 API가 INVALID_REQUEST_PARAMETER_ERROR 를 주므로 보지 않는다"""
    today = date.today()
    last = (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)
    found, n = None, None
    for ym in months_after(used, last):
        if sido := fetch_emd_population.call(key, ym, '1100000000', 1):
            found, n = ym, len(sido)
    return found, n


def main(out_dir='data-watch'):
    out = ROOT / out_dir
    out.mkdir(parents=True, exist_ok=True)
    key = fetch_emergency.service_key()  # .env 또는 환경변수, URL 인코딩은 풀어 둠
    outputs = {}

    try:
        rows, n_old, n_new = facility_changes(key)
    except Exception as e:  # noqa: BLE001 - 키를 지운 메시지만 남기고 실패로 끝낸다
        sys.exit(f'응급의료기관 API 확인 실패: {safe(e, key)}')
    print(f'[응급의료기관] 현재 {n_old}곳, API {n_new}곳, 변경 {len(rows)}건')
    outputs['facilities_changed'] = 'true' if rows else 'false'
    if rows:
        (out / 'facilities.md').write_text('\n'.join([
            f'월간 점검({date.today().isoformat()})에서 응급의료기관(권역·지역센터, 지역응급의료기관) 변경을 찾았습니다.',
            f'현재 대시보드 {n_old}곳 → API {n_new}곳',
            '', '| 구분 | 기관 | 내용 | 주소 |', '|---|---|---|---|', *rows, '',
            '### 반영 방법 (로컬)',
            '- [ ] `python -m src.fetch_emergency`',
            '- [ ] WSL에서 `bash scripts/osrm_setup.sh serve` 후 `python -m src.drivetime` (**OSRM 주행시간 재계산 필요**, Actions에서는 하지 않음)',
            '- [ ] `python -m src.accessibility` → `python -m src.build_table` → 노트북 실행 → `python scripts/export_web_data.py`',
            '- [ ] 등급 변화 확인 후 PR',
        ]) + '\n', encoding='utf-8')

    used = max(p.stem.rsplit('_', 1)[1] for p in (ROOT / 'data' / 'processed').glob('emd_population_*.csv'))
    try:
        ym, n_sido = latest_population_month(key, used)
        n_used = len(fetch_emd_population.call(key, used, '1100000000', 1))
    except Exception as e:  # noqa: BLE001
        sys.exit(f'행정동 인구 API 확인 실패: {safe(e, key)}')
    print(f'[행정동 인구] 사용 중 {used}, API 최신 {ym or used} ({"새 달 있음" if ym else "변경 없음"})')
    outputs['population_ym'] = ym or ''
    if ym:
        (out / 'population.md').write_text('\n'.join([
            f'행정동 인구 API에 새 기준월 **{ym}** 데이터가 있습니다(사용 중: {used}).',
            *(['', f'> 시도 수가 {n_used}개에서 {n_sido}개로 바뀌었습니다. 행정구역 개편(경계·코드·region_mapping)을 먼저 확인하세요.']
              if n_sido != n_used else []),
            '', '### 반영 방법 (로컬)',
            f'- [ ] `python -m src.fetch_emd_population {ym}` → `python -m src.emd_centers --population {ym}` → `python -m src.emd_islands {ym}`',
            '- [ ] 행안부 인구·1인세대 파일도 같은 달로 받아 `python -m src.population` (data/README 수동 갱신 체크리스트)',
            '- [ ] 기준점 인구가 바뀌므로 WSL OSRM으로 `python -m src.drivetime` 재계산 후 accessibility → build_table → 노트북 → export',
            '- [ ] 기준 시점(README·meta) 갱신',
        ]) + '\n', encoding='utf-8')

    if gh := os.getenv('GITHUB_OUTPUT'):
        with open(gh, 'a', encoding='utf-8') as f:
            f.writelines(f'{k}={v}\n' for k, v in outputs.items())


if __name__ == '__main__':
    main(*sys.argv[1:2])
