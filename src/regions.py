"""시군구 이름 정규화와 행정구역 코드(5자리) 매핑

기준 코드표(master)는 행정안전부 주민등록 인구 파일의 행정기관코드에서 만든다.
KOSIS 등 다른 출처는 통계청 코드를 써서 행안부 코드와 다르므로, 코드가 아니라
(시도, 시군구) 이름으로 master에 붙인다.
분석 단위: 일반구(수원시 장안구 등)는 상위 시로 합친다. 일반구 단위 복지 통계가 출처마다 들쭉날쭉해서다.
"""
import re

import pandas as pd

from .loaders import clean_sido_name

SKIP_SGG = {'', 'nan', '계', '소계', '합계', '전체'}


def region_key(sido, sgg):
    """(시도, 시군구) 원본값 -> ('경기', '수원시장안구'). 합계 행은 None."""
    sido_raw = re.sub(r'\s+', '', str(sido))
    sgg = re.sub(r'\s+', '', str(sgg))
    if sgg in SKIP_SGG:
        return None
    sido = clean_sido_name(sido_raw)
    if sido == '세종':  # 시군구가 없는 단층제. 출처마다 '세종시', '세종특별자치시', 도로명 등 제각각
        return ('세종', '')
    if sgg == sido_raw:  # 시도 합계 행
        return None
    return (sido, sgg)


def build_master(pop):
    """행안부 인구 파일(행정기관코드, 행정기관) -> master: code, unit, 시도, 시군구"""
    code = pop['행정기관코드'].astype(str).str.replace(r'\.0$', '', regex=True).str.zfill(10).str[:5]
    names = pop['행정기관'].astype(str).str.split(n=1)
    m = pd.DataFrame({
        'code': code,
        '시도': [clean_sido_name(n[0]) for n in names],
        '시군구': [re.sub(r'\s+', '', n[1]) if len(n) > 1 else '' for n in names],
    }, index=pop.index)
    m = m[m['code'].str[2:] != '000']  # 전국·시도 합계 행 제외 (세종 36110은 남음)

    # 일반구 -> 상위 시 코드
    city_code = dict(zip(zip(m['시도'], m['시군구']), m['code']))
    def unit(row):
        hit = re.fullmatch(r'(.+?시)(.+구)', row['시군구'])
        return city_code.get((row['시도'], hit.group(1)), row['code']) if hit else row['code']
    m['unit'] = m.apply(unit, axis=1)
    return m


def load_mapping(path):
    """매핑 테이블 csv(시도, 시군구, to_시도, to_시군구) -> {원래 key: 바꿀 key}"""
    t = pd.read_csv(path, dtype=str).fillna('')
    return {region_key(a, b): region_key(c, d)
            for a, b, c, d in zip(t['시도'], t['시군구'], t['to_시도'], t['to_시군구'])}


def attach_code(df, master, mapping):
    """df(시도, 시군구 열)에 code, unit을 붙인다. -> (매칭된 df, 매칭 안 된 df)"""
    lookup = {(s, g): (c, u) for s, g, c, u in zip(master['시도'], master['시군구'], master['code'], master['unit'])}
    df = df.copy()
    df['시도'] = df['시도'].ffill()  # 엑셀 병합 셀은 첫 행만 값이 있음
    keys = [region_key(s, g) for s, g in zip(df['시도'], df['시군구'])]
    keys = [mapping.get(k, k) for k in keys]
    df = df[[k is not None for k in keys]]
    hits = [lookup.get(k) for k in keys if k is not None]
    ok = [h is not None for h in hits]
    df['code'] = [h[0] if h else None for h in hits]
    df['unit'] = [h[1] if h else None for h in hits]
    return df[ok], df[[not x for x in ok]].drop(columns=['code', 'unit'])


def rollup(df, col, how, has_subtotals):
    """unit(시군구) 단위로 집계.
    has_subtotals: 표 형태 통계처럼 '수원시' 합계 행과 일반구 행이 같이 있으면 합계 행만 쓴다.
    """
    if has_subtotals:
        df = df[(df['code'] == df['unit']) | ~df['unit'].isin(df['code'])]
        dup = df.loc[df['code'].duplicated(keep=False), ['시도', '시군구', 'code']]
        if len(dup):
            print(f"[경고] 같은 지역이 여러 행이라 합산됨 (중복 집계 확인 필요):\n{dup.to_string()}")
    return df.groupby('unit')[col].agg(how)


def age_start(col):
    """정규화된 연령 컬럼명 -> 시작 나이. '6569세'->65, '100세이상'->100, 그 외 None (5세 단위 전제)"""
    m = re.fullmatch(r'(\d+)세(이상)?', col)
    if not m:
        return None
    d = m.group(1)
    if m.group(2):
        return int(d)
    return int(d[:len(d) // 2]) if len(d) % 2 == 0 else None
