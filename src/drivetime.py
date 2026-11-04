"""행정동 기준점 × 응급의료기관 자동차 주행시간 (로컬 OSRM table API)

실행: WSL에서 bash scripts/osrm_setup.sh serve 로 OSRM(localhost:5000)을 띄운 뒤, 레포 루트에서 python -m src.drivetime
입력: 기준점 src.accessibility.load_centers(), 응급의료기관(G001·G006·G007) src.accessibility.load_facilities()
출력: data/processed/drivetime_pairs.csv: 기준점마다 직선거리 가까운 응급의료기관 10곳 + 권역·지역센터 10곳의
        주행시간(초)·주행거리(m). 길이 없으면(연륙 안 된 섬 등) 비어 있음
      data/processed/drivetime_snap.csv: 기준점·기관을 도로에 붙인(스냅) 거리(m)

페리는 빼고(exclude=ferry) 계산한다. 해상 이동은 반영하지 않으므로 다리가 없는 섬은 육지 기관에 도달 불가가 된다.
기준점이 도로에서 1km 넘게 떨어지면(OSM 도로가 없는 섬 등) 다른 섬·육지 도로에 붙어 바다를 건너는 경로가 나오므로
그 기준점의 주행시간은 모두 비우고 미연결사유를 남긴다 -> accessibility 에서 직선거리 × 우회계수로 대체
"""
import os
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd
import requests

from . import accessibility as acc

OSRM = os.getenv('OSRM_URL', 'http://localhost:5000')
TOP = 10
PAIRS = acc.PROC / 'drivetime_pairs.csv'
SNAP = acc.PROC / 'drivetime_snap.csv'
SNAP_REPORT_M = 1000


def table(src, dests):
    """기준점 1곳 -> 기관 여러 곳. (주행시간 초, 주행거리 m, 기준점 스냅 m, 기관 스냅 m)"""
    coords = ';'.join(f'{lon:.6f},{lat:.6f}' for lat, lon in [src, *dests])
    r = requests.get(f'{OSRM}/table/v1/driving/{coords}', params={
        'sources': 0, 'destinations': ';'.join(map(str, range(1, len(dests) + 1))),
        'annotations': 'duration,distance', 'exclude': 'ferry'}, timeout=60)
    r.raise_for_status()
    j = r.json()
    if j['code'] != 'Ok':
        raise RuntimeError(j)
    return j['durations'][0], j['distances'][0], j['sources'][0]['distance'], [d['distance'] for d in j['destinations']]


def main():
    _, fac, _ = acc.load_facilities()
    em = fac[fac['dutyEmcls'].isin(acc.EMERGENCY)].reset_index(drop=True)
    is_ctr = em['dutyEmcls'].isin(acc.CENTER).to_numpy()
    pts = acc.load_centers()
    d = acc.haversine(pts['lat'], pts['lon'], em['wgs84Lat'], em['wgs84Lon'])

    # 기준점마다 직선거리 가까운 응급의료기관 10곳 + 권역·지역센터 10곳 (겹치면 한 번)
    ctr_idx = np.flatnonzero(is_ctr)
    picks = [sorted(set(np.argsort(row)[:TOP]) | set(ctr_idx[np.argsort(row[ctr_idx])[:TOP]])) for row in d]

    def run(i):
        p = pts.iloc[i]
        js = picks[i]
        dur, dist, snap, fsnap = table((p['lat'], p['lon']), [(em.at[j, 'wgs84Lat'], em.at[j, 'wgs84Lon']) for j in js])
        return i, js, dur, dist, snap, fsnap

    rows, snaps, fsnaps = [], [], {}
    with ThreadPoolExecutor(8) as ex:
        for i, js, dur, dist, snap, fsnap in ex.map(run, range(len(pts))):
            pid = pts.at[i, '기준점ID']
            snaps.append({'구분': '기준점', 'ID': pid, '이름': pts.at[i, '지점'], '스냅m': round(snap, 1)})
            far = snap > SNAP_REPORT_M
            for j, t, m, s in zip(js, dur, dist, fsnap):
                fsnaps[em.at[j, 'hpid']] = s
                why = '기준점 도로 스냅 1km 초과' if far else ('도로 미연결' if t is None else '')
                rows.append({'기준점ID': pid, 'hpid': em.at[j, 'hpid'], '직선km': round(d[i, j], 3),
                             '주행시간초': None if far else t, '주행거리m': None if far else m, '미연결사유': why})
    snaps += [{'구분': '기관', 'ID': h, '이름': em.loc[em['hpid'] == h, 'dutyName'].iloc[0], '스냅m': round(s, 1)} for h, s in fsnaps.items()]

    out = pd.DataFrame(rows)
    out.to_csv(PAIRS, index=False, encoding='utf-8-sig')
    s = pd.DataFrame(snaps)
    s.to_csv(SNAP, index=False, encoding='utf-8-sig')

    pp = out.groupby('기준점ID')['주행시간초'].apply(lambda v: v.notna().any())
    print(f'기준점 {len(pts)}곳 × 기관 {len(em)}곳 중 {len(out)}쌍 -> {PAIRS}')
    print(f'도달 불가 쌍 {out["주행시간초"].isna().sum()}개, 모든 기관에 도달 불가한 기준점 {(~pp).sum()}곳')
    far = s[s['스냅m'] > SNAP_REPORT_M].sort_values('스냅m', ascending=False)
    print(f'도로 스냅 {SNAP_REPORT_M}m 초과 {len(far)}곳 -> {SNAP}\n{far.to_string(index=False)}')


if __name__ == '__main__':
    main()
