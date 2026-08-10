"""세 개의 시계 — 심정지를 원점으로 두고 시간을 거꾸로 읽는다.

환자마다 심정지 시각(CARDT)을 t=0 으로 놓고 세 개의 시점을 각각 추정한다.

  T_phys  생리 이탈 시점 — 환자 자신의 안정기 기저에서 활력징후가 지속적으로 벗어난 때
  T_rule  규칙 발화 시점 — 표준 조기경보점수(NEWS2/MEWS)가 대응 기준을 넘긴 때
  T_obs   관측 강화 시점 — 활력징후 **측정 간격이 짧아진** 때

셋 다 심정지 몇 시간 전인지로 표현한다. 값이 클수록 이르다. `None` 은 끝내 없었다는 뜻이다.

## T_obs 가 왜 데이터인가

측정 간격은 기계가 정하지 않는다. 사람이 정한다. 병동 정규 관측은 q4~8h 로 돌지만,
간호사가 환자 상태를 걱정하기 시작하면 간격이 짧아진다. 즉 **VSDT 의 간격 자체가
임상진의 판단을 남긴 흔적**이다. 활력징후 값 외에 추가 데이터가 하나도 필요 없다.

기존 연구는 불규칙 측정 간격을 결측 편향으로 보고 보정 대상으로 삼는다
(Agniel et al., BMJ 2018). 우리는 반대로 **읽어야 할 신호**로 쓴다. 이것이
T_phys·T_rule 만 보는 선행 연구(예: Kim et al., PLOS ONE 2015)와 갈라지는 지점이다.

## 자기대조 원칙

세 시계 모두 **환자 자신의 안정기**를 기준으로 삼는다. 다른 환자와 비교하지 않는다.
이 코호트는 전원이 심정지 후 사망한 환자여서 정상 대조군이 아예 없고, 따라서
환자 간 비교로는 어떤 것도 판정할 수 없기 때문이다. 나이·기저질환·체질 차이는
자기 자신과 비교하는 순간 전부 상쇄된다.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

from .ews import news2_triggered
from .schema import DETERIORATION_SIGN, MEASUREMENT_NOISE_FLOOR, PLAUSIBLE_RANGE, VITALS

# 시간 창을 둘로 나눈다 (통계적 공정관리의 Phase I / Phase II 와 같은 분리).
#
#   교정창 [-72h, -48h]  환자 자신의 기준값과 산포를 추정한다. 여기서는 탐지하지 않는다.
#   감시창 [-48h,   0)   변화점을 찾는다.
#
# 왜 나누는가 — 교정에 쓴 구간에서 변화를 탐지하면 자기 자신을 기준으로 자기를
# 재는 셈이 되어 앞뒤가 맞지 않는다. 더 실무적인 이유도 있다. 창을 나누지 않고
# 입원 시점부터 누적을 돌리면, 입원 직후의 불안정한 활력징후에 누적이 먼저 쌓여
# 변화 개시 시점이 입원일까지 밀린다 (실측으로 확인: 중앙값 84h 로 부풀었다).
#
# 감시창을 48시간으로 끊은 것은 임상적 판단이다. 그보다 이른 신호는 병동에서
# 실행 가능한 조치로 이어지지 않으며, 선행 연구도 24~48시간 범위를 본다
# (Kim et al., PLOS ONE 2015 는 24·16·8시간 시점을 봤다).
MONITOR_H = 48.0
REF_MIN_OBS = 8  # 교정 구간 관측이 이보다 적으면 그 환자는 분석에서 제외한다

# 롤링 기준선 — 각 시점을 자신의 [t+12h, t+36h] 구간과 비교한다.
BASELINE_LAG_H = 12.0
BASELINE_WIDTH_H = 24.0
BASELINE_MIN_OBS = 4

# CUSUM 파라미터. 이탈량은 이미 무차원(표준화된 z 의 양수부 평균)이다.
CUSUM_K_MARGIN = 1.0  # 허용 드리프트 = 교정 구간 중앙값 + 이 배수 × MAD
CUSUM_K_MIN = 0.5
CUSUM_H_MIN = 3.5  # 문턱의 하한
CUSUM_H_MARGIN = 1.15  # 교정 구간 내 최대 누적값에 이 배수를 곱해 문턱을 잡는다
LOCF_TOLERANCE_H = 2.0  # 직전 측정치를 끌어다 쓸 수 있는 최대 경과 시간


@dataclass
class Clocks:
    patid: str
    t_phys: float | None  # 심정지 몇 시간 전 (클수록 이름)
    t_rule_lo: float | None  # 부분점수 하한 기준 발화
    t_rule_hi: float | None  # 미관측 항목 최대가점 가정 시 발화
    t_obs: float | None
    n_obs_events: int
    los_hours: float
    arrest_to_death_min: float
    age: int
    sex: str
    ref_ok: bool

    @property
    def archetype(self) -> str:
        """개입 지점이 다른 세 유형으로 나눈다.

        규칙포착   T_rule 이 있다 → 규칙은 울렸다. 남은 문제는 대응이다.
        규칙미발화 T_phys 는 있는데 T_rule 이 없다 → 임계값이 이 환자에게 안 맞았다.
        무신호     둘 다 없다 → 활력징후로는 잡히지 않는 심정지. 다른 접근이 필요하다.
        """
        if self.t_rule_lo is not None:
            return "규칙포착"
        if self.t_phys is not None:
            return "규칙미발화"
        return "무신호"

    @property
    def recognition_gap_h(self) -> float | None:
        """생리 이탈과 관측 강화 사이의 간격 (시간).

        양수면 생리가 먼저 움직였는데 사람이 늦게 알아챈 것이고,
        음수면 사람이 먼저 알아챈 것이다. `None` 은 둘 중 하나가 없다는 뜻이다.
        """
        if self.t_phys is None or self.t_obs is None:
            return None
        return self.t_phys - self.t_obs

    @property
    def detection_gap_h(self) -> float | None:
        """생리 이탈이 규칙 발화보다 얼마나 앞섰는가 (시간). 규칙 임계값의 여유분."""
        if self.t_phys is None or self.t_rule_lo is None:
            return None
        return self.t_phys - self.t_rule_lo


# ── 견고 통계 ─────────────────────────────────────────────────────────────
def _median(xs: list[float]) -> float:
    s = sorted(xs)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0


def _mad_scale(xs: list[float], med: float) -> float:
    """정규분포에서 표준편차와 눈금이 맞도록 1.4826 을 곱한 MAD."""
    if len(xs) < 2:
        return 0.0
    return 1.4826 * _median([abs(x - med) for x in xs])


# ── 파싱 ─────────────────────────────────────────────────────────────────
def parse_cohort(pinfo_rows: list[dict], vital_rows: list[dict]) -> dict[str, dict]:
    """두 테이블을 환자별 시계열로 접는다. 여기까지가 전처리다.

    수행하는 것:
      · VS_RSLT 는 VARCHAR2 다. 숫자 변환에 실패하는 행이 있을 수 있으므로 버린다.
      · 생리학적 가용 범위(`schema.PLAUSIBLE_RANGE`) 밖의 값은 기록 오류로 보고 버린다.
      · 심정지 시각 **이후** 기록은 전부 잘라낸다. 소생술 중 기록이 섞이면
        "심정지 전 신호" 를 묻는 질문 자체가 오염된다.
    """
    info: dict[str, dict] = {}
    for r in pinfo_rows:
        arrest = datetime.strptime(str(r["CARDT"]), "%Y%m%d%H%M")
        death = datetime.strptime(str(r["DEATHDT"]), "%Y%m%d%H%M")
        admit = datetime.strptime(str(r["INDD"]), "%Y%m%d")
        info[str(r["PATID"])] = {
            "admit": admit,
            "arrest": arrest,
            "death": death,
            "age": int(r["AGE"]),
            "sex": str(r["SEX"]),
            "series": {v: [] for v in VITALS},
            "dropped": 0,
        }

    for r in vital_rows:
        pid = str(r["PATID"])
        rec = info.get(pid)
        if rec is None:
            continue
        gbn = str(r["VS_GBN"]).strip().upper()
        if gbn not in PLAUSIBLE_RANGE:
            rec["dropped"] += 1
            continue
        try:
            value = float(str(r["VS_RSLT"]).strip())
        except ValueError:
            rec["dropped"] += 1
            continue
        lo, hi = PLAUSIBLE_RANGE[gbn]
        if not (lo <= value <= hi):
            rec["dropped"] += 1
            continue
        ts = datetime.strptime(str(r["VSDT"]), "%Y%m%d%H%M")
        h_before = (rec["arrest"] - ts).total_seconds() / 3600.0
        if h_before <= 0:  # 심정지 이후 기록
            rec["dropped"] += 1
            continue
        rec["series"][gbn].append((h_before, value))

    for rec in info.values():
        for v in VITALS:
            rec["series"][v].sort(key=lambda p: -p[0])  # 이른 것부터
    return info


# ── 공통 시각 격자 ────────────────────────────────────────────────────────
GRID_SNAP_H = 0.25  # 15분


def _grid(rec: dict) -> list[float]:
    """관측 시각을 15분 격자에 맞춰 접는다.

    같은 간호 라운드에서 잰 값이라도 기록 시각이 몇 분씩 흩어진다 (설명서 예시가
    14:00 과 14:10 으로 나뉜 것이 그 경우다). 접지 않으면 한 번의 관측이 여러
    격자점으로 세어져 관측 강도가 부풀고, 누적합의 표본이 서로 상관된다.

    내림으로 접는 것은 의도적이다. 격자점이 원래 측정보다 뒤(=심정지에 가까운
    쪽)로 가야 직전 측정치 끌어오기(LOCF)가 그 측정을 놓치지 않는다.
    """
    stamps = {math.floor(h / GRID_SNAP_H) * GRID_SNAP_H
              for v in VITALS for h, _ in rec["series"][v]}
    return sorted(stamps, reverse=True)


def _locf(series: list[tuple[float, float]], at_h: float) -> float | None:
    """at_h 시점에서 유효한 최근 측정치. 허용 경과 시간을 넘기면 없는 것으로 본다."""
    best = None
    for h, value in series:
        if h < at_h:
            break
        best = (h, value)
    if best is None:
        return None
    return best[1] if (best[0] - at_h) <= LOCF_TOLERANCE_H else None


def _observed_at(rec: dict, at_h: float) -> dict[str, float | None]:
    return {v: _locf(rec["series"][v], at_h) for v in VITALS}


# ── CUSUM ────────────────────────────────────────────────────────────────
def _cusum_onset(times: list[float], values: list[float | None]) -> float | None:
    """단측 CUSUM 으로 상승 변화점을 찾는다.

    교정창(cal_mask)의 중앙값·MAD 로 표준화하고, 감시창(mon_mask)에서만 누적을 돌린다.
    문턱을 넘은 시점이 아니라, **그 직전에 누적합이 마지막으로 0 이었던 시점**을
    변화 개시 시점으로 돌려준다 (CUSUM 의 표준 변화점 추정량). 문턱 도달 시점을
    쓰면 탐지 지연만큼 늦게 잡혀 리드타임이 체계적으로 과소평가된다.

    ## 문턱을 고정값으로 두지 않는 이유

    문턱을 상수로 박으면 그 값이 데이터마다 맞기도 하고 안 맞기도 한다. 활력징후
    6종을 평균 낸 이탈량은 평균 과정에서 분산이 줄어드는데, 그 좁아진 산포로
    표준화하면 아주 작은 변화도 문턱을 즉시 넘긴다 (실측으로 확인: 심어 둔 개시
    시점이 2h 든 22h 든 전부 감시창 시작점인 43h 로 추정되었다).

    그래서 문턱을 **환자 자신의 교정창에서 뽑는다.** 교정창에서 같은 누적합을
    돌려 안정 상태에서 도달하는 최댓값을 재고, 거기에 여유를 곱한 값을 문턱으로
    쓴다. 안정기에 울리지 않을 만큼만 둔감한 문턱이 환자마다 자동으로 정해진다.
    정답 라벨이 필요 없으므로 안심존 실데이터에 그대로 적용된다.

    의존성 없는 40줄이다. 안심존에서 패키지 반입이 거부되어도 그대로 돈다.
    """
    points = [(t, v) for t, v in zip(times, values) if v is not None]
    cal = [v for t, v in points if t >= MONITOR_H]
    mon = [(t, v) for t, v in points if t < MONITOR_H]
    if len(cal) < REF_MIN_OBS or len(mon) < 3:
        return None

    med = _median(cal)
    k = max(CUSUM_K_MIN, med + CUSUM_K_MARGIN * _mad_scale(cal, med))

    # 1단계 — 교정 구간에서 안정 상태의 누적 최댓값을 잰다.
    s = 0.0
    in_control_peak = 0.0
    for v in cal:
        s = max(0.0, s + v - k)
        in_control_peak = max(in_control_peak, s)
    threshold = max(CUSUM_H_MIN, CUSUM_H_MARGIN * in_control_peak)

    # 2단계 — 감시창에서 그 문턱을 넘는 시점을 찾는다.
    s = 0.0
    anchor = None
    for t, v in mon:
        s_new = max(0.0, s + v - k)
        if s <= 0.0 and s_new > 0.0:
            anchor = t  # 누적이 다시 쌓이기 시작한 지점
        s = s_new
        if s > threshold:
            return anchor if anchor is not None else t
    return None


# ── 시계 1: 생리 이탈 ─────────────────────────────────────────────────────
def _deviation_series(rec: dict, grid: list[float]) -> list[float | None]:
    """각 시점의 '악화 방향 이탈량'. 활력징후 6종을 하나의 무차원 수로 접는다.

    ## 기준선은 고정이 아니라 따라 움직인다

    각 시점 t 를 그 환자의 **12~36시간 전 자신**과 비교한다. 재원 기간 전체의
    중앙값을 기준으로 삼지 않는다. 이유는 두 가지다.

    첫째, 활력징후는 재원 중 계속 변한다. 3개월 입원한 환자의 전체 중앙값은
    지금의 그를 대표하지 않는다. 고정 기준선으로 돌렸을 때, 심정지 2.6시간 전에
    급격히 악화된 환자도 34시간 전부터 이탈한 것으로 잡혔다 — 기준선이 옛날의
    그를 가리키고 있었기 때문이다.

    둘째, 이 쪽이 사례교차 설계와 같은 논리다. 대조 구간을 같은 환자의 조금 전
    시간대로 두는 것이며, 그렇게 하면 나이·기저질환·체질이 자동으로 상쇄된다.

    12시간의 지연(lag)을 두는 것은 **비교 대상이 이미 악화된 시점이 되는 것을
    막기 위해서**다. 바로 직전과 비교하면 서서히 진행하는 악화는 매 시점 조금씩만
    달라 보여 영영 탐지되지 않는다.

    ## 방향

    HR·RR 은 오를 때, SBP·DBP·SPO2 는 내릴 때만 이탈로 센다. 체온은 고열·저체온
    양쪽이 악화이므로 절댓값을 쓴다. 반대 방향 변화는 0 이다 — 호전을 이탈로 세면
    회복 중인 환자에게 경보가 울린다.

    반환값의 `None` 은 그 시점에 비교할 기준선이 없다는 뜻이다 (기록 초반).
    """
    per_vital_raw = {v: [_locf(rec["series"][v], t) for t in grid] for v in VITALS}

    out: list[float | None] = []
    for i, t in enumerate(grid):
        lo, hi = t + BASELINE_LAG_H, t + BASELINE_LAG_H + BASELINE_WIDTH_H
        zs: list[float] = []
        for v in VITALS:
            now = per_vital_raw[v][i]
            if now is None:
                continue
            base = [x for h, x in rec["series"][v] if lo <= h <= hi]
            if len(base) < BASELINE_MIN_OBS:
                continue
            med = _median(base)
            # 산포는 반드시 측정 잡음 바닥 이상이어야 한다. 기준선 값이 우연히
            # 전부 같으면 MAD 가 0 이 되고, 그것으로 나누면 이탈량이 발산한다
            # (바닥값 없이 돌렸을 때 2×10⁸ 까지 튀었다).
            scale = max(_mad_scale(base, med), MEASUREMENT_NOISE_FLOOR[v])
            sign = DETERIORATION_SIGN[v]
            if sign == 0:
                zs.append(abs(now - med) / scale)
            else:
                zs.append(max(0.0, sign * (now - med) / scale))
        out.append(sum(zs) / len(zs) if zs else None)
    return out


# ── 시계 3: 관측 강도 ─────────────────────────────────────────────────────
def _intensity_series(grid: list[float]) -> list[float]:
    """측정 사건 사이 간격의 역수 = 시간당 관측 횟수. 3점 이동평균으로 다듬는다."""
    if len(grid) < 2:
        return [0.0] * len(grid)
    rates = [0.0]
    for i in range(1, len(grid)):
        gap = max(grid[i - 1] - grid[i], 1e-3)
        rates.append(1.0 / gap)
    rates[0] = rates[1]
    smoothed = []
    for i in range(len(rates)):
        lo, hi = max(0, i - 1), min(len(rates), i + 2)
        smoothed.append(sum(rates[lo:hi]) / (hi - lo))
    return smoothed


# ── 조립 ─────────────────────────────────────────────────────────────────
def compute_clocks(pid: str, rec: dict) -> Clocks:
    arrest, admit = rec["arrest"], rec["admit"]
    los_h = (arrest - admit).total_seconds() / 3600.0
    a2d_min = (rec["death"] - arrest).total_seconds() / 60.0
    grid = _grid(rec)

    empty = Clocks(pid, None, None, None, None, len(grid), los_h, a2d_min,
                   rec["age"], rec["sex"], ref_ok=False)
    if len(grid) < 8:
        return empty

    if sum(1 for t in grid if t >= MONITOR_H) < REF_MIN_OBS:
        return empty  # 감시창 이전 기록이 모자라 교정이 불가능하다

    dev = _deviation_series(rec, grid)
    t_phys = _cusum_onset(grid, dev)

    intensity = _intensity_series(grid)
    t_obs = _cusum_onset(grid, intensity)

    # 규칙 발화도 같은 감시창 안에서만 센다. 세 시계를 같은 창에서 재야 비교가 성립한다.
    t_rule_lo = t_rule_hi = None
    for t in (g for g in grid if g < MONITOR_H):
        obs = _observed_at(rec, t)
        if t_rule_lo is None and news2_triggered(obs, bound="lo"):
            t_rule_lo = t
        if t_rule_hi is None and news2_triggered(obs, bound="hi"):
            t_rule_hi = t
        if t_rule_lo is not None and t_rule_hi is not None:
            break

    return Clocks(pid, t_phys, t_rule_lo, t_rule_hi, t_obs, len(grid), los_h, a2d_min,
                  rec["age"], rec["sex"], ref_ok=True)


def compute_all(cohort: dict[str, dict]) -> list[Clocks]:
    return [compute_clocks(pid, rec) for pid, rec in cohort.items()]
