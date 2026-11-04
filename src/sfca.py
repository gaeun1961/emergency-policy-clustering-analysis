"""2SFCA 응급의료 접근성 (추가 지표, 기존 접근성 점수·등급은 그대로)

실행: 레포 루트에서 python -m src.sfca   (python -m src.accessibility, src.fetch_emergency --capacity, src.drivetime --radius 40 다음)
입력: data/processed/drivetime_radius40.csv: 기준점 × 직선 40km 이내 기관 주행시간 (30분 도달은 직선 33km 이내라 충분)
      data/processed/emergency_capacity.csv: 응급실 병상 수 (없거나 0이면 등급별 중앙값)
      기준점(src.accessibility.load_centers, 행정동·섬 리, 인구), 시군구 우회계수(accessibility_sigungu.csv)
출력: data/processed/sfca_sigungu.csv, sfca_emd.csv (지수와 근사 반영 비율), sfca_facility.csv (기관별 공급 비율)

2SFCA (Luo & Wang 2003), 통행권 = 자동차 30분
  1단계 기관 j: R_j = 병상_j / (j 에서 30분 안 기준점 인구 합)
  2단계 기준점 i: A_i = Σ (i 에서 30분 안 기관의 R_j)   -> 인구 10만 명당 응급실 병상으로 표시
  행정동·시군구 지수 = 기준점 A_i 의 인구가중 평균
주행시간: 실주행값, 도로로 닿지 않는 쌍(연륙 안 된 섬, 스냅 1km 초과)은 직선거리 × 시군구 우회계수 근사(기존 규칙).
  근사로 30분 안에 든 쌍이 있는 기준점은 근사 반영으로 표시 (해상 이동 미반영이라 실제보다 좋게 나올 수 있음)
"""
import numpy as np
import pandas as pd

from . import accessibility as acc

PAIRS = acc.PROC / 'drivetime_radius40.csv'
CAPACITY = acc.PROC / 'emergency_capacity.csv'
CATCHMENT = 30   # 분
PER = 100_000    # 인구 10만 명당


def two_step(pop, supply, t, catchment=CATCHMENT):
    """pop (n,), supply (m,), t (n, m) 분(없으면 inf) -> (A (n,), R (m,)). 30분 안에 인구가 없는 기관은 R=0"""
    within = t <= catchment
    demand = within.T.astype(float) @ pop
    r = np.divide(supply, demand, out=np.zeros_like(supply, dtype=float), where=demand > 0)
    return within.astype(float) @ r, r


def main():
    _, fac, _ = acc.load_facilities()
    em = fac[fac['dutyEmcls'].isin(acc.EMERGENCY)].reset_index(drop=True)
    pts = acc.load_centers().reset_index(drop=True)
    pts['행정동코드'] = pts['기준점ID'].str.split('-').str[0]

    # 공급: 응급실 병상. 없거나 0이면 같은 등급 중앙값 (권역 > 지역센터 > 지역기관 순으로 큼)
    cap = pd.read_csv(CAPACITY, dtype={'hpid': str}).set_index('hpid')['응급실병상수']
    beds = em['hpid'].astype(str).map(cap)
    known = beds.notna() & (beds > 0)
    med = beds[known].groupby(em.loc[known, 'dutyEmcls']).median()
    em['병상'] = beds.where(known, em['dutyEmcls'].map(med))
    em['병상출처'] = np.where(known, '응급실 병상', '등급 중앙값')

    # 주행시간 행렬: 40km 밖은 30분 밖(inf). 실주행 없음 -> 직선 × 우회계수 근사
    p = pd.read_csv(PAIRS, dtype={'기준점ID': str, 'hpid': str, '미연결사유': str})
    row = pd.Series(range(len(pts)), index=pts['기준점ID'])
    col = pd.Series(range(len(em)), index=em['hpid'].astype(str))
    p = p[p['hpid'].isin(col.index)]
    ri, ci = row[p['기준점ID']].to_numpy(), col[p['hpid']].to_numpy()
    factor = pd.read_csv(acc.OUT, dtype={'행정기관코드': str}).set_index('행정기관코드')['우회계수_분per직선km']
    approx_min = p['직선km'].to_numpy() * factor.reindex(pts['행정기관코드'].to_numpy()[ri]).to_numpy()
    real = p['주행시간초'].notna().to_numpy()
    t = np.full((len(pts), len(em)), np.inf)
    t[ri, ci] = np.where(real, p['주행시간초'].to_numpy() / 60, approx_min)
    approx = np.zeros(t.shape, bool)
    approx[ri, ci] = ~real

    a, r = two_step(pts['가중치'].to_numpy(float), em['병상'].to_numpy(float), t)
    pts['지수'] = a * PER
    pts['근사반영'] = (approx & (t <= CATCHMENT)).any(axis=1).astype(float)
    pts['30분내기관수'] = (t <= CATCHMENT).sum(axis=1)

    def by(group):
        w = pts['가중치']
        g = pts[['지수', '근사반영', '30분내기관수']].mul(w, axis=0).groupby(pts[group]).sum().div(w.groupby(pts[group]).sum(), axis=0)
        return g.rename(columns={'지수': '2SFCA_병상per10만', '근사반영': '근사반영_인구비율', '30분내기관수': '30분내_기관수'})

    sgg = by('행정기관코드').round(4)
    sgg.index.name = '행정기관코드'
    # 하위 25%: 소수 4자리 값 기준 (웹이 같은 값으로 다시 판정, pandas quantile = 웹 quantile)
    sgg['2SFCA_하위25'] = sgg['2SFCA_병상per10만'] <= sgg['2SFCA_병상per10만'].quantile(0.25)
    # 주민 30분 안에 병상을 등급 중앙값으로 대체한 기관이 있으면 이름 (웹 안내용)
    sub = np.flatnonzero(em['병상출처'].to_numpy() == '등급 중앙값')
    reach = pd.DataFrame(t[:, sub] <= CATCHMENT, columns=em.loc[sub, 'dutyName']).groupby(pts['행정기관코드'].to_numpy()).any()
    sgg['병상대체기관'] = reach.apply(lambda r: ';'.join(r.index[r]), axis=1).reindex(sgg.index).fillna('')
    sgg.to_csv(acc.PROC / 'sfca_sigungu.csv', encoding='utf-8-sig')
    emd = by('행정동코드')
    emd.index.name = '행정동코드'
    emd.round(4).to_csv(acc.PROC / 'sfca_emd.csv', encoding='utf-8-sig')
    em.assign(공급비율per10만=r * PER)[['hpid', 'dutyName', 'dutyEmcls', '병상', '병상출처', '공급비율per10만']].round(4).to_csv(
        acc.PROC / 'sfca_facility.csv', index=False, encoding='utf-8-sig')

    print(f'[공급] 기관 {len(em)}곳, 응급실 병상 {int(known.sum())}곳 실제·{int((~known).sum())}곳 등급 중앙값 {med.to_dict()}, 병상 합 {em["병상"].sum():,.0f}')
    print(f'[2SFCA] 시군구 지수(인구 10만 명당 30분 내 응급실 병상) 중앙값 {sgg.iloc[:, 0].median():.1f}, '
          f'0인 시군구 {(sgg.iloc[:, 0] == 0).sum()}곳, 근사 반영 시군구 {(sgg["근사반영_인구비율"] > 0).sum()}곳')
    compare(sgg)
    return sgg


def compare(sgg):
    """기존 접근성 점수·등급과 비교 (README 표용 출력)"""
    s = pd.read_csv(acc.ROOT / 'outputs' / 'sigungu_scores.csv', dtype={'code': str}).set_index('code').fillna({'등급': '', '시군구': ''})
    x = s.join(sgg)
    name = (x['시도'] + ' ' + x['시군구']).str.strip()
    v = x['2SFCA_병상per10만']
    low = v <= v.quantile(0.25)                                   # 2SFCA 하위 25% (공급이 적은 쪽)
    acc_top = x['접근성취약점수'] >= x['접근성취약점수'].quantile(0.75)  # 기존 접근성 상위 25% (취약)
    rho = x['접근성취약점수'].rank().corr((-v).rank())               # 스피어만: 2SFCA 낮을수록 취약 방향으로 맞춤
    dd = x['등급'] == '이중 취약'
    print(f'[비교] 스피어만 순위 상관(접근성 취약 점수 vs 2SFCA 낮은 순) {rho:.3f}, 2SFCA 하위 25% 경계 {v.quantile(0.25):.1f}')
    print(f'  이중 취약 {dd.sum()}곳 중 2SFCA 하위 25%: {(dd & low).sum()}곳. 아닌 곳: {sorted(name[dd & ~low])}')
    only = low & ~acc_top
    print(f'  2SFCA로만 취약(2SFCA 하위 25%, 기존 접근성 상위 25% 아님) {only.sum()}곳:')
    print(x.loc[only, ['시도', '시군구', '등급', '접근성취약점수']].assign(**{'2SFCA': v[only].round(1)}).sort_values('2SFCA').to_string())


if __name__ == '__main__':
    main()
