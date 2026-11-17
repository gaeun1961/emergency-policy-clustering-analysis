"""생성형 AI(Gemini) 지역 정책 브리핑: 시군구마다 취약 원인과 우선 검토할 서비스를 담당자용 문단으로

AI 에는 그 지역의 사실(지표 값을 미리 문자열로 만든 것)만 주고, 결과의 모든 숫자가 사실 안에 있는지 대조한다.
어긋나면 다시 생성하고(최대 3번), 끝내 어긋나면 그 지역은 싣지 않는다. 판정·점수에는 쓰지 않는다.

실행: 레포 루트에서 python -m src.briefing [--only 47770,46820] [--fresh]
입력: web/public/data/sigungu_metrics.json, placement_greedy.json (python scripts/export_web_data.py, cd web && npm run placement 뒤)
      .env 의 GEMINI_API_KEY (값은 출력·저장하지 않는다)
출력: data/processed/ai_briefing.json, web/public/data/ai_briefing.json (같은 내용, 이미 만든 지역은 건너뛰어 이어서 생성)
"""
import argparse
import json
import os
import re
import statistics
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUB = ROOT / 'web' / 'public' / 'data'
OUT = ROOT / 'data' / 'processed' / 'ai_briefing.json'
MODEL = 'gemini-3.5-flash-lite'  # 무료 등급: 3.5-flash 는 하루 20회라 229곳 불가, 3.8·3.7 은 혼잡(2026-11). lite 도 같은 검증을 통과
PROMPT_VERSION = 3  # 3: 한 문단 -> 짧은 세 줄(핵심·우선 서비스·배치 제안). 2: 배치 효과·기초연금 사실, 근사 주행시간 표시
URL = f'https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent'
# 화면에 보일 항목 이름 -> 모델 응답 JSON 키
PARTS = {'핵심': 'core', '우선 서비스': 'service', '배치 제안': 'placement'}

INSTRUCTION = """너는 지자체 복지·보건 정책 담당자가 10초 안에 읽을 시군구 브리핑을 쓴다.
규칙:
1. 아래 [사실]에 있는 숫자만, 적힌 그대로 쓴다. 계산·반올림·추정·새 통계·비교 배수를 만들지 않는다.
2. 사실에 없는 기관명, 사업명, 정책, 원인을 지어내지 않는다.
3. 세 항목을 JSON 으로 쓴다. 항목마다 한 문장, 40~100자, "~다."로 끝나는 보고서 문체. 마크다운·줄바꿈 없음.
   - core: 판정(등급)과 가장 두드러진 취약 원인 지표 1~2개를 숫자와 함께. 순위(몇 곳 중 몇 위)는 쓰지 않는다.
   - service: [검토 후보]에서 1~2개를 고르고 근거 숫자 1개를 붙인다. core 에 쓴 숫자는 다시 쓰지 않는다. 후보가 없으면 "현재 지표로는 우선 검토할 서비스가 두드러지지 않는다."
   - placement: [사실]의 "배치 효과(시뮬레이션)" 중 이중 취약에서 벗어나는 시군구가 더 많은 것 하나의 위치와 효과. 벗어나는 시군구가 1곳이면 "OO군이 이중 취약에서 벗어난다", 여러 곳이면 "OO군, OO군 N곳이 이중 취약에서 벗어난다"처럼 이름과 함께, 0곳이면 주행시간이 줄어드는 인구를 쓴다. 반드시 배치 효과 사실의 위치 이름과 숫자를 쓰고, "후보가 없다"고 쓰지 않는다. 퍼센트는 "%" 기호로, "이상(근사)"이 붙은 시간과 기관 종류 이름(예: 응급의료기관·센터)은 [사실]의 표기 그대로 쓴다."""
SCHEMA = {'type': 'OBJECT', 'properties': {k: {'type': 'STRING'} for k in PARTS.values()}, 'required': list(PARTS.values())}

pct = lambda v: f'{v * 100:.1f}%'
mins = lambda v: f'{v:.0f}분' if v >= 10 else f'{v:.1f}분'


def mins_at(v, raw):
    """근사값 상한에 걸린 주행시간은 '38분 이상(근사)' (대시보드의 '≥ 38분 (근사)'와 같은 뜻)"""
    return f'{mins(v)} 이상(근사)' if raw is not None and raw > v + 1e-3 else mins(v)


def rank(values, v):
    """큰 값이 1위 (가장 취약한 쪽)"""
    return 1 + sum(x > v for x in values)


def facts_for(r, regions, placement):
    """그 지역의 사실 줄들과, AI 가 고를 수 있는 서비스 후보"""
    n = len(regions)
    col = lambda k: [x[k] for x in regions]
    med = lambda k: statistics.median(col(k))
    name = f"{r['시도']} {r['시군구']}".strip()
    grade = r['등급'] or '해당 없음'
    lines = [
        f"지역: {name} (전국 시군구 {n}곳, 기준 2025년 12월)",
        f"판정: {grade} (응급의료 접근성 취약 {n}곳 중 {r['접근성순위']}위, 복지 취약 {n}곳 중 {r['복지순위']}위, 1위가 가장 취약)",
        f"유형: {r['클러스터라벨']}",
        f"최근접 응급의료기관까지 자동차 주민 평균 {mins_at(r['최근접_응급의료기관_분'], r.get('최근접_응급의료기관_분_원값'))} (전국 중앙값 {mins(med('최근접_응급의료기관_분'))})",
        f"최근접 권역·지역응급의료센터까지 {mins_at(r['최근접_권역지역센터_분'], r.get('최근접_권역지역센터_분_원값'))} (전국 중앙값 {mins(med('최근접_권역지역센터_분'))})",
        f"30분 내 응급의료기관 주민 평균 {r['30분내_기관수']:.1f}곳",
        f"고령인구비율 {pct(r['고령인구비율'])} ({n}곳 중 {rank(col('고령인구비율'), r['고령인구비율'])}위)",
        f"독거노인비율 {pct(r['독거노인비율'])} ({n}곳 중 {rank(col('독거노인비율'), r['독거노인비율'])}위)",
        f"장애인비율 {pct(r['장애인비율'])} ({n}곳 중 {rank(col('장애인비율'), r['장애인비율'])}위)",
        f"기초생활수급자 비율 {pct(r['수급자비율'])} ({n}곳 중 {r['수급자비율순위']}위)",
        f"기초연금 수급률(65세 이상 중 수급자) {pct(r['기초연금수급률'])} ({n}곳 중 {r['기초연금순위']}위)",
        f"응급실 병상(2SFCA) 인구 10만 명당 {r['2SFCA']:.1f}병상 (적은 순 {n}곳 중 {1 + sum(x < r['2SFCA'] for x in col('2SFCA'))}위)",
    ]
    if r['근사반영비율'] >= 0.05:
        lines.append(f"도로로 닿지 않는 섬 등 근사값을 쓰는 주민 {pct(r['근사반영비율'])} (실제 이동은 더 오래 걸릴 수 있음)")
    for kind, label in (('G006', '지역응급의료센터'), ('G007', '지역응급의료기관')):
        for i, s in enumerate(placement['plans'][kind]['steps']):
            if r['코드'] in s['escaped']:
                lines.append(f"순차 배치 추천: {label}{'을' if label.endswith('관') else '를'} {i + 1}곳째 추가하면 이중 취약에서 벗어남")
                break
    # 시군구별 최적 1곳 (그 시군구 안 후보, simulate 로 확인한 값, placement_greedy.json 의 시군구별)
    names = {x['코드']: (x['시군구'] or x['시도']) for x in regions}
    effect = False
    for kind, label in (('G006', '지역응급의료센터'), ('G007', '지역응급의료기관')):
        b = placement.get('시군구별', {}).get(kind, {}).get(r['코드'])
        if not b:
            continue
        where = f"{b['label']}을(를) 지역응급의료센터로 승격하면" if b['kind'] == 'upgrade' else f"시군구 안 {b['label']}에 {label} 1곳을 두면"
        esc = f" ({', '.join(names[c] for c in b['escaped'])})" if b['escaped'] else ''
        lines.append(f"배치 효과(시뮬레이션): {where} 이중 취약에서 벗어나는 시군구 {len(b['escaped'])}곳{esc}, "
                     f"주변 포함 최근접 응급의료기관·센터 주행시간이 줄어드는 인구 {b['popImproved']:,}명")
        effect = effect or bool(b['escaped'])

    top = lambda k, v=None: rank(col(k), r[k] if v is None else v) <= n // 4  # 상위 25%
    cands = []
    if top('독거노인비율') or top('고령인구비율'):
        cands.append('응급안전안심서비스 확대 (독거노인·고령 비율이 높음)')
    if r['접근성순위'] <= n // 4:
        cands.append('응급의료기관 지정·지원 또는 응급 이송 체계 점검 (응급의료 접근성 취약)')
    if top('장애인비율'):
        cands.append('장애인 응급 상황 지원 강화 (장애인 비율이 높음)')
    if r['수급자비율순위'] <= n // 4:
        cands.append('기초생활수급 가구 사례관리 연계 (수급자 비율이 높음)')
    if 1 + sum(x < r['2SFCA'] for x in col('2SFCA')) <= n // 4:
        cands.append('응급실 병상 확충 검토 (30분 내 병상이 적음)')
    if effect:
        cands.append('시군구 안 응급의료기관 신설·지정 검토 (배치 효과: 이중 취약 시군구가 줄어듦)')
    return lines, cands


NUM = re.compile(r'\d+(?:[.,]\d+)*')


def numbers(text):
    return {m.replace(',', '') for m in NUM.findall(text)}


def check(text, facts, lo=20, hi=130):
    """한 줄 검증 실패 사유 목록 (비면 통과): 사실에 없는 숫자, 잘렸거나 형식이 다른 답"""
    bad = sorted(numbers(text) - numbers('\n'.join(facts)))
    if not lo <= len(text) <= hi:
        bad.append(f'길이 {len(text)}자')
    if not text.endswith('다.'):
        bad.append('문장이 끝나지 않음')
    if re.search(r'[*#\n]', text) or not text[:1].isalnum():
        bad.append('마크다운·줄바꿈')
    return bad


def check_parts(parts, facts):
    """세 줄 브리핑 검증: 항목이 모두 있고 줄마다 check 통과"""
    if not isinstance(parts, dict) or list(parts) != list(PARTS):
        return ['항목 누락']
    bad = [f'{k}: {b}' for k, v in parts.items() for b in check(v, facts)]
    bad += [f'{k}: 퍼센트 표기' for k, v in parts.items() if '퍼센트' in v]
    effect = [l for l in facts if l.startswith('배치 효과')]
    # 배치 위치 이름(시군구 안 OO면에 / OO병원을(를) 승격하면)이 하나라도 들어가야 사실을 쓴 것
    places = [g for l in effect for m in [re.search(r'시군구 안 (\S+)에 |: (\S.*?)을\(를\)', l)] if m for g in m.groups() if g]
    if effect and not any(p in parts['배치 제안'] for p in places):
        bad.append('배치 제안: 배치 효과 사실을 쓰지 않음')
    return bad


def generate(key, lines, cands, session):
    prompt = '[사실]\n' + '\n'.join(f'- {l}' for l in lines) + '\n\n[검토 후보]\n' + ('\n'.join(f'- {c}' for c in cands) or '- 없음')
    body = {'systemInstruction': {'parts': [{'text': INSTRUCTION}]}, 'contents': [{'role': 'user', 'parts': [{'text': prompt}]}],
            'generationConfig': {'temperature': 0.2, 'maxOutputTokens': 8192,  # 생각(thinking) 토큰도 이 안에서 써서 넉넉히
                                 'responseMimeType': 'application/json', 'responseSchema': SCHEMA}}
    import requests
    for attempt in range(6):
        try:
            r = session.post(URL, headers={'x-goog-api-key': key}, json=body, timeout=90)
        except requests.RequestException as e:  # 메시지에 키는 없지만 URL 도 넣지 않는다
            print(f'  요청 실패({type(e).__name__}), 다시 시도', flush=True)
            time.sleep(min(15 * 2 ** attempt, 120))
            continue
        if r.status_code == 429 and 'per day' in r.text:
            raise SystemExit('Gemini 일일 요청 한도에 걸림: 지금까지 만든 것은 저장됨, 한도가 풀린 뒤 다시 실행하면 이어서 생성')
        if r.status_code in (429, 500, 503):
            wait = min(15 * 2 ** attempt, 120)  # 분당 제한·혼잡: 기다렸다 다시
            print(f'  HTTP {r.status_code}, {wait}초 뒤 다시', flush=True)
            time.sleep(wait)
            continue
        if not r.ok:
            raise RuntimeError(f'Gemini HTTP {r.status_code}: {r.json().get("error", {}).get("status", "")}')  # 키·URL 은 넣지 않는다
        cand = r.json()['candidates'][0]
        if cand.get('finishReason') != 'STOP':  # 길이 제한 등으로 잘린 답은 버린다 (check_parts 에서 다시 생성)
            return None
        try:
            raw = json.loads(''.join(p.get('text', '') for p in cand['content']['parts'] if not p.get('thought')))
        except ValueError:
            return None
        return {label: str(raw.get(key, '')).strip() for label, key in PARTS.items()}
    raise RuntimeError('Gemini 요청이 계속 제한됨 (잠시 뒤 다시 실행하면 이어서 생성)')


def main():
    import requests
    from dotenv import load_dotenv
    ap = argparse.ArgumentParser()
    ap.add_argument('--only', help='쉼표로 구분한 시군구 코드만')
    ap.add_argument('--fresh', action='store_true', help='이미 만든 것도 다시 생성')
    a = ap.parse_args()
    load_dotenv(ROOT / '.env')
    key = os.getenv('GEMINI_API_KEY')
    if not key:
        sys.exit('.env 또는 환경변수에 GEMINI_API_KEY 가 없음')

    regions = json.loads((PUB / 'sigungu_metrics.json').read_text(encoding='utf-8'))
    placement = json.loads((PUB / 'placement_greedy.json').read_text(encoding='utf-8'))
    done = {} if a.fresh or not OUT.exists() else json.loads(OUT.read_text(encoding='utf-8'))['지역']
    order = {'이중 취약': 0, '준 이중 취약': 1, '': 2}  # 한도에 걸려도 이중·준 이중 취약부터 채워지게
    targets = sorted((r for r in regions if not a.only or r['코드'] in a.only.split(',')), key=lambda r: order[r['등급']])
    session = requests.Session()
    failed = []
    for i, r in enumerate(targets):
        lines, cands = facts_for(r, regions, placement)
        old = done.get(r['코드'])
        if old and old['사실'] == lines and old.get('버전') == PROMPT_VERSION and not check_parts(old['브리핑'], lines) and not a.only:
            continue
        text, bad = None, ['-']
        for _ in range(3):
            text = generate(key, lines, cands, session)
            bad = check_parts(text, lines)
            if not bad:
                break
        if bad:
            failed.append((r['코드'], bad))
            done.pop(r['코드'], None)
        else:
            done[r['코드']] = {'브리핑': text, '사실': lines, '검토후보': cands, '버전': PROMPT_VERSION}
        print(f"[{i + 1}/{len(targets)}] {r['시도']} {r['시군구']}: {'실패 ' + str(bad) if bad else f"{sum(map(len, text.values()))}자"}", flush=True)
        save(done)
        time.sleep(1)  # 분당 요청 제한 여유
    print(f'완료: {len(done)}곳, 숫자 검증 실패로 뺀 곳 {len(failed)}곳 {failed}')


def save(done):
    out = {
        '설명': '생성형 AI 가 시군구 사실(지표)만 보고 쓴 담당자용 브리핑. 모든 숫자는 사실과 자동 대조(src.briefing.check). 판정·점수에는 쓰지 않음',
        '모델': MODEL, '프롬프트버전': PROMPT_VERSION, '생성일': date.today().isoformat(),
        '지역': dict(sorted(done.items())),
    }
    text = json.dumps(out, ensure_ascii=False, indent=1)
    OUT.write_text(text, encoding='utf-8')
    (PUB / 'ai_briefing.json').write_text(text, encoding='utf-8')


if __name__ == '__main__':
    main()
