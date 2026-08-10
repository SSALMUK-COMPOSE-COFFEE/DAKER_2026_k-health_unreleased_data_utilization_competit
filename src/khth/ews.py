"""조기경보점수(EWS) 후향 채점 — 그리고 이 데이터로는 **완전히 채점할 수 없다**는 사실.

## 이 모듈이 정직하게 말해야 하는 것

경북대병원 활력징후 데이터는 HR·SBP·DBP·BT·SPO2·RR 6종만 담는다.
그런데 표준 조기경보점수는 그것만으로 계산되지 않는다.

  NEWS2 (RCP 2017)  7개 항목 중 우리가 가진 것은 5개.
                    빠진 것: 의식수준(CVPU, 최대 +3), 산소투여 여부(최대 +2)
  MEWS  (Subbe 2001) 5개 항목 중 우리가 가진 것은 4개.
                    빠진 것: 의식수준(AVPU, 최대 +3)

빠진 항목은 모두 **가점 항목**이다. 감점 항목이 아니다. 따라서

    부분점수 ≤ 실제점수 ≤ 부분점수 + 미관측 최대가점

이 부등식이 항상 성립한다. 결과적으로

  · 우리가 계산한 **발화 시점은 실제보다 늦거나 같다** (민감도는 하한)
  · 우리가 계산한 **무신호 비율은 실제보다 높거나 같다** (상한)

이 방향성이 확정되어 있으므로, 부분점수로 얻은 결론은 "적어도 이만큼"이라는
형태로 안전하게 진술할 수 있다. `score_bounds()` 가 하한·상한을 함께 돌려주는
이유이며, 본선 분석에서는 두 경계를 모두 보고한다.

## 임계값 출처

NEWS2: Royal College of Physicians. National Early Warning Score (NEWS) 2. 2017.
MEWS : Subbe CP et al. Validation of a modified Early Warning Score in medical
       admissions. QJM 2001;94(10):521-6.
"""

from __future__ import annotations

# 미관측 항목이 더할 수 있는 최대 가점.
NEWS2_UNOBSERVED_MAX = 5  # 의식수준 3 + 산소투여 2
MEWS_UNOBSERVED_MAX = 3  # 의식수준 3

# NEWS2 표준 대응 임계값 (RCP 2017).
NEWS2_LOW_MEDIUM = 5  # 합계 5 이상 = 긴급 대응(key threshold)
NEWS2_HIGH = 7  # 합계 7 이상 = 응급 대응
NEWS2_SINGLE_PARAM = 3  # 단일 항목 3점 = 병동 긴급 진료
MEWS_TRIGGER = 5  # 통용되는 호출 기준


def _band(value: float, bands: list[tuple[float, float, int]]) -> int:
    """구간표에서 점수를 찾는다. 경계는 [lo, hi] 양끝 포함."""
    for lo, hi, score in bands:
        if lo <= value <= hi:
            return score
    return 0


# ── NEWS2 항목별 구간표 (RCP 2017) ───────────────────────────────────────
_INF = float("inf")

_NEWS2_RR = [(-_INF, 8, 3), (9, 11, 1), (12, 20, 0), (21, 24, 2), (25, _INF, 3)]
_NEWS2_SPO2 = [(-_INF, 91, 3), (92, 93, 2), (94, 95, 1), (96, _INF, 0)]
_NEWS2_SBP = [(-_INF, 90, 3), (91, 100, 2), (101, 110, 1), (111, 219, 0), (220, _INF, 3)]
_NEWS2_HR = [(-_INF, 40, 3), (41, 50, 1), (51, 90, 0), (91, 110, 1), (111, 130, 2), (131, _INF, 3)]
_NEWS2_BT = [(-_INF, 35.0, 3), (35.1, 36.0, 1), (36.1, 38.0, 0), (38.1, 39.0, 1), (39.1, _INF, 2)]

_NEWS2_TABLE = {"RR": _NEWS2_RR, "SPO2": _NEWS2_SPO2, "SBP": _NEWS2_SBP, "HR": _NEWS2_HR, "BT": _NEWS2_BT}

# ── MEWS 항목별 구간표 (Subbe 2001) ──────────────────────────────────────
_MEWS_SBP = [(-_INF, 70, 3), (71, 80, 2), (81, 100, 1), (101, 199, 0), (200, _INF, 2)]
_MEWS_HR = [(-_INF, 40, 2), (41, 50, 1), (51, 100, 0), (101, 110, 1), (111, 129, 2), (130, _INF, 3)]
_MEWS_RR = [(-_INF, 8, 2), (9, 14, 0), (15, 20, 1), (21, 29, 2), (30, _INF, 3)]
_MEWS_BT = [(-_INF, 34.9, 2), (35.0, 38.4, 0), (38.5, _INF, 2)]

_MEWS_TABLE = {"SBP": _MEWS_SBP, "HR": _MEWS_HR, "RR": _MEWS_RR, "BT": _MEWS_BT}


def news2_partial(obs: dict[str, float | None]) -> tuple[int, int, int]:
    """부분 NEWS2 를 채점한다.

    반환: (합계, 단일항목 최댓값, 채점에 쓰인 항목 수)

    관측되지 않은 항목은 **0 으로 취급하지 않고 채점에서 제외**한다. 결측을
    정상으로 간주하면 실제보다 낮은 점수가 나오는데, 그 방향의 오차는 이미
    의식수준·산소투여 누락으로 발생하고 있다. 두 번 겹치게 두지 않는다.
    """
    total = 0
    single_max = 0
    used = 0
    for key, table in _NEWS2_TABLE.items():
        v = obs.get(key)
        if v is None:
            continue
        s = _band(v, table)
        total += s
        single_max = max(single_max, s)
        used += 1
    return total, single_max, used


def mews_partial(obs: dict[str, float | None]) -> tuple[int, int]:
    """부분 MEWS 를 채점한다. 반환: (합계, 채점에 쓰인 항목 수)."""
    total = 0
    used = 0
    for key, table in _MEWS_TABLE.items():
        v = obs.get(key)
        if v is None:
            continue
        total += _band(v, table)
        used += 1
    return total, used


def score_bounds(obs: dict[str, float | None]) -> dict[str, object]:
    """한 시점의 관측치를 점수의 **하한과 상한**으로 옮긴다.

    상한은 미관측 항목이 최악(만점 가점)이었다고 가정한 값이다. 실제 점수는
    반드시 이 사이에 있다. 하한만 쓰면 놓친 경보를 과다 계상하고, 상한만 쓰면
    과소 계상한다. 본선 보고에서는 두 값이 만드는 구간을 그대로 제시한다.
    """
    n_total, n_single, n_used = news2_partial(obs)
    m_total, m_used = mews_partial(obs)
    return {
        "news2_lo": n_total,
        "news2_hi": n_total + NEWS2_UNOBSERVED_MAX,
        "news2_single_max": n_single,
        "news2_items": n_used,
        "mews_lo": m_total,
        "mews_hi": m_total + MEWS_UNOBSERVED_MAX,
        "mews_items": m_used,
    }


def news2_triggered(obs: dict[str, float | None], *, threshold: int = NEWS2_LOW_MEDIUM,
                    bound: str = "lo", use_single_param: bool = True) -> bool:
    """NEWS2 대응 기준을 넘겼는가.

    `bound="lo"` 는 확실히 넘긴 경우만 참이 된다 (보수적 · 민감도 하한).
    `bound="hi"` 는 넘겼을 가능성이 있으면 참이 된다 (민감도 상한).
    단일 항목 3점 기준은 관측된 항목만으로 판정하므로 두 경계가 같다.

    NEWS2 는 발화 경로가 둘이다. 합계 임계값과 단일 항목 3점이며, 둘은 OR 로 묶인다.
    실제 운영에서는 둘 다 켜는 것이 맞지만, **합계 임계값의 효과만 보려면 단일 항목
    경로를 꺼야 한다.** 켜 둔 채로 임계값을 훑으면 곡선이 단일 항목 경로에 포화되어
    임계값이 무엇을 바꾸는지 보이지 않는다. `use_single_param` 이 그 스위치다.
    """
    total, single_max, used = news2_partial(obs)
    if used == 0:
        return False
    value = total if bound == "lo" else total + NEWS2_UNOBSERVED_MAX
    if value >= threshold:
        return True
    return use_single_param and single_max >= NEWS2_SINGLE_PARAM
