import { geoContains } from 'd3-geo'
import type { SigunguGeo } from '../data'

/** 좌표가 들어 있는 시군구 코드. 바다·경계 밖이면 null (경계는 d3 고리 방향으로 저장돼 있음) */
export function locateSigungu(sigungu: SigunguGeo, lat: number, lon: number): string | null {
  for (const f of sigungu.features) if (geoContains(f, [lon, lat])) return f.properties.code
  return null
}
