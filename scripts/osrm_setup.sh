#!/usr/bin/env bash
# 로컬 OSRM(자동차) 준비: Geofabrik south-korea pbf -> MLD 전처리 -> 서버 실행
# 실행: WSL(Docker Engine)에서  bash scripts/osrm_setup.sh [serve]
#   인자 없으면 내려받기·전처리만, serve 면 이어서 localhost:5000 에 osrm-routed 실행(포그라운드)
# 파일은 레포 밖 OSRM_DIR(기본 ~/osrm)에 둔다. 데몬이 꺼져 있으면: sudo service docker start
set -euo pipefail
IMAGE=ghcr.io/project-osrm/osrm-backend:v6.0.0
DIR=${OSRM_DIR:-$HOME/osrm}
PBF=south-korea-latest.osm.pbf
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$DIR" && cd "$DIR"

docker info >/dev/null 2>&1 || { echo 'Docker 데몬이 꺼져 있음: sudo service docker start'; exit 1; }
if [ ! -f "$PBF" ]; then
  curl -fL -R -o "$PBF" "https://download.geofabrik.de/asia/$PBF"
  curl -fsL "https://download.geofabrik.de/asia/$PBF.md5" | md5sum -c -
fi
# 내려받은 pbf 기준 시점(curl -R 로 보존한 서버 수정 시각)을 레포에 기록 -> export_web_data.py 출처 표기
REPO=$(dirname "$SCRIPT_DIR")
date -u -r "$PBF" +%Y-%m-%dT%H:%M:%SZ > "$REPO/data/processed/osm_timestamp.txt"

base=${PBF%.osm.pbf}
if [ ! -f "$base.osrm.mldgr" ]; then
  docker run --rm -t -v "$DIR:/data" "$IMAGE" osrm-extract -p /opt/car.lua "/data/$PBF"
  docker run --rm -t -v "$DIR:/data" "$IMAGE" osrm-partition "/data/$base.osrm"
  docker run --rm -t -v "$DIR:/data" "$IMAGE" osrm-customize "/data/$base.osrm"
fi

if [ "${1:-}" = serve ]; then
  # table 요청 크기 제한을 넉넉히 (기본 100)
  exec docker run --rm --name osrm -p 5000:5000 -v "$DIR:/data" "$IMAGE" \
    osrm-routed --algorithm mld --max-table-size 10000 "/data/$base.osrm"
fi
