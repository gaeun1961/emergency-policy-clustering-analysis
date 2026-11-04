"""대시보드용 지표 JSON 내보내기

실행: 레포 루트에서 python scripts/export_web_data.py
입력: outputs/sigungu_scores.csv, outputs/double_vulnerable.csv (notebooks/sigungu_clustering.ipynb)
      data/processed/sigungu_table.csv (총인구), data/processed/emergency_facilities.csv (수집일자)
      시뮬레이터용: data/processed/emd_centers.csv (행정동 기준점·인구), emd_li_points.csv (섬 읍·면 리 단위),
      drivetime_pairs.csv (기준점 × 가까운 기관 주행시간, python -m src.drivetime)
출력: web/public/data/sigungu_metrics.json, meta.json
      시뮬레이터용 facilities.json, centers.json, baseline.json
      읍면동 드릴다운용 emd.json (data/processed/emd_metrics.csv·emd_li_metrics.csv, python -m src.emd_metrics)
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src import accessibility  # noqa: E402

OUT = ROOT / 'web' / 'public' / 'data'
FIELDS = {  # 내보낼 이름: 원래 컬럼
    '코드': 'code', '시도': '시도', '시군구': '시군구', '총인구': '총인구', '65세이상인구': '65세이상인구',
    '고령인구비율': '고령인구비율', '독거노인비율': '독거노인비율', '장애인비율': '장애인비율',
    '최근접_응급의료기관_분': '최근접_응급의료기관_분', '최근접_권역지역센터_분': '최근접_권역지역센터_분',
    '30분내_기관수': '30분내_응급의료기관수',
    '최근접_응급의료기관_km': '최근접_응급의료기관_km', '최근접_권역지역센터_km': '최근접_권역지역센터_km',
    '반경30km_기관수': '반경30km_응급의료기관수', '우회계수': '우회계수_분per직선km', '근사반영비율': '근사반영_인구비율',
    '최근접_응급의료기관_분_원값': '최근접_응급의료기관_분_원값', '최근접_권역지역센터_분_원값': '최근접_권역지역센터_분_원값',
    '접근성점수': '접근성취약점수', '복지점수': '복지취약점수', '등급': '등급',
    '클러스터': '클러스터', '클러스터라벨': '유형', '접근성순위': '접근성순위', '복지순위': '복지순위', '합산점수': '합산점수',
    '기준점방식': '기준점방식',  # 행정동 인구가중 / 행정동 인구가중(섬 읍·면은 리 단위)
}
SOURCES = [
    {'이름': '행정안전부 주민등록 인구통계 (연령별 인구현황, 성/연령별 1인세대수)', 'url': 'https://jumin.mois.go.kr', '기준': '2025-12'},
    {'이름': '보건복지부 장애인현황 (KOSIS DT_11761_N009)', 'url': 'https://kosis.kr/statHtml/statHtml.do?orgId=117&tblId=DT_11761_N009', '기준': '2025 연말'},
    {'이름': '국립중앙의료원 응급의료정보조회 서비스 (공공데이터포털 OpenAPI)', 'url': 'https://www.data.go.kr', '기준': None},
    {'이름': '카카오 로컬 API (행정복지센터·리 좌표)', 'url': 'https://developers.kakao.com', '기준': None},
    {'이름': '© OpenStreetMap contributors (ODbL), Geofabrik south-korea 추출본', 'url': 'https://www.openstreetmap.org/copyright', '기준': None},
    {'이름': 'OSRM (Open Source Routing Machine, 자동차 프로필) 주행시간', 'url': 'https://project-osrm.org', '기준': None},
    {'이름': '행정동 경계 vuski/admdongkor ver20251231 (CC BY 4.0)', 'url': 'https://github.com/vuski/admdongkor', '기준': '2025-12-31'},
    {'이름': '통계청 SGIS 행정구역 경계 (admdongkor 원자료)', 'url': 'https://sgis.kostat.go.kr', '기준': None},
]


def main():
    s = pd.read_csv(ROOT / 'outputs' / 'sigungu_scores.csv', dtype={'code': str}).fillna({'시군구': '', '등급': ''})
    dv = pd.read_csv(ROOT / 'outputs' / 'double_vulnerable.csv', dtype={'code': str})[['code', '합산점수']]
    extra = ['총인구', '65세이상인구', '기준점방식', '최근접_응급의료기관_km', '최근접_권역지역센터_km', '반경30km_응급의료기관수',
             '우회계수_분per직선km', '근사반영_인구비율', '최근접_응급의료기관_분_원값', '최근접_권역지역센터_분_원값']  # 점수에 안 쓰는 지표는 통합 테이블에서
    pop = pd.read_csv(ROOT / 'data' / 'processed' / 'sigungu_table.csv', dtype={'code': str})[['code'] + extra]
    df = s.merge(dv, on='code', how='left').merge(pop, on='code', how='left')
    assert len(df) == 229 and df['총인구'].notna().all(), '시군구 229개와 총인구가 모두 있어야 함'

    df = df[list(FIELDS.values())].set_axis(list(FIELDS), axis=1).round(4)
    records = [{k: (None if pd.isna(v) else v) for k, v in r.items()} for r in df.to_dict('records')]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'sigungu_metrics.json').write_text(json.dumps(records, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')

    collected = pd.read_csv(ROOT / 'data' / 'processed' / 'emergency_facilities.csv', usecols=['수집일자'])['수집일자'].iloc[0]
    SOURCES[2]['기준'] = collected
    stamp = ROOT / 'data' / 'processed' / 'osm_timestamp.txt'  # scripts/osrm_setup.sh 가 OSM 추출본 시점을 기록
    SOURCES[6]['기준'] = stamp.read_text(encoding='utf-8').strip()[:10] if stamp.exists() else None
    counts = df['등급'].value_counts()
    meta = {
        '기준시점': {'인구·복지': '2025-12', '응급의료기관': collected, '경계': '2025-12-31 (2026.7 인천·광주전남 개편 이전)'},
        '시군구수': len(df),
        '이중취약수': int(counts.get('이중 취약', 0)),
        '준이중취약수': int(counts.get('준 이중 취약', 0)),
        '클러스터': df.groupby('클러스터')['클러스터라벨'].first().to_dict(),
        '출처': SOURCES,
        '생성일시': datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds'),
    }
    (OUT / 'meta.json').write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f'sigungu_metrics.json {len(records)}개, meta: 이중 {meta["이중취약수"]} / 준 {meta["준이중취약수"]}, '
          f'응급의료기관 수집일 {collected}')
    export_simulation(s)


# 시뮬레이터: 노트북(notebooks/sigungu_clustering.ipynb)과 같은 정의
ACCESS = ['최근접_응급의료기관_분', '최근접_권역지역센터_분', '30분내_응급의료기관수']
REVERSE = ['30분내_응급의료기관수']  # 클수록 좋은 지표 -> 부호 반대
WELFARE = ['고령인구비율', '독거노인비율', '장애인비율']
TOP, NEAR = 0.25, 0.40


def export_simulation(scores):
    """브라우저에서 접근성을 다시 계산하기 위한 기관 좌표·기준점·baseline 분포"""
    _, fac, _ = accessibility.load_facilities()
    fac = fac[fac['dutyEmcls'].isin(accessibility.EMERGENCY)]
    facilities = [{'hpid': r.hpid, '기관명': r.dutyName, '등급': r.dutyEmcls, '위도': r.wgs84Lat, '경도': r.wgs84Lon,
                   '시군구코드': r.행정기관코드, '주소': r.dutyAddr, '응급실전화': r.dutyTel3, '대표전화': r.dutyTel1}
                  for r in fac.itertuples()]

    # 행정동 기준점(섬 읍·면은 리)과 인구 가중치. Python 접근성 계산(src.accessibility.load_centers)과 같은 점·같은 순서
    # drive: 도로로 닿는 가까운 기관의 주행시간(초). 없는 기관은 직선거리 × 시군구 우회계수 (src.accessibility.drive_minutes)
    c = accessibility.load_centers()
    pairs = pd.read_csv(accessibility.DRIVE_PAIRS, dtype={'기준점ID': str, 'hpid': str}).dropna(subset=['주행시간초'])
    drive = {pid: dict(zip(g['hpid'], g['주행시간초'].astype(float))) for pid, g in pairs.groupby('기준점ID')}
    centers = {code: [{'lat': r.lat, 'lon': r.lon, 'weight': float(r.가중치), '지점': r.지점, 'emd': r.기준점ID.split('-')[0],
                       'drive': drive.get(r.기준점ID, {})}
                      for r in g.itertuples()]
               for code, g in c.groupby('행정기관코드', sort=False)}

    # 점수 재현: sigungu_table(접근성 지표는 소수 3자리 반올림 값)의 백분위 순위 평균
    t = pd.read_csv(ROOT / 'data' / 'processed' / 'sigungu_table.csv', dtype={'code': str}).set_index('code')
    t['고령인구비율'] = t['65세이상인구'] / t['총인구']
    X = t[ACCESS + WELFARE].copy()
    X[REVERSE] = -X[REVERSE]  # log1p는 순위를 바꾸지 않아 생략
    pct = X.rank(pct=True) * 100
    acc, wel = pct[ACCESS].mean(axis=1), pct[WELFARE].mean(axis=1)
    cut = {q: (acc.quantile(1 - q), wel.quantile(1 - q)) for q in (TOP, NEAR)}
    grade = np.select([(acc >= cut[TOP][0]) & (wel >= cut[TOP][1]),
                       ((acc >= cut[TOP][0]) & (wel >= cut[NEAR][1])) | ((wel >= cut[TOP][1]) & (acc >= cut[NEAR][0]))],
                      ['이중 취약', '준 이중 취약'], '')
    expected = scores.set_index('code')['등급'].reindex(t.index)
    assert (grade == expected.values).all(), '재현한 등급이 outputs/sigungu_scores.csv와 다름'

    baseline = {
        '설명': '접근성 지표 baseline 분포(소수 3자리). 시뮬레이션 값은 이 분포 기준 백분위로 환산하고 기준선은 고정',
        '지표': {k: t[k].tolist() for k in ACCESS},
        '방향': {k: (-1 if k in REVERSE else 1) for k in ACCESS},
        '기준선': {'상위25': {'접근성': cut[TOP][0], '복지': cut[TOP][1]}, '상위40': {'접근성': cut[NEAR][0], '복지': cut[NEAR][1]}},
        '기준분': accessibility.MINUTES,
        '우회계수': t['우회계수_분per직선km'].to_dict(),  # 분/직선km. 실주행시간이 없는 기관·가상 기관에 쓰는 근사
        '근사상한분': float(t['근사상한_분'].iloc[0]),    # 근사값 상한 (도로로 잰 주행시간 99백분위)
        '코드': t.index.tolist(),
        '접근성점수': acc.tolist(),  # 전체 정밀도 (검증용)
        '복지점수': wel.tolist(),    # 시뮬레이션에서 고정
    }
    for name, obj in [('facilities.json', facilities), ('centers.json', centers), ('baseline.json', baseline)]:
        (OUT / name).write_text(json.dumps(obj, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    export_emd()
    print(f'시뮬레이터: 기관 {len(facilities)}곳, 기준점 {sum(map(len, centers.values()))}개({len(centers)}개 시군구), '
          f'기준선 상위25% 접근성 {cut[TOP][0]:.3f} / 복지 {cut[TOP][1]:.3f}, 등급 재현 일치')


def export_emd():
    """읍면동 드릴다운: 고정값(이름·인구·고령 비율, 섬 리)과 전국 행정동 접근성 점수 분포(웹이 같은 방식으로 다시 계산)"""
    from src.emd_metrics import ACCESS as EMD_ACCESS, BANDS, REVERSE as EMD_REVERSE
    e = pd.read_csv(ROOT / 'data' / 'processed' / 'emd_metrics.csv', dtype={'행정동코드': str, '시군구코드': str})
    li = pd.read_csv(ROOT / 'data' / 'processed' / 'emd_li_metrics.csv', dtype={'행정동코드': str})
    # 구간 경계: CSV 점수(소수 6자리)가 아니라 지표에서 다시 낸 전체 정밀도 점수로 (src.emd_metrics 와 같은 값)
    X = e[EMD_ACCESS].copy()
    X[EMD_REVERSE] = -X[EMD_REVERSE]
    cuts = (X.rank(pct=True) * 100).mean(axis=1).quantile([0.25, 0.5, 0.75]).tolist()
    emd = {
        '설명': '행정동 고정값 [이름, 인구, 고령인구비율]과 섬 리 [인구, 고령인구비율]. 주행시간 지표는 centers.json 기준점(emd)으로 웹이 계산',
        '행정동': {r.행정동코드: [r.이름, int(r.인구), round(r.고령인구비율, 4)] for r in e.itertuples()},
        '리': {c: {r.리: [int(r.인구), round(r.고령인구비율, 4)] for r in g.itertuples()} for c, g in li.groupby('행정동코드')},
        '지표': {k: e[k].round(3).tolist() for k in EMD_ACCESS},   # 전국 행정동 분포 (점수 = 이 분포 기준 백분위 평균)
        '방향': {k: (-1 if k in EMD_REVERSE else 1) for k in EMD_ACCESS},
        '구간': BANDS, '구간경계': cuts,
    }
    (OUT / 'emd.json').write_text(json.dumps(emd, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    print(f'읍면동: 행정동 {len(e)}곳, 섬 리 {len(li)}곳, 구간 경계 {[round(c, 2) for c in cuts]}, '
          f'emd.json {(OUT / "emd.json").stat().st_size / 1e3:.0f}KB')


if __name__ == '__main__':
    main()
