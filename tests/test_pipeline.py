"""작은 가짜 데이터로 통합 파이프라인 검증. 실행: python tests/test_pipeline.py"""
import os
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import accessibility, basic_pension, briefing, disability, emergency_safety, fetch_emergency, population, sensitivity, welfare  # noqa: E402
from src.build_table import main  # noqa: E402
from src.regions import age_start, region_key  # noqa: E402

AGES = ['60~64세', '65~69세', '80~84세', '100세 이상']
HEADER = ['행정기관코드', '행정기관', '총 인구수', '연령구간인구수'] + AGES + ['남 인구수', '연령구간인구수', '65~69세']
SH_HEADER = ['행정기관코드', '행정기관', '총 세대수', '총연령구간세대수'] + AGES + ['남자 세대수', '남자연령구간세대수', '65~69세']


def write(path, df):
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding='cp949')


def write_pop(path, rows, header=HEADER):
    """행안부 형식: 0~2행 안내문, 3행 헤더, 계 블록 뒤에 남 블록(버려야 할 값 999)"""
    path.parent.mkdir(parents=True, exist_ok=True)
    body = [['※ 안내'] + [None] * 10, [None] * 11, [None, None, '계'] + [None] * 8, header]
    body += [[c, n, f'{t:,}', f'{t:,}'] + [f'{a:,}' for a in ages] + ['999', '999', '999'] for c, n, t, ages in rows]
    pd.DataFrame(body).to_excel(path, header=False, index=False)


def test_units():
    assert region_key('경기도', '수원시 장안구') == ('경기', '수원시장안구')
    assert region_key('전라북도', '전주시') == region_key('전북특별자치도', '전주시') == ('전북', '전주시')
    assert region_key('세종특별자치시', '한누리대로 ') == region_key('세종특별자치시', '세종특별자치시') == ('세종', '')
    assert region_key('서울특별시', '소계') is None and region_key('서울특별시', '서울특별시') is None
    assert [age_start(c) for c in ['04세', '6569세', '100세이상', '연령구간인구수', '6세']] == [0, 65, 100, None, None]


def test_end_to_end():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        raw, pop_raw = d / 'raw', d / 'pop'
        # (코드, 행정기관, 총인구, [60~64, 65~69, 80~84, 100+])
        write_pop(pop_raw / '202512_202512_연령별인구현황_서울.xlsx', [
            ('1100000000', '서울특별시', 300, [0, 30, 0, 0]),
            ('1111000000', '서울특별시 종로구', 100, [5, 20, 5, 5]),
            ('1114000000', '서울특별시 중구', 200, [0, 0, 0, 0])])
        write_pop(pop_raw / '202512_202512_연령별인구현황_세종.xlsx', [
            ('3600000000', '세종특별자치시', 100, [0, 50, 0, 0]),
            ('3611000000', '세종특별자치시', 100, [0, 50, 0, 0])])
        write_pop(pop_raw / '202512_202512_연령별인구현황_경기.xlsx', [
            ('4100000000', '경기도', 500, [0, 200, 0, 0]),
            ('4111000000', '경기도 수원시', 500, [0, 150, 40, 10]),
            ('4111100000', '경기도 수원시 장안구', 200, [0, 50, 20, 0]),
            ('4111300000', '경기도 수원시 권선구', 300, [0, 100, 20, 10])])
        write_pop(pop_raw / '202512_202512_연령별인구현황_대구.xlsx', [
            ('2700000000', '대구광역시', 100, [0, 100, 0, 0]),
            ('2772000000', '대구광역시 군위군', 100, [0, 100, 0, 0])])
        write_pop(pop_raw / '202512_202512_연령별인구현황_전국.xlsx', [
            ('0000000000', '전국', 1000, [0] * 4), ('1100000000', '서울특별시', 300, [0] * 4),
            ('3600000000', '세종특별자치시', 100, [0] * 4), ('4100000000', '경기도', 500, [0] * 4),
            ('2700000000', '대구광역시', 100, [0] * 4)])
        population.DATASETS['population']['national_total'] = 1000
        pop_file = d / 'pop.csv'
        units, ok = population.build('population', pop_raw, pop_file)
        assert ok
        assert list(units.index) == ['11110', '11140', '27720', '36110', '41110'], units.index.tolist()
        assert units.loc['41110'].tolist() == ['경기', '수원시', 500, 200, 50]  # 일반구 중복 없이 시 합계
        assert units.loc['11110', ['65세이상인구', '80세이상인구']].tolist() == [30, 10]

        # 1인세대: 같은 규칙, 전국 파일 없으면 ok=False (시도 합계 행으로 대신 검증), 목록 비교
        sh_raw, sh_file = d / 'sh', d / 'sh.csv'
        sh = '202512_202512_행정동별 성연령별 주민등록 1인세대수_'
        write_pop(sh_raw / f'{sh}서울.xlsx', [('1100000000', '서울특별시', 30, [0, 15, 0, 0]),
                                             ('1111000000', '서울특별시 종로구', 10, [0, 5, 0, 0]),
                                             ('1114000000', '서울특별시 중구', 20, [0, 10, 0, 0])], SH_HEADER)
        write_pop(sh_raw / f'{sh}경기.xlsx', [('4100000000', '경기도', 50, [0, 20, 0, 0]),
                                             ('4111000000', '경기도 수원시', 50, [0, 20, 4, 1]),
                                             ('4111100000', '경기도 수원시 장안구', 20, [0, 8, 2, 0]),
                                             ('4111300000', '경기도 수원시 권선구', 30, [0, 12, 2, 1])], SH_HEADER)
        sh_units, ok = population.build('single_household', sh_raw, sh_file, ref_codes=units.index)
        assert not ok  # 전국 파일 없음 + 대구·세종 누락
        assert sh_units.loc['41110'].tolist() == ['경기', '수원시', 50, 25, 5]
        write_pop(sh_raw / f'{sh}대구.xlsx', [('2700000000', '대구광역시', 9, [0] * 4), ('2772000000', '대구광역시 군위군', 9, [0, 6, 0, 0])], SH_HEADER)
        write_pop(sh_raw / f'{sh}세종.xlsx', [('3600000000', '세종특별자치시', 8, [0] * 4), ('3611000000', '세종특별자치시', 8, [0, 5, 0, 0])], SH_HEADER)
        write_pop(sh_raw / f'{sh}전국.xlsx', [('1000000000', '전국', 97, [0] * 4), ('1100000000', '서울특별시', 30, [0] * 4),
                                             ('4100000000', '경기도', 50, [0] * 4), ('2700000000', '대구광역시', 9, [0] * 4),
                                             ('3600000000', '세종특별자치시', 8, [0] * 4)], SH_HEADER)
        sh_units, ok = population.build('single_household', sh_raw, sh_file, ref_codes=units.index)
        assert ok

        # KOSIS 등록장애인: 머리글 3행, 시도 첫 행만, 일반구만 있고 시 합계 없음(띄어쓰기 없음), 세종은 소계만
        dis_raw, dis_file = d / 'dis', d / 'dis.csv'
        dis_raw.mkdir()
        pd.DataFrame([['시군구별(1)', '시군구별(2)', '2025']] * 3 + [
            ['전국', '소계', '90'], ['서울특별시', '소계', '30'], [None, '종로구', '10'], [None, '중구', '20'],
            ['대구광역시', '소계', '3'], [None, '군위군', '3'], ['세종특별자치시', '소계', '7'],
            ['경기도', '소계', '50'], [None, '수원시장안구', '20'], [None, '수원시권선구', '30']],
        ).to_excel(dis_raw / 'dis.xlsx', sheet_name='데이터', header=False, index=False)
        mapping = d / 'map.csv'
        mapping.write_text('시도,시군구,to_시도,to_시군구\n경상북도,군위군,대구광역시,군위군\n', encoding='utf-8')
        disability.NATIONAL_TOTAL = 90
        dis_units, ok = disability.build(dis_raw, dis_file, pop_file, mapping)
        assert ok
        assert dis_units['등록장애인수'].tolist() == [10, 20, 3, 7, 50]

        # 접근성: 주소 -> 시군구(일반구 주소, 군위군 매핑, 세종 도로명), G009 제외, 행정동 기준점 인구가중 평균(수원시 A·B동)
        pd.DataFrame({
            'hpid': list('12345'), 'dutyName': list('abcde'),
            'dutyAddr': ['서울특별시 종로구 x', '경기도 수원시 팔달구 x', '대구광역시 군위군 x', '경상북도 군위군 x', '세종특별자치시 한누리대로 1'],
            'dutyEmcls': ['G001', 'G007', 'G009', 'G007', 'G007'],
            'wgs84Lat': [37.0, 37.2, 36.0, 36.1, 36.5], 'wgs84Lon': [127.0, 127.0, 128.0, 128.0, 127.3], '수집일자': '2026-11-04',
        }).to_csv(d / 'fac.csv', index=False)
        pd.DataFrame({
            '코드': ['1111051500', '1114052000', '2772025000', '3611051000', '4111152000', '4111353000'],
            '시군구코드': ['11110', '11140', '27720', '36110', '41110', '41110'],
            '이름': ['종로구 a동', '중구 b동', '군위군 군위읍', '세종 c동', '수원시 A동', '수원시 B동'],
            '위도': [37.0, 37.0, 36.0, 36.5, 37.2, 37.4], '경도': [127.0, 127.1, 128.0, 127.3, 127.0, 127.0],
            '좌표출처': 'kakao', '장소명': '', '인구': [100, 200, 100, 100, 300, 100],
        }).to_csv(d / 'emd.csv', index=False)
        accessibility.FACILITIES, accessibility.EMD_CENTERS, accessibility.POP_CSV = d / 'fac.csv', d / 'emd.csv', pop_file
        accessibility.MAPPING, accessibility.MOHW_CSV = mapping, d / 'none.csv'
        accessibility.LI_WEIGHTED = d / 'no_li.csv'  # 실제 섬 리 단위 목록을 읽지 않게
        # 주행시간: 군위읍->4 15분(11.12km), 수원 A동->2 1분(0km라 계수 계산 제외), B동->2 20분(22.24km), 세종 c동->5 도달 불가,
        #          종로 a동->1 1분(같은 자리), ->2 60분(근사 상한을 키우는 긴 실주행 값)
        pd.DataFrame({'기준점ID': ['2772025000', '4111152000', '4111353000', '3611051000', '1111051500', '1111051500'],
                      'hpid': ['4', '2', '2', '5', '1', '2'], '직선km': 0, '주행시간초': [900, 60, 1200, None, 60, 3600],
                      '주행거리m': 0}).to_csv(d / 'drive.csv', index=False)
        accessibility.DRIVE_PAIRS = d / 'drive.csv'
        acc_file = d / 'acc.csv'
        a = accessibility.build(acc_file)
        km01 = accessibility.haversine([36.0], [128.0], [36.1], [128.0])[0, 0]  # 위도 0.1도 ≈ 11.12km
        assert abs(km01 - 11.12) < 0.01
        assert a['응급의료기관수'].tolist() == [1, 0, 1, 1, 1]
        assert a.loc['11110', '최근접_응급의료기관_km'] == 0
        assert abs(a.loc['27720', '최근접_응급의료기관_km'] - km01) < 1e-6  # G009(36.0,128.0)는 제외
        assert abs(a.loc['41110', '최근접_응급의료기관_km'] - km01 * 2 * 100 / 400) < 1e-6  # A동 0km×300명, B동 22.24km×100명
        assert a.loc['41110', '기준점방식'] == '행정동 인구가중'
        # 우회계수(분/직선km): 군위 15/11.12, 수원 20/22.24, 나머지는 두 값의 중앙값
        f_gw, f_sw = round(15 / km01, 3), round(20 / (2 * km01), 3)
        assert a.loc['27720', '우회계수_분per직선km'] == f_gw and a.loc['41110', '우회계수_분per직선km'] == f_sw
        assert a.loc['36110', '우회계수_분per직선km'] == round((15 / km01 + 20 / (2 * km01)) / 2, 3)
        assert a.loc['27720', '최근접_응급의료기관_분'] == 15
        assert a.loc['41110', '최근접_응급의료기관_분'] == (1 * 300 + 20 * 100) / 400   # 실주행 쌍이 근사(직선×계수)보다 우선
        assert a.loc['41110', '30분내_응급의료기관수'] == (2 * 300 + 1 * 100) / 400     # A동: 2(1분)·1(22km×계수=20분), B동: 2만
        # 근사값 상한: 실주행 분(15·1·20·1·60)의 99백분위. 세종 c동 -> 센터(종로 G001, 약 62km) 근사값이 상한에 걸림
        cap = round(float(np.percentile([15, 1, 20, 1, 60], 99)), 1)
        km_sj = accessibility.haversine([36.5], [127.3], [37.0], [127.0])[0, 0]
        assert a.loc['36110', '근사상한_분'] == cap
        assert abs(a.loc['36110', '최근접_권역지역센터_분_원값'] - km_sj * a.loc['36110', '우회계수_분per직선km']) < 1e-9
        assert a.loc['36110', '최근접_권역지역센터_분'] == cap < a.loc['36110', '최근접_권역지역센터_분_원값']
        # 근사 반영 인구 비율: 최근접 기관·센터 둘 중 하나라도 근사값이면 1. 종로 a동은 둘 다 실주행(G001 1분)
        assert a.loc['11110', '근사반영_인구비율'] == 0 and a.loc['36110', '근사반영_인구비율'] == 1
        # 이용 기관: 수원(41110) 주민 400명 모두 2번 기관이 최근접 -> 비율 1, 평균 (1×300 + 20×100)/400분
        u = pd.read_csv(d / 'facility_usage.csv', dtype={'행정기관코드': str, 'hpid': str}).set_index(['행정기관코드', '구분'])
        sw = u.loc[('41110', '응급의료기관')]
        assert sw['hpid'] == '2' and sw['주민비율'] == 1 and abs(sw['평균주행분'] - 5.75) < 1e-6
        assert (u.groupby(level=[0, 1])['주민비율'].sum().round(6) == 1).all()

        t = main(d / 'out', pop_file, sh_file, dis_file, acc_file)

        assert t.loc['11110', '독거노인비율'] == 5 / 30
        assert t.loc['11110', '장애인비율'] == 10 / 100
        assert t['응급의료기관수'].tolist() == [1, 0, 1, 1, 1]
        assert not t.isna().any().any()


def test_sfca():
    """2SFCA: 기관0(병상 10)은 두 기준점 모두 30분 안, 기관1(병상 20)은 기준점1만. R0=10/400, R1=20/300"""
    from src.sfca import two_step
    a, r = two_step(np.array([100., 300.]), np.array([10., 20.]), np.array([[10, np.inf], [20, 25]]))
    assert np.allclose(r, [10 / 400, 20 / 300]) and np.allclose(a, [10 / 400, 10 / 400 + 20 / 300])
    a, r = two_step(np.array([100.]), np.array([5.]), np.array([[31.]]))   # 30분 밖이면 공급 0
    assert a[0] == 0 and r[0] == 0


def test_welfare():
    """수급자 비율: 연령·성별·구분 행 합산, 일반구는 상위 시로, 미매칭은 보고, 순위 1 = 비율 가장 높음"""
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        pop = d / 'pop.csv'
        pd.DataFrame({'행정기관코드': ['11110', '41110', '36110'], '시도': ['서울', '경기', '세종'], '시군구': ['종로구', '수원시', ''],
                      '총인구': [1000, 2000, 500]}).to_csv(pop, index=False, encoding='utf-8-sig')
        rows = [('서울특별시', '종로구', '일반수급자', 30), ('서울특별시', '종로구', '일반수급자', 10), ('서울특별시', '종로구', '시설수급자', 10),
                ('경기도', '수원시장안구', '일반수급자', 40), ('경기도', '수원시권선구', '일반수급자', 50), ('경기도', '수원시권선구', '시설수급자', 10),
                ('세종특별자치시', '세종특별자치시', '일반수급자', 5), ('없는도', '없는군', '일반수급자', 7)]
        write(d / 'raw' / '수급자.csv', pd.DataFrame([['202512', s, g, k, '65~69세', '남성', n] for s, g, k, n in rows],
                                                  columns=['통계연월', '통계시도명', '통계시군구명', '수급자구분', '연령구간', '성별', '수급자수']))
        u, ok = welfare.build(raw=d / 'raw', out=d / 'out.csv', pop_csv=pop)
        assert not ok  # 미매칭 '없는도 없는군' 이 있으면 실패로 보고
        assert u.loc['11110', ['일반수급자', '시설수급자', '수급자수']].tolist() == [40, 10, 50]
        assert u.loc['41110', '수급자수'] == 100 and u.loc['36110', '수급자수'] == 5   # 장안구 + 권선구 -> 수원시
        assert u['수급자비율'].round(3).tolist() == [0.05, 0.05, 0.01]
        assert u['수급자비율_순위'].tolist() == [1, 1, 3]
        assert (d / 'out.csv').exists()


def test_briefing_check():
    """AI 브리핑 검증: 사실에 없는 숫자, 잘린 답, 마크다운이면 실패"""
    facts = ['최근접 응급의료기관까지 자동차 주민 평균 44분 (전국 중앙값 6.9분)', '독거노인비율 41.6% (229곳 중 11위)']
    good = '최근접 응급의료기관까지 주민 평균 44분이 걸려 전국 중앙값 6.9분보다 멀다. ' * 3 + '독거노인비율은 41.6%로 229곳 중 11위이며 응급안전안심서비스 확대를 우선 검토할 만하다.'
    assert briefing.check(good, facts) == []
    assert '45' in briefing.check(good.replace('44분', '45분'), facts)            # 지어낸 숫자
    assert briefing.check(good.replace('41.6%', '41.60%'), facts) != []          # 다른 형식의 숫자도 거절
    assert any('끝나지' in b for b in briefing.check(good[:-1], facts))           # 잘린 문장
    assert any('길이' in b for b in briefing.check('44분이다.', facts))
    assert any('마크다운' in b for b in briefing.check('**' + good, facts))


def test_briefing_facts():
    """브리핑 사실(v2): 근사값 주행시간은 '이상(근사)', 기초연금 수급률, 시군구별 1곳 배치 효과(벗어나는 시군구 이름·인구)"""
    import json
    assert briefing.mins_at(38.2, 120.0) == '38분 이상(근사)' and briefing.mins_at(38.2, 38.2) == '38분' and briefing.mins_at(6.9, None) == '6.9분'
    regions = json.loads((briefing.PUB / 'sigungu_metrics.json').read_text(encoding='utf-8'))
    placement = json.loads((briefing.PUB / 'placement_greedy.json').read_text(encoding='utf-8'))
    by = {r['코드']: r for r in regions}
    lines, cands = briefing.facts_for(by['46860'], regions, placement)  # 함평: 시군구 안 1곳으로 이중 취약이 줄어듦
    text = '\n'.join(lines)
    assert '기초연금 수급률' in text and '배치 효과(시뮬레이션)' in text and '(함평군, 영광군)' in text
    assert any('배치 효과' in c for c in cands)
    assert '38분 이상(근사)' in '\n'.join(briefing.facts_for(by['46910'], regions, placement)[0])  # 신안: 섬 근사값


def test_briefing_output():
    """생성된 브리핑이 있으면: 전부 검증 통과, 사실이 지금 데이터와 같음 (데이터가 바뀌면 다시 생성해야 함)"""
    import json
    if not briefing.OUT.exists():
        return
    out = json.loads(briefing.OUT.read_text(encoding='utf-8'))
    regions = json.loads((briefing.PUB / 'sigungu_metrics.json').read_text(encoding='utf-8'))
    placement = json.loads((briefing.PUB / 'placement_greedy.json').read_text(encoding='utf-8'))
    by_code = {r['코드']: r for r in regions}
    for code, b in out['지역'].items():
        assert briefing.check(b['브리핑'], b['사실']) == [], code
        assert b['사실'] == briefing.facts_for(by_code[code], regions, placement)[0], f'{code}: 사실이 지금 데이터와 다름 -> python -m src.briefing'
    assert out == json.loads((briefing.PUB / 'ai_briefing.json').read_text(encoding='utf-8'))


def test_departments_parse():
    """진료과목(dgidIdName): 쉼표로 나누고 공백·빈칸·중복을 빼 가나다순"""
    assert fetch_emergency.parse_departments('정형외과,내과, 내과,,가정의학과 ') == ['가정의학과', '내과', '정형외과']
    assert fetch_emergency.parse_departments(None) == [] and fetch_emergency.parse_departments('') == []


def test_basic_pension():
    """기초연금 수급률: 기준월 행만, '시도 시군구' 나눔, 일반구는 상위 시로, 미매칭 보고, 순위 1 = 가장 높음"""
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        pop = d / 'pop.csv'
        pd.DataFrame({'행정기관코드': ['11110', '41110', '36110'], '시도': ['서울', '경기', '세종'], '시군구': ['종로구', '수원시', ''],
                      '총인구': [1000, 2000, 500]}).to_csv(pop, index=False, encoding='utf-8-sig')
        rows = [('2025-11', '서울특별시 종로구', 999, 1), ('2025-12', '서울특별시 종로구', 100, 50),
                ('2025-12', '경기도 수원시장안구', 100, 30), ('2025-12', '경기도 수원시권선구', 300, 90),
                ('2025-12', '세종특별자치시 세종특별자치시', 200, 160), ('2025-12', '없는도 없는군', 10, 5)]
        write(d / 'raw' / '기초연금.csv', pd.DataFrame([[m, n, a, b, round(b / a * 100, 2)] for m, n, a, b in rows],
                                                    columns=['통계연월', '행정동명', '65세이상 인구수', '수급자수', '수급비율']))
        u, ok = basic_pension.build(raw=d / 'raw', out=d / 'out.csv', pop_csv=pop)
        assert not ok  # 미매칭 '없는도 없는군'
        assert u.loc['11110', ['65세이상인구', '기초연금수급자수']].tolist() == [100, 50]   # 2025-11 행은 안 씀
        assert u.loc['41110', ['65세이상인구', '기초연금수급자수']].tolist() == [400, 120]  # 장안구 + 권선구 -> 수원시
        assert u['기초연금수급률'].round(3).tolist() == [0.5, 0.3, 0.8]
        assert u['기초연금수급률_순위'].tolist() == [2, 3, 1]


def test_service_key():
    """공공데이터포털 키: DATA_GO_KR_SERVICE_KEY 우선, 없으면 KR_SERVICE_KEY, URL 인코딩은 풀어서"""
    saved = {n: os.environ.pop(n, None) for n in fetch_emergency.KEY_NAMES}
    root = fetch_emergency.ROOT
    try:
        with tempfile.TemporaryDirectory() as tmp:
            fetch_emergency.ROOT = Path(tmp)  # 실제 .env 를 읽지 않게
            os.environ['KR_SERVICE_KEY'] = 'a%2Bb'
            assert fetch_emergency.service_key() == 'a+b'
            os.environ['DATA_GO_KR_SERVICE_KEY'] = 'first'
            assert fetch_emergency.service_key() == 'first'
            for n in fetch_emergency.KEY_NAMES:
                del os.environ[n]
            try:
                fetch_emergency.service_key()
                raise AssertionError('키가 없으면 종료해야 함')
            except SystemExit as e:
                assert 'KR_SERVICE_KEY' in str(e)
    finally:
        fetch_emergency.ROOT = root
        for n, v in saved.items():
            os.environ.pop(n, None)
            if v is not None:
                os.environ[n] = v



def test_emergency_safety():
    """응급안전안심서비스: 나이 구간 -> 65세 이상, 나이 결측은 노인에서 빼고 이용자에는 셈, 서비스 공백 = 이중 취약 중 이용률 하위 25%"""
    df = pd.DataFrame({'시도': ['경북'] * 4 + ['전남'], '시군구': ['영덕군'] * 4 + ['신안군'],
                       '나이': ['80세~84세', '60세~64세', '100세 이상', None, '65세~69세']})
    g = emergency_safety.count_users(df).set_index('시군구')
    assert g.loc['영덕군', '이용자'] == 4 and g.loc['영덕군', '노인이용자'] == 2 and g.loc['신안군', '노인이용자'] == 1
    u = pd.DataFrame({'등급': ['이중 취약'] * 4 + ['', '이중 취약'], '이용률': [0.1, 0.2, 0.3, 0.4, 0.05, None]})
    flag, cut = emergency_safety.gaps(u)
    assert flag.tolist() == [True, False, False, False, False, False] and abs(cut - 0.175) < 1e-9  # 해당 없음·자료 없음은 공백 아님
    out = emergency_safety.OUT
    if out.exists():
        r = pd.read_csv(out, dtype={'행정기관코드': str})
        assert len(r) == 229 and r['이용률'].isna().sum() == 28  # 서울 25개 구 + 인천 3곳
        assert r['서비스공백'].sum() > 0 and r.loc[r['서비스공백'], '이용률'].notna().all()  # 공백은 자료가 있는 곳만



def test_sensitivity():
    """민감도: 기본 설정이 기존 이중 취약을 그대로 재현, 기준선을 좁히면 기존의 부분집합, 가중치는 반영됨"""
    pct = sensitivity.load()
    s = pd.read_csv(sensitivity.ROOT / 'outputs' / 'sigungu_scores.csv', dtype={'code': str}).set_index('code').fillna({'등급': ''})
    base = set(s.index[s['등급'] == '이중 취약'])
    assert sensitivity.double(pct) == base
    assert sensitivity.double(pct, top=0.20) <= base <= sensitivity.double(pct, top=0.30)
    assert sensitivity.double(pct, weights={'독거노인비율': 1}) == base


if __name__ == '__main__':
    test_units()
    test_end_to_end()
    test_sfca()
    test_welfare()
    test_briefing_check()
    test_briefing_facts()
    test_briefing_output()
    test_departments_parse()
    test_basic_pension()
    test_emergency_safety()
    test_sensitivity()
    test_service_key()
    print('OK')
