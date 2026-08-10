"""자기대조 분석 — 대조군이 없는 코호트에서 판별력을 정직하게 추정하는 법.

## 문제

이 코호트는 573명 전원이 원내 심정지 후 사망했다. 심정지가 없었던 환자가 한 명도
없다. 따라서 P(심정지 | 활력징후) 를 추정할 수 없고, 특이도·양성예측도·오경보율도
계산할 수 없다. 이 데이터로 "심정지 예측 모델" 을 만들었다고 말하면 그것은
검증 불가능한 주장이다.

## 우리가 대신 하는 것 — 사례교차(case-crossover) 설계

각 환자를 **자기 자신의 대조군**으로 쓴다 (Maclure, Am J Epidemiol 1991).

    사례창   심정지 직전 6시간
    대조창   같은 환자의 24시간 이전 구간을 6시간 단위로 자른 것

두 창은 같은 사람에게서 나왔으므로 나이·기저질환·평소 혈압·병동 특성이 전부
설계 단계에서 상쇄된다. 보정할 교란변수가 남지 않는다.

## 이 추정량이 무엇이고 무엇이 아닌가

`within_patient_concordance()` 가 돌려주는 값은
**"같은 환자의 심정지 직전 6시간을, 그 환자의 이전 시간대와 구별하는 능력"** 이다.

일반 병동 환자 대비 판별력이 **아니다.** 두 값은 다른 추정량이고, 후자는 이
데이터로 원리상 추정할 수 없다. 제안서·보고서에서 이 둘을 섞어 쓰지 않는다.

다만 방향은 논증할 수 있다. 여기서 음성으로 쓰인 창은 **곧 심정지에 이를 환자의**
시간대이므로, 평범한 병동 환자보다 이미 나쁜 값을 가질 가능성이 높다. 즉 구별이
더 어려운 음성이다. 그렇다면 이 값은 일반 병동 대비 판별력의 **보수적 하한**으로
읽는 것이 타당하다. 이것은 논증이지 증명이 아니며, 보고서에도 그렇게 적는다.
"""

from __future__ import annotations

from dataclasses import dataclass

from .clocks import Clocks, _median, _observed_at
from .ews import news2_partial

CASE_WINDOW_H = 6.0  # 사례창 길이
WASHOUT_H = 24.0  # 사례창 앞의 완충 구간. 이 안은 대조창으로 쓰지 않는다
MIN_CONTROL_WINDOWS = 2  # 이보다 대조창이 적은 환자는 판별력 계산에서 제외


@dataclass
class WindowPair:
    patid: str
    case_score: float
    control_scores: list[float]


def _window_max_news2(rec: dict, hi_h: float, lo_h: float) -> float | None:
    """[lo_h, hi_h) 구간(심정지 전 시간 기준)에서 관측된 부분 NEWS2 의 최댓값."""
    stamps = sorted({h for v in rec["series"] for h, _ in rec["series"][v]}, reverse=True)
    inside = [t for t in stamps if lo_h <= t < hi_h]
    if not inside:
        return None
    best = None
    for t in inside:
        total, _single, used = news2_partial(_observed_at(rec, t))
        if used == 0:
            continue
        best = total if best is None else max(best, total)
    return float(best) if best is not None else None


def build_window_pairs(cohort: dict[str, dict]) -> list[WindowPair]:
    """환자마다 사례창 1개와 대조창 여러 개의 점수를 뽑는다."""
    pairs: list[WindowPair] = []
    for pid, rec in cohort.items():
        los_h = (rec["arrest"] - rec["admit"]).total_seconds() / 3600.0
        case = _window_max_news2(rec, CASE_WINDOW_H, 0.0)
        if case is None:
            continue
        controls: list[float] = []
        hi = WASHOUT_H + CASE_WINDOW_H
        while hi <= los_h:
            score = _window_max_news2(rec, hi, hi - CASE_WINDOW_H)
            if score is not None:
                controls.append(score)
            hi += CASE_WINDOW_H
        if len(controls) >= MIN_CONTROL_WINDOWS:
            pairs.append(WindowPair(pid, case, controls))
    return pairs


def within_patient_concordance(pairs: list[WindowPair]) -> dict[str, float]:
    """환자내 일치도 — 환자별로 층화한 Mann-Whitney 통계량의 평균.

    환자 한 명 안에서 "사례창 점수 > 대조창 점수" 인 비율을 구하고(동점은 0.5),
    그 값을 환자끼리 평균한다. 층화 AUC 와 같은 양이며, 최적화 루틴이 필요 없어
    폐쇄망에서 그대로 돈다. 0.5 는 전혀 구별하지 못한다는 뜻이다.
    """
    per_patient: list[float] = []
    for p in pairs:
        wins = sum(1.0 if p.case_score > c else 0.5 if p.case_score == c else 0.0
                   for c in p.control_scores)
        per_patient.append(wins / len(p.control_scores))
    if not per_patient:
        return {"c": float("nan"), "n": 0}
    mean = sum(per_patient) / len(per_patient)
    # 환자 단위 부트스트랩 대신 정규근사로 구간을 낸다 (환자 간 독립 가정).
    if len(per_patient) > 1:
        var = sum((x - mean) ** 2 for x in per_patient) / (len(per_patient) - 1)
        se = (var / len(per_patient)) ** 0.5
    else:
        se = 0.0
    return {"c": mean, "lo": mean - 1.96 * se, "hi": mean + 1.96 * se, "n": len(per_patient)}


def sensitivity_leadtime_curve(cohort: dict[str, dict], thresholds: list[int],
                               *, use_single_param: bool = False,
                               sustain_h: float | None = None) -> list[dict]:
    """임계값을 바꿔가며 (민감도, 리드타임) 을 훑는다.

    민감도 = 심정지 전에 한 번이라도 임계값을 넘긴 환자의 비율.
    이 코호트는 전원이 사례이므로 민감도는 정직하게 계산된다. **특이도는
    계산하지 않는다** — 음성 환자가 없어 계산 자체가 불가능하기 때문이다.
    임계값을 낮추면 민감도가 오르는 대신 실제 병동에서는 오경보가 늘지만,
    그 비용은 이 데이터로 측정할 수 없다. 곡선의 절반만 그릴 수 있다는 사실을
    그림에도 적는다.

    `sustain_h` 를 주면 **지속 발화**만 센다. 한 번 넘긴 뒤 그 시간 안에 다시
    넘겨야 인정한다. 한 점짜리 이상치로 울린 경보를 리드타임에 넣으면 리드타임이
    과대평가되므로, 실제 운영 기준에 가까운 쪽은 이쪽이다.
    """
    from .ews import news2_triggered

    out: list[dict] = []
    for th in thresholds:
        leads: list[float] = []
        fired = 0
        total = 0
        for _pid, rec in cohort.items():
            stamps = sorted({h for v in rec["series"] for h, _ in rec["series"][v]}, reverse=True)
            if not stamps:
                continue
            total += 1
            hits = [t for t in stamps
                    if news2_triggered(_observed_at(rec, t), threshold=th, bound="lo",
                                       use_single_param=use_single_param)]
            first = None
            if sustain_h is None:
                first = hits[0] if hits else None
            else:
                for i, t in enumerate(hits):
                    if any(t - later <= sustain_h for later in hits[i + 1:]):
                        first = t
                        break
            if first is not None:
                fired += 1
                leads.append(first)
        out.append(
            {
                "threshold": th,
                "sensitivity": fired / total if total else 0.0,
                "median_lead_h": _median(leads) if leads else 0.0,
                "n_fired": fired,
                "n_total": total,
            }
        )
    return out


def summarise(clocks: list[Clocks]) -> dict:
    """제안서에 실을 요약 수치."""
    ok = [c for c in clocks if c.ref_ok]
    n = len(ok)

    def frac(pred) -> float:
        return sum(1 for c in ok if pred(c)) / n if n else 0.0

    types = {}
    for c in ok:
        types[c.archetype] = types.get(c.archetype, 0) + 1

    phys = [c.t_phys for c in ok if c.t_phys is not None]
    rule = [c.t_rule_lo for c in ok if c.t_rule_lo is not None]
    obs = [c.t_obs for c in ok if c.t_obs is not None]
    rec_gap = [c.recognition_gap_h for c in ok if c.recognition_gap_h is not None]
    det_gap = [c.detection_gap_h for c in ok if c.detection_gap_h is not None]

    return {
        "n_total": len(clocks),
        "n_analysable": n,
        "types": types,
        "type_frac": {k: v / n for k, v in types.items()} if n else {},
        "median_t_phys_h": _median(phys) if phys else None,
        "median_t_rule_h": _median(rule) if rule else None,
        "median_t_obs_h": _median(obs) if obs else None,
        "median_recognition_gap_h": _median(rec_gap) if rec_gap else None,
        "median_detection_gap_h": _median(det_gap) if det_gap else None,
        "frac_late_recognition": (
            sum(1 for g in rec_gap if g > 0) / len(rec_gap) if rec_gap else None
        ),
        "frac_no_rule": frac(lambda c: c.t_rule_lo is None),
        "frac_no_signal": frac(lambda c: c.t_rule_lo is None and c.t_phys is None),
        "median_los_h": _median([c.los_hours for c in ok]) if ok else None,
        "median_arrest_to_death_min": _median([c.arrest_to_death_min for c in ok]) if ok else None,
        "frac_immediate_death": frac(lambda c: c.arrest_to_death_min <= 5.0),
    }
