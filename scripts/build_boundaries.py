"""대시보드용 시군구 경계: admdongkor 행정동 -> 기준 코드표 229개 시군구

실행: 레포 루트에서 python scripts/build_boundaries.py   (node·npx 필요, mapshaper는 npx로 받음)
입력: data/raw/boundary/HangJeongDong_{경계 버전}.geojson (없으면 내려받음, gitignore)
      data/processed/population_sigungu_{기준연월}.csv (기준 코드표)   (기준 시점은 src/config.py)
출력: web/public/data/sigungu.geojson (시군구 면), web/public/data/sido.geojson (시도 경계선)

출처: vuski/admdongkor (CC BY 4.0), 원자료 통계청 SGIS 행정구역 경계
"""
import json
import subprocess
import sys
import tempfile
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.config import BOUNDARY_VERSION, YM  # noqa: E402
from src.loaders import clean_sido_name  # noqa: E402
from src.regions import parent_city  # noqa: E402

VERSION = BOUNDARY_VERSION  # 기준 코드표와 같은 시점)
URL = f'https://raw.githubusercontent.com/vuski/admdongkor/master/{VERSION}/HangJeongDong_{VERSION}.geojson'
RAW = ROOT / 'data' / 'raw' / 'boundary' / f'HangJeongDong_{VERSION}.geojson'
POP_CSV = ROOT / 'data' / 'processed' / f'population_sigungu_{YM}.csv'
OUT = ROOT / 'web' / 'public' / 'data'
MAPSHAPER = 'mapshaper@0.7.101'
SIMPLIFY = '10%'  # 남길 꼭짓점 비율
PRECISION = '0.00005'  # 좌표 소수점 (약 5m)
ISLANDS = ['28720', '46910', '46890', '47940', '46900', '50110', '50130']  # 옹진·신안·완도·울릉·진도·제주·서귀포


def load_units():
    import csv
    with open(POP_CSV, encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))
    return {r['행정기관코드']: (r['시도'], r['시군구']) for r in rows}


def unit_code(props, units, by_name):
    """행정동 -> 기준 코드표 시군구 코드. 일반구(수원시장안구 41111 등)는 상위 시로"""
    code = props['adm_cd2'][:5]
    if code in units:
        return code
    key = (clean_sido_name(props['sidonm']), props['sggnm'].replace(' ', ''))
    return by_name.get(parent_city(key))


def rings(geom):
    return len(geom['coordinates']) if geom['type'] == 'MultiPolygon' else 1


def rewind_for_d3(fc):
    """d3-geo는 구면 기준이라 바깥 고리가 시계 방향이어야 한다 (RFC 7946과 반대).
    반시계로 두면 '지구 전체 - 그 지역'으로 그려져 화면이 한 색으로 덮인다."""
    def area(ring):  # 평면 신발끈 공식: 양수면 반시계
        return sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(ring, ring[1:]))

    def fix(poly):
        return [r if (area(r) < 0) == (i == 0) else r[::-1] for i, r in enumerate(poly)]
    for f in fc['features']:
        g = f['geometry']
        g['coordinates'] = [fix(p) for p in g['coordinates']] if g['type'] == 'MultiPolygon' else fix(g['coordinates'])
    return fc


def mapshaper(*args):
    subprocess.run(['npx', '-y', MAPSHAPER, *args], check=True, shell=sys.platform == 'win32')


def main():
    if not RAW.exists():
        RAW.parent.mkdir(parents=True, exist_ok=True)
        print(f'내려받는 중: {URL}')
        urllib.request.urlretrieve(URL, RAW)
    src = json.loads(RAW.read_text(encoding='utf-8'))
    units = load_units()
    by_name = {v: k for k, v in units.items()}

    feats, unmatched = [], Counter()
    for f in src['features']:
        code = unit_code(f['properties'], units, by_name)
        if code is None:
            unmatched[(f['properties']['sidonm'], f['properties']['sggnm'], f['properties']['adm_cd2'][:5])] += 1
            continue
        sido, sgg = units[code]
        f['properties'] = {'code': code, 'sido': code[:2], '시도': sido, '시군구': sgg}
        feats.append(f)

    got = {f['properties']['code'] for f in feats}
    print(f'[매칭] 행정동 {len(src["features"])}개 -> 시군구 {len(got)}개 (기준 코드표 {len(units)}개)')
    print('  경계에 없는 기준 코드:', sorted(set(units) - got) or '없음')
    print('  기준 코드표에 없는 행정동:', dict(unmatched) or '없음')

    OUT.mkdir(parents=True, exist_ok=True)
    sgg_out, sido_out = OUT / 'sigungu.geojson', OUT / 'sido.geojson'
    with tempfile.TemporaryDirectory() as d:
        tmp, full = Path(d) / 'dong.geojson', Path(d) / 'full.geojson'
        tmp.write_text(json.dumps({'type': 'FeatureCollection', 'features': feats}, ensure_ascii=False), encoding='utf-8')
        # 비교 기준: 단순화 없이 시군구로 합친 경계의 섬 조각 수
        mapshaper(str(tmp), '-dissolve', 'code', 'copy-fields=sido,시도,시군구', '-o', str(full), 'format=geojson')
        # keep-shapes는 피처 단위로만 보호해서, 조각(섬)마다 피처로 쪼갠 뒤 단순화하고 다시 합친다
        mapshaper(str(full), '-explode', '-simplify', SIMPLIFY, 'keep-shapes',
                  '-dissolve', 'code', 'copy-fields=sido,시도,시군구', '-o', str(sgg_out), f'precision={PRECISION}', 'format=geojson')
        mapshaper(str(sgg_out), '-dissolve', 'sido', '-innerlines', '-o', str(sido_out), f'precision={PRECISION}',
                  'format=geojson', 'geojson-type=FeatureCollection')
        parts_before = {f['properties']['code']: rings(f['geometry'])
                        for f in json.loads(full.read_text(encoding='utf-8'))['features']}

    out = rewind_for_d3(json.loads(sgg_out.read_text(encoding='utf-8')))
    sgg_out.write_text(json.dumps(out, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    codes = [f['properties']['code'] for f in out['features']]
    parts_after = {f['properties']['code']: rings(f['geometry']) for f in out['features']}
    print(f'\n[결과] 시군구 {len(codes)}개 (중복 {len(codes) - len(set(codes))}개), 기준 코드표와 일치: {set(codes) == set(units)}')
    print(f'  sigungu.geojson {sgg_out.stat().st_size / 1e6:.2f}MB, sido.geojson {sido_out.stat().st_size / 1e6:.2f}MB')
    print(f'[폴리곤 조각 수] 단순화 전 -> 후: 전체 {sum(parts_before.values())} -> {sum(parts_after.values())}')
    for c in ISLANDS:
        print(f'  {c} {units[c][0]} {units[c][1]}: {parts_before[c]} -> {parts_after.get(c)}')
    lost = {f'{units[c][0]} {units[c][1]}': (parts_before[c], parts_after.get(c, 0))
            for c in units if parts_after.get(c, 0) < parts_before[c]}
    print('  조각이 줄어든 시군구:', lost or '없음')
    dokdo = next(f for f in out['features'] if f['properties']['code'] == '47940')['geometry']
    print('  독도 포함:', any(abs(x - 131.866) < 0.02 and abs(y - 37.241) < 0.02
                            for poly in dokdo['coordinates'] for ring in poly for x, y in ring))


if __name__ == '__main__':
    main()
