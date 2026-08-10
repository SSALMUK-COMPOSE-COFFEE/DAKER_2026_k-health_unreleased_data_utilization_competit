"""파이프라인 전 구간 실행 — 합성 코호트 생성 → 세 시계 → 자기대조 분석 → 요약.

    .venv/bin/python -m src.khth.run

안심존에서는 `generate()` 호출부만 실데이터 로더로 바꾼다. 그 아래는 손대지 않는다.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .analysis import (
    build_window_pairs,
    sensitivity_leadtime_curve,
    summarise,
    within_patient_concordance,
)
from .clocks import compute_all, parse_cohort
from .synth import generate

OUT = Path("data/khth_pipeline.json")


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 573
    print(f"[1/5] 합성 코호트 생성 (N={n}) …")
    pinfo, vital, truth = generate(n=n)
    print(f"      PINFO {len(pinfo):,}행 · VITAL {len(vital):,}행")

    print("[2/5] 전처리 (long → 환자별 시계열, 이상값·심정지후 기록 제거) …")
    cohort = parse_cohort(pinfo, vital)
    dropped = sum(r["dropped"] for r in cohort.values())
    print(f"      환자 {len(cohort):,}명 · 제외행 {dropped:,}")

    print("[3/5] 세 개의 시계 …")
    clocks = compute_all(cohort)
    s = summarise(clocks)
    print(f"      분석가능 {s['n_analysable']}/{s['n_total']}명 · 유형 {s['types']}")

    print("[4/5] 자기대조 (사례교차) …")
    pairs = build_window_pairs(cohort)
    conc = within_patient_concordance(pairs)
    print(f"      환자내 일치도 {conc['c']:.3f} [{conc['lo']:.3f}, {conc['hi']:.3f}] (n={conc['n']})")

    print("[5/5] 민감도–리드타임 곡선 …")
    ths = [3, 4, 5, 6, 7, 8, 9, 10]
    curve = sensitivity_leadtime_curve(cohort, ths)
    curve_sustained = sensitivity_leadtime_curve(cohort, ths, sustain_h=4.0)
    for a, b in zip(curve, curve_sustained):
        print(f"      NEWS2 합계 ≥{a['threshold']:>2}  민감도 {a['sensitivity']:.3f} "
              f"(지속 {b['sensitivity']:.3f})  리드타임 중앙값 {a['median_lead_h']:>5.1f}h "
              f"(지속 {b['median_lead_h']:>5.1f}h)")

    # 합성 데이터에서만 가능한 검증: 심어 둔 정답과 대조한다.
    truth_mix: dict[str, int] = {}
    for p in truth:
        truth_mix[p.archetype] = truth_mix.get(p.archetype, 0) + 1
    print(f"\n      [검증] 생성 시 심은 잠재유형 {truth_mix}")

    print("[6/6] 도표 …")
    from .figures import render_all

    render_all(cohort, clocks, s, curve, curve_sustained)

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(
        json.dumps(
            {"summary": s, "concordance": conc, "curve": curve, "curve_sustained": curve_sustained, "truth_mix": truth_mix},
            ensure_ascii=False,
            indent=2,
        )
    )
    print(f"\n      → {OUT}")


if __name__ == "__main__":
    main()
