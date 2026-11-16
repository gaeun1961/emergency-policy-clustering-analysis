"""대시보드용 지표 JSON 내보내기

실행: 레포 루트에서 python scripts/export_web_data.py
입력: outputs/sigungu_scores.csv, outputs/double_vulnerable.csv (notebooks/sigungu_clustering.ipynb)
      data/processed/sigungu_table.csv (총인구), data/processed/emergency_facilities.csv (수집일자)
      시뮬레이터용: data/processed/emd_centers.csv (행정동 기준점·인구), emd_li_points.csv (섬 읍·면 리 단위),
      drivetime_pairs.csv (기준점 × 가까운 기관 주행시간, python -m src.drivetime)
출력: web/public/data/sigungu_metrics.json, meta.json
      시뮬레이터용 facilities.json, centers.json, baseline.json
      2SFCA 보조 지표: data/processed/sfca_sigungu.csv (python -m src.sfca) -> sigungu_metrics.json 의 2SFCA* 필드
      읍면동 드릴다운용 emd.json (data/processed/emd_metrics.csv·emd_li_metrics.csv, python -m src.emd_metrics)
      수급자 비율 참고 지표: data/processed/welfare_rate.csv (python -m src.welfare) -> sigungu_metrics.json 의 수급자비율* 필드
      기초연금 수급률 참고 지표: data/processed/basic_pension_rate.csv (python -m src.basic_pension) -> sigungu_metrics.json 의 기초연금*
      응급안전안심서비스 이용률: data/processed/emergency_safety_rate.csv (python -m src.emergency_safety) -> 응급안전이용률·응급안전순위·서비스공백 (서울 등 자료 없으면 null)
      진료과목 참고 표시: data/processed/emergency_departments.csv (python -m src.fetch_emergency --departments) -> facilities.json 의 진료과목
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
from src.config import BOUNDARY_DATE, BOUNDARY_NOTE, BOUNDARY_VERSION, DISABILITY_YEAR, YM_LABEL  # noqa: E402

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
    {'이름': '행정안전부 주민등록 인구통계 (연령별 인구현황, 성/연령별 1인세대수)', 'url': 'https://jumin.mois.go.kr', '기준': YM_LABEL},
    {'이름': '보건복지부 장애인현황 (KOSIS DT_11761_N009)', 'url': 'https://kosis.kr/statHtml/statHtml.do?orgId=117&tblId=DT_11761_N009', '기준': f'{DISABILITY_YEAR} 연말'},
    {'이름': '복지로 기초생활보장 수급자 통계 (수급자구분·연령·성별, 참고 지표)', 'url': 'https://www.bokjiro.go.kr', '기준': None},
    {'이름': '보건복지부 기초연금 수급 현황 (공공데이터포털 15161618, 참고 지표)', 'url': 'https://www.data.go.kr/data/15161618/fileData.do', '기준': None},
    {'이름': '보건복지부 응급안전안심서비스 대상자 기본정보 (공공데이터포털 15128127, 참고 지표)', 'url': 'https://www.data.go.kr/data/15128127/fileData.do', '기준': None},
    {'이름': '국립중앙의료원 응급의료정보조회 서비스 (공공데이터포털 OpenAPI)', 'url': 'https://www.data.go.kr', '기준': None},
    {'이름': '카카오 로컬 API (행정복지센터·리 좌표)', 'url': 'https://developers.kakao.com', '기준': None},
    {'이름': '© OpenStreetMap contributors (ODbL), Geofabrik south-korea 추출본', 'url': 'https://www.openstreetmap.org/copyright', '기준': None},
    {'이름': 'OSRM (Open Source Routing Machine, 자동차 프로필) 주행시간', 'url': 'https://project-osrm.org', '기준': None},
    {'이름': f'행정동 경계 vuski/admdongkor {BOUNDARY_VERSION} (CC BY 4.0)', 'url': 'https://github.com/vuski/admdongkor', '기준': BOUNDARY_DATE},
    {'이름': '통계청 SGIS 행정구역 경계 (admdongkor 원자료)', 'url': 'https://sgis.kostat.go.kr', '기준': None},
]


def source(prefix):
    """SOURCES 에서 이름이 prefix 로 시작하는 항목 (순서가 바뀌어도 기준 시점이 엉뚱한 출처에 붙지 않게)"""
    return next(x for x in SOURCES if x['이름'].startswith(prefix))


def main():
    s = pd.read_csv(ROOT / 'outputs' / 'sigungu_scores.csv', dtype={'code': str}).fillna({'시군구': '', '등급': ''})
    dv = pd.read_csv(ROOT / 'outputs' / 'double_vulnerable.csv', dtype={'code': str})[['code', '합산점수']]
    extra = ['총인구', '65세이상인구', '기준점방식', '최근접_응급의료기관_km', '최근접_권역지역센터_km', '반경30km_응급의료기관수',
             '우회계수_분per직선km', '근사반영_인구비율', '최근접_응급의료기관_분_원값', '최근접_권역지역센터_분_원값']  # 점수에 안 쓰는 지표는 통합 테이블에서
    pop = pd.read_csv(ROOT / 'data' / 'processed' / 'sigungu_table.csv', dtype={'code': str})[['code'] + extra]
    df = s.merge(dv, on='code', how='left').merge(pop, on='code', how='left')
    assert len(df) == 229 and df['총인구'].notna().all(), '시군구 229개와 총인구가 모두 있어야 함'

    df = df[list(FIELDS.values())].set_axis(list(FIELDS), axis=1).round(4)
    # 2SFCA 보조 지표 (판정·점수에는 쓰지 않음)
    sf = pd.read_csv(ROOT / 'data' / 'processed' / 'sfca_sigungu.csv', dtype={'행정기관코드': str}).fillna({'병상대체기관': ''})
    sf = sf.set_index('행정기관코드').reindex(df['코드'])
    assert sf['2SFCA_병상per10만'].notna().all(), '2SFCA 값이 없는 시군구가 있음 (python -m src.sfca)'
    df['2SFCA'] = sf['2SFCA_병상per10만'].to_numpy()
    df['2SFCA근사비율'] = sf['근사반영_인구비율'].to_numpy()
    df['2SFCA하위25'] = sf['2SFCA_하위25'].astype(bool).to_numpy()
    df['병상대체기관'] = [[x for x in v.split(';') if x] for v in sf['병상대체기관']]
    # 수급자 비율 참고 지표 (판정·점수에는 쓰지 않음)
    wr = pd.read_csv(ROOT / 'data' / 'processed' / 'welfare_rate.csv', dtype={'행정기관코드': str, '기준연월': str}).set_index('행정기관코드').reindex(df['코드'])
    assert wr['수급자비율'].notna().all(), '수급자 비율이 없는 시군구가 있음 (python -m src.welfare)'
    df['수급자비율'] = wr['수급자비율'].round(4).to_numpy()
    df['수급자비율순위'] = wr['수급자비율_순위'].astype(int).to_numpy()
    welfare_ym = wr['기준연월'].iloc[0]
    source('복지로')['기준'] = f'{welfare_ym[:4]}-{welfare_ym[4:]}'
    bp = pd.read_csv(ROOT / 'data' / 'processed' / 'basic_pension_rate.csv', dtype={'행정기관코드': str}).set_index('행정기관코드').reindex(df['코드'])
    assert bp['기초연금수급률'].notna().all(), '기초연금 수급률이 없는 시군구가 있음 (python -m src.basic_pension)'
    df['기초연금수급률'] = bp['기초연금수급률'].round(4).to_numpy()
    df['기초연금순위'] = bp['기초연금수급률_순위'].astype(int).to_numpy()
    source('보건복지부 기초연금')['기준'] = bp['기준연월'].iloc[0]
    # 응급안전안심서비스 이용률 참고 지표 (판정·점수에는 쓰지 않음). 서울·인천 일부는 원본에 없어 null
    es = pd.read_csv(ROOT / 'data' / 'processed' / 'emergency_safety_rate.csv', dtype={'행정기관코드': str}).set_index('행정기관코드').reindex(df['코드'])
    assert es['서비스공백'].notna().all(), '응급안전안심서비스 이용률 파일에 없는 시군구가 있음 (python -m src.emergency_safety)'
    df['응급안전이용률'] = es['이용률'].round(4).to_numpy()
    df['응급안전순위'] = pd.Series([int(v) if pd.notna(v) else None for v in es['이용률_순위']], index=df.index, dtype=object)  # 1위 = 가장 낮음, 정수 유지
    df['서비스공백'] = es['서비스공백'].astype(bool).to_numpy()
    source('보건복지부 응급안전안심서비스')['기준'] = es['기준일'].iloc[0]
    records = [{k: (v if isinstance(v, list) else None if pd.isna(v) else v) for k, v in r.items()} for r in df.to_dict('records')]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'sigungu_metrics.json').write_text(json.dumps(records, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')

    collected = pd.read_csv(ROOT / 'data' / 'processed' / 'emergency_facilities.csv', usecols=['수집일자'])['수집일자'].iloc[0]
    source('국립중앙의료원')['기준'] = collected
    stamp = ROOT / 'data' / 'processed' / 'osm_timestamp.txt'  # scripts/osrm_setup.sh 가 OSM 추출본 시점을 기록
    source('© OpenStreetMap')['기준'] = stamp.read_text(encoding='utf-8').strip()[:10] if stamp.exists() else None
    counts = df['등급'].value_counts()
    meta = {
        '기준시점': {'인구·복지': YM_LABEL, '응급의료기관': collected, '경계': f'{BOUNDARY_DATE} ({BOUNDARY_NOTE})',
                 **({'진료과목': load_departments()[1]} if load_departments()[1] else {})},
        '시군구수': len(df),
        '이중취약수': int(counts.get('이중 취약', 0)),
        '준이중취약수': int(counts.get('준 이중 취약', 0)),
        '클러스터': df.groupby('클러스터')['클러스터라벨'].first().to_dict(),
        '출처': SOURCES,
        '일반구': general_districts(),
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
    # 진료과목 (참고 표시, 계산에는 안 씀): 받은 기관만 목록으로, 진료과목이 비어 있으면 빈 목록
    dept, _ = load_departments()
    for f in facilities:
        if f['hpid'] in dept:
            f['진료과목'] = dept[f['hpid']]

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
    export_access_curve()
    print(f'시뮬레이터: 기관 {len(facilities)}곳, 기준점 {sum(map(len, centers.values()))}개({len(centers)}개 시군구), '
          f'기준선 상위25% 접근성 {cut[TOP][0]:.3f} / 복지 {cut[TOP][1]:.3f}, 등급 재현 일치')


def load_departments():
    """({hpid: [진료과목, ...]}, 기준 'YYYY-MM'). 파일이 없으면 ({}, None)"""
    p = ROOT / 'data' / 'processed' / 'emergency_departments.csv'
    if not p.exists():
        return {}, None
    d = pd.read_csv(p, dtype={'hpid': str, '진료과목': str}, keep_default_na=False)
    return {h: [x for x in v.split(';') if x] for h, v in zip(d['hpid'], d['진료과목'])}, d['수집일자'].max()[:7]


def general_districts():
    """상위 시로 합친 일반구 목록 [[시도, '수원시 장안구', 상위 시 코드], ...] (검색 안내용, 행정동 기준점 이름에서)"""
    import re
    c = pd.read_csv(ROOT / 'data' / 'processed' / 'emd_centers.csv', dtype={'시군구코드': str})
    out = set()
    for name, code in zip(c['이름'], c['시군구코드']):
        sido, sgg = name.split()[:2]
        if hit := re.fullmatch(r'(.+?시)(.+구)', sgg):
            out.add((sido, f'{hit.group(1)} {hit.group(2)}', code))
    return [list(x) for x in sorted(out)]


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



def export_access_curve(max_min=60):
    """분포 탭 누적 인구 곡선: 최근접 응급의료기관까지 N분 안에 사는 주민 비율 (행정동 인구가중, 등급 그룹별).
    행정동 지표는 emd_metrics.csv (시뮬레이션 미반영 현재 값). 섬 등 근사값은 상한값 그대로"""
    e = pd.read_csv(ROOT / 'data' / 'processed' / 'emd_metrics.csv', dtype={'행정동코드': str, '시군구코드': str})
    grade = {r['코드']: r['등급'] for r in json.loads((OUT / 'sigungu_metrics.json').read_text(encoding='utf-8'))}
    assert e['시군구코드'].isin(list(grade)).all(), '행정동의 시군구코드가 시군구 목록에 없음'
    e['등급'] = e['시군구코드'].map(grade)
    groups = {'전국': e, '이중 취약': e[e['등급'] == '이중 취약'], '준 이중 취약': e[e['등급'] == '준 이중 취약'], '해당 없음': e[e['등급'] == '']}
    mins = list(range(0, max_min + 1))
    curve = {name: [round(float(g.loc[g['최근접_응급의료기관_분'] <= m, '인구'].sum() / g['인구'].sum()), 4) for m in mins]
             for name, g in groups.items()}
    out = {'설명': f'최근접 응급의료기관까지 자동차 N분 안에 사는 주민 비율 (행정동 {len(e)}곳 인구가중, 0~{max_min}분, 시뮬레이션 미반영)',
           '분': mins, '비율': curve, '인구': {name: int(g['인구'].sum()) for name, g in groups.items()}}
    (OUT / 'access_curve.json').write_text(json.dumps(out, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    print('누적 곡선: 30분 안 주민 ' + ', '.join(f"{k} {v[30]:.1%}" for k, v in curve.items()))


if __name__ == '__main__':
    main()
