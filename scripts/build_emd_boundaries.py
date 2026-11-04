"""대시보드 읍면동 드릴다운용 행정동 경계: 시군구별 파일로 나눠 선택할 때만 불러온다

실행: 레포 루트에서 python scripts/build_emd_boundaries.py   (node·npx 필요, python -m src.emd_metrics 다음)
입력: data/raw/boundary/HangJeongDong_ver20251231.geojson (scripts/build_boundaries.py 가 내려받음)
      data/processed/emd_metrics.csv (행정동 -> 시군구 코드, 일반구는 상위 시)
출력: web/public/data/emd/{시군구코드}.json  행정동 면 (속성 code = 행정동코드). 섬 리는 소속 읍·면 면 안에 있다
"""
import json
import sys
import tempfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from build_boundaries import PRECISION, RAW, mapshaper, rewind_for_d3  # noqa: E402

OUT = ROOT / 'web' / 'public' / 'data' / 'emd'
SIMPLIFY = '40%'  # 시군구 하나만 확대해서 본다. 15%는 작은 구(서울 중구 등)에서 동 경계가 각져 40%로 (합계 3.1MB -> 6.6MB, 선택한 시군구만 불러옴)


def main():
    sgg = pd.read_csv(ROOT / 'data' / 'processed' / 'emd_metrics.csv', dtype={'행정동코드': str, '시군구코드': str})
    sgg_of = dict(zip(sgg['행정동코드'], sgg['시군구코드']))
    src = json.loads(RAW.read_text(encoding='utf-8'))
    feats = []
    for f in src['features']:
        code = f['properties']['adm_cd2']
        f['properties'] = {'code': code, 'sgg': sgg_of.get(code)}
        feats.append(f)
    missing = [f['properties']['code'] for f in feats if f['properties']['sgg'] is None]
    print(f'[매칭] 경계 {len(feats)}개, 지표 {len(sgg_of)}개, 지표 없는 경계 {missing or "없음"}, '
          f'경계 없는 지표 {sorted(set(sgg_of) - {f["properties"]["code"] for f in feats}) or "없음"}')

    with tempfile.TemporaryDirectory() as d:
        tmp, out = Path(d) / 'dong.geojson', Path(d) / 'simple.geojson'
        tmp.write_text(json.dumps({'type': 'FeatureCollection', 'features': [f for f in feats if f['properties']['sgg']]},
                                  ensure_ascii=False), encoding='utf-8')
        # 섬 조각이 사라지지 않게 조각마다 쪼개 단순화하고 다시 합친다 (build_boundaries 와 같은 방식)
        mapshaper(str(tmp), '-explode', '-simplify', SIMPLIFY, 'keep-shapes', '-dissolve', 'code', 'copy-fields=sgg',
                  '-o', str(out), f'precision={PRECISION}', 'format=geojson')
        fc = rewind_for_d3(json.loads(out.read_text(encoding='utf-8')))

    OUT.mkdir(parents=True, exist_ok=True)
    for p in OUT.glob('*.json'):
        p.unlink()
    groups = {}
    for f in fc['features']:
        groups.setdefault(f['properties'].pop('sgg'), []).append(f)
    sizes = []
    for code, fs in groups.items():
        p = OUT / f'{code}.json'
        p.write_text(json.dumps({'type': 'FeatureCollection', 'features': fs}, ensure_ascii=False, separators=(',', ':')),
                     encoding='utf-8')
        sizes.append(p.stat().st_size)
    s = pd.Series(sizes)
    print(f'[출력] {len(groups)}개 파일, 합계 {s.sum() / 1e6:.2f}MB, 파일당 중앙값 {s.median() / 1e3:.0f}KB, 최대 {s.max() / 1e3:.0f}KB -> {OUT}')


if __name__ == '__main__':
    main()
