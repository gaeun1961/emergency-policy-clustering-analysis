"""작은 가짜 데이터로 통합 파이프라인 검증. 실행: python tests/test_pipeline.py"""
import sys
import tempfile
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import population  # noqa: E402
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

        inst = pd.DataFrame({'지역': ['서울특별시', '경기도', '경기도', '세종특별자치시', '경상북도', '부산광역시'],
                             '시군구': ['종로구 ', '수원시', '수원시 권선구', '한누리대로', '군위군', '없는구']})
        write(raw / 'emergency/institutions.csv', inst)
        # 표 형태 통계: 시도 소계 행, 수원시 합계 + 일반구 행, 병합 셀(시도 빈칸)
        write(raw / 'welfare/disabled.csv', pd.DataFrame({
            '시도': ['서울특별시', None, None, '경기도', None, None, '세종특별자치시', '경상북도'],
            '시군구': ['소계', '종로구', '중구', '수원시', '수원시 장안구', '수원시 권선구', '세종시', '군위군'],
            '등록장애인수': ['30', '10', '20', '50', '20', '30', '7', '3']}))
        write(raw / 'accessibility/ngii_emergency_access.csv', pd.DataFrame({
            '시도': ['서울특별시', '서울특별시', '경기도', '경기도', '세종특별자치시', '대구광역시'],
            '시군구': ['종로구', '중구', '수원시 장안구', '수원시 권선구', '세종특별자치시', '군위군'],
            '평균거리': [1.0, 2.0, 3.0, 5.0, 4.0, 9.0]}))
        mapping = d / 'map.csv'
        mapping.write_text('시도,시군구,to_시도,to_시군구\n경상북도,군위군,대구광역시,군위군\n', encoding='utf-8')

        t, unmatched = main(raw, d / 'out', mapping, pop_file, sh_file)

        assert t.loc['11110', '독거노인비율'] == 5 / 30

        assert t['응급의료기관수'].tolist() == [1, 0, 1, 1, 2]  # 일반구 기관은 시로 합산, 군위군은 매핑
        assert t['등록장애인수'].tolist() == [10, 20, 3, 7, 50]  # 소계 제외, 수원시는 합계 행만
        assert t.loc['41110', '응급의료시설_평균접근거리_km'] == 4.0  # 일반구 평균
        assert t.loc['36110', '응급의료시설_평균접근거리_km'] == 4.0
        assert unmatched[['출처', '시군구']].values.tolist() == [['응급의료기관수', '없는구']]


if __name__ == '__main__':
    test_units()
    test_end_to_end()
    print('OK')
