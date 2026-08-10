#!/usr/bin/env python3
"""오염된 약물명 → 표준 성분 → 허가사항 권고 주입시간 대조.

설명서(4~5페이지)의 항암제 컬럼 값 22개를 그대로 입력으로 받는다.
어떤 의약품 DB도 `Perbrolizumab`을 조회하지 못하므로 정규화가 선행되어야 한다.

  1단계  RxNorm approximateTerm — 철자 오류에 강인한 후보 매칭 (인증 불필요)
  2단계  RxNorm rxcui → 성분명(IN) 확정
  3단계  openFDA drug label(CC0)에서 dosage_and_administration 조회
  4단계  주입시간 문구 추출 → 데이터의 처방시간 30/60/90/120분과 대조

표준 라이브러리만 사용. 이 환경엔 pip이 없다.
실제 시스템에서는 1~2단계를 Gemini가 함께 수행하고, RxNorm은 교차검증에 쓴다.
결과 22건은 전수 수작업 검증 대상이다 (제안서에 정확도로 보고).
"""
import json
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request

CTX = ssl.create_default_context()
UA = {"User-Agent": "kheath-proposal-prototype/1.0"}

# 설명서 원문 그대로. 오타·중복·상품명 혼입 포함.
DIRTY = [
    "BevaciZumab", "Bevacizumb", "Carboplatin", "Cetuximab", "Cisplain",
    "Cisplatin", "Cisplatine", "Gemcitabin", "Gemcitabine", "Irinotecan",
    "Leucovorin", "Leucovorin sod", "Nivolumab", "Nivolumab 옵디보주",
    "Oxailplatin", "Oxaliplati", "Oxaliplatin", "pembrolizumab",
    "Pembrolizumb", "Perbrolizumab", "Ramucirumab", "Trastuzumab-Deruxt",
]

# 데이터의 처방 주입시간 수준 (분)
PRESCRIBED = [30, 60, 90, 120]


def get(url, params=None, tries=3):
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=25, context=CTX) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            if i == tries - 1:
                return {"__error__": str(e)}
            time.sleep(1.5 * (i + 1))
    return None


def strip_noise(name):
    """상품명·염 표기 등 검색을 방해하는 꼬리를 떼어낸다."""
    s = re.sub(r"[^\x00-\x7F]+", " ", name)          # 한글 상품명 제거
    s = re.sub(r"\b(sod|sodium|hcl|inj|injection)\b", " ", s, flags=re.I)
    s = s.replace("-", " ")
    return " ".join(s.split())


def normalize(name):
    """RxNorm approximateTerm → 성분명(IN). 실패 시 None."""
    q = strip_noise(name)
    j = get("https://rxnav.nlm.nih.gov/REST/approximateTerm.json",
            {"term": q, "maxEntries": 4})
    cands = ((j or {}).get("approximateGroup") or {}).get("candidate") or []
    if not cands:
        return None, None, None
    best = cands[0]
    rxcui = best.get("rxcui")
    try:
        score = float(best.get("score"))
    except (TypeError, ValueError):
        score = None
    # 매칭된 개념 자체의 이름
    concept = best.get("name")
    # rxcui → 성분(IN)
    rel = get(f"https://rxnav.nlm.nih.gov/REST/rxcui/{rxcui}/related.json", {"tty": "IN"})
    ing = None
    for g in (((rel or {}).get("relatedGroup") or {}).get("conceptGroup") or []):
        for c in (g.get("conceptProperties") or []):
            ing = c.get("name")
            break
        if ing:
            break

    # ⚠️ 실패모드 B 보정 — 항체-약물 접합체가 모체 항체로 붕괴하는 것을 막는다.
    # 예: "Trastuzumab-Deruxt" → 개념은 fam-trastuzumab deruxtecan인데 IN은 trastuzumab.
    # 개념명이 성분명보다 토큰이 많으면 개념명을 채택한다.
    if concept and ing and len(concept.split()) > len(ing.split()):
        base = re.split(r"\s+\d|\s*\(", concept)[0].strip().lower()
        if ing.lower() in base and base != ing.lower():
            return base, rxcui, score
    return (ing or concept), rxcui, score


DUR = re.compile(
    r"over\s+(?:a\s+)?(?:period\s+of\s+)?"
    r"(\d+(?:\s*(?:to|-|–)\s*\d+)?)\s*(minute|min|hour|hr)",
    re.I,
)


def durations(text):
    """허가사항 본문에서 '~에 걸쳐 주입' 문구를 분 단위로 추출."""
    out = []
    for m in DUR.finditer(text):
        qty, unit = m.group(1), m.group(2).lower()
        nums = [int(x) for x in re.findall(r"\d+", qty)]
        mult = 60 if unit.startswith("h") else 1
        lo, hi = min(nums) * mult, max(nums) * mult
        out.append((lo, hi, " ".join(m.group(0).split())))
    seen, uniq = set(), []
    for lo, hi, s in out:
        if (lo, hi) not in seen:
            seen.add((lo, hi))
            uniq.append((lo, hi, s))
    return sorted(uniq)


def label_durations(ingredient, iv_only=True):
    """⚠️ 실패모드 A 보정 — 경로(route)를 고정하지 않으면 피하주사(SC) 제형 라벨이 잡힌다.
    pembrolizumab·nivolumab은 SC 제형이 존재해 '1~2분', '3~5분'이 반환된다.
    우리 데이터는 정맥주입이므로 INTRAVENOUS로 한정해야 한다."""
    q = f'openfda.generic_name:"{ingredient}"'
    if iv_only:
        q += ' AND openfda.route:"INTRAVENOUS"'
    j = get("https://api.fda.gov/drug/label.json", {"search": q, "limit": 1})
    if not j or "error" in j or not j.get("results"):
        return None, []
    r = j["results"][0]
    txt = " ".join(r.get("dosage_and_administration", []))
    if not txt:
        return None, []
    return len(txt), durations(txt)


def main():
    print("=" * 96)
    print("오염된 약물명 정규화 + 허가사항 권고 주입시간 대조")
    print("=" * 96)

    # 1~2단계
    resolved = {}
    print(f"\n[1] RxNorm 정규화 — 입력 {len(DIRTY)}개 문자열\n")
    print(f"{'설명서 표기':<24} {'→ 표준 성분':<30} {'rxcui':>9} {'score':>7}")
    print("-" * 74)
    for d in DIRTY:
        ing, rxcui, score = normalize(d)
        resolved[d] = ing
        mark = "" if ing else "  ✗ 실패"
        print(f"{d:<24} {(ing or '—'):<30} {str(rxcui or '—'):>9} "
              f"{(f'{score:.1f}' if score else '—'):>7}{mark}")

    uniq = sorted({v for v in resolved.values() if v})
    print(f"\n  → {len(DIRTY)}개 문자열이 {len(uniq)}개 성분으로 수렴")
    print(f"  → 실패 {sum(1 for v in resolved.values() if not v)}건")

    # 3~4단계
    print(f"\n[2] openFDA 허가사항(CC0) 권고 주입시간 — 성분 {len(uniq)}개")
    print("    경로 한정 없이 조회한 결과와 INTRAVENOUS로 한정한 결과를 나란히 둔다.\n")
    print(f"{'성분':<26} {'경로 무관(분)':<22} {'IV 한정(분)':<22} 판정")
    print("-" * 96)
    table = {}
    routebug = 0
    for ing in uniq:
        _, any_d = label_durations(ing, iv_only=False)
        n, iv_d = label_durations(ing, iv_only=True)
        table[ing] = iv_d
        def fmt(ds):
            if not ds:
                return "—"
            return ", ".join(f"{lo}" if lo == hi else f"{lo}~{hi}" for lo, hi, _ in ds)
        a, b = fmt(any_d), fmt(iv_d)
        flag = ""
        if a != b and any_d and iv_d:
            flag = "⚠ 경로 혼입"
            routebug += 1
        print(f"{ing:<26} {a:<22} {b:<22} {flag}")
    print(f"\n  → 경로를 한정하지 않으면 {routebug}개 성분에서 다른 값이 나온다.")

    # 대조
    print(f"\n[3] 데이터의 처방시간 {PRESCRIBED}분과 대조\n")
    print(f"{'성분':<26} " + " ".join(f"{p:>6}분" for p in PRESCRIBED))
    print("-" * 96)
    legend_hit, legend_out = 0, 0
    for ing in uniq:
        ds = table.get(ing) or []
        if not ds:
            continue
        cells = []
        for p in PRESCRIBED:
            inside = any(lo <= p <= hi for lo, hi, _ in ds)
            cells.append(f"{'  적합' if inside else '  이탈':>7}")
            legend_hit += inside
            legend_out += (not inside)
        print(f"{ing:<26} " + " ".join(cells))
    print(f"\n  적합 {legend_hit} / 이탈 {legend_out}")
    print("\n  ※ '이탈'은 해당 처방시간이 그 약의 허가사항 권고 범위 밖이라는 뜻이다.")
    print("     실제 판정에는 실측 편차를 더해야 하므로, 이 표는 편차 이전의 기준선이다.")


if __name__ == "__main__":
    sys.exit(main())
