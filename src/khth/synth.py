"""설명서 스키마로 합성 코호트를 만든다.

## 왜 만드는가

의료데이터안심존은 폐쇄망이고, 전자기기 반입이 금지되며, 방문 시간이 평일 주간으로
제한된다. 현장에서 코드를 처음 쓰기 시작하면 방문 회차의 대부분을 디버깅에 쓴다.
그래서 **설명서에 적힌 스키마만으로 데이터를 흉내 내어, 파이프라인을 미리 끝까지
돌려 놓는다.** 안심존에서는 입력 경로만 바꾼다.

## 무엇이 아닌가

여기서 나오는 수치는 **임상적 발견이 아니다.** 합성 생성 파라미터를 되읽은 것에
불과하다. 이 모듈의 출력으로 그린 그림은 전부 "파이프라인이 끝까지 돈다"는 사실만
증명한다. 제안서에서도 그렇게만 인용한다.

## 맞춘 것 / 지어낸 것

맞춘 것 — 설명서에 적혀 있어 그대로 따른 값
  · N=573, 성별 M 376 / F 197, 연령대 7구간 분포
  · 두 테이블의 컬럼명·타입·날짜 포맷, 조인키 (PATID, INDD)
  · 활력징후 6종과 VS_GBN 코드, long 포맷 (한 행에 한 측정)
  · 입원 후 24시간 이내 심정지 제외 → 모든 환자가 24시간 이상의 선행 기록을 갖는다
  · 측정 간격이 일정하지 않다는 서술

지어낸 것 — 설명서에 없어 가정한 값. 안심존 1차 방문에서 전부 대조한다.
  · 활력징후의 기저값과 분산, 악화 궤적의 모양
  · 측정 간격의 기저 분포 (병동 관측 프로토콜을 q4~8h 로 가정)
  · 임상진의 관측 강화 시점과 그 지연
  · 심정지→사망 간격의 분포
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .schema import AGE_DISTRIBUTION, COHORT_N, SEX_DISTRIBUTION, VITALS

# 합성 코호트의 잠재 유형. 실데이터에서 이 비율을 **추정하는 것**이 분석의 목표이지,
# 여기 적힌 값이 답은 아니다. 파이프라인이 세 유형을 구분해내는지 보려고 심어 둔다.
ARCHETYPE_MIX = {
    "gradual": 0.45,  # 수 시간~하루에 걸쳐 서서히 악화
    "abrupt": 0.35,  # 심정지 직전 1~3시간에 급격히 악화
    "silent": 0.20,  # 활력징후에 거의 드러나지 않음 (부정맥·색전 등)
}

# 연령대별 기저 활력징후. (평균, 개인간 표준편차)
_BASE = {
    "HR": (78.0, 11.0),
    "SBP": (126.0, 17.0),
    "DBP": (74.0, 10.0),
    "BT": (36.7, 0.35),
    "SPO2": (97.0, 1.6),
    "RR": (17.0, 2.6),
}

# 측정 잡음 (개인 내 변동). 기기·자세·시간대에서 오는 흔들림.
_NOISE = {"HR": 5.0, "SBP": 9.0, "DBP": 6.0, "BT": 0.2, "SPO2": 1.0, "RR": 1.6}

# 심정지 직전 최종 이탈 폭. 악화 방향으로 이만큼 밀린다.
_TERMINAL_SHIFT = {"HR": +38.0, "SBP": -42.0, "DBP": -24.0, "BT": +0.9, "SPO2": -9.0, "RR": +11.0}


@dataclass
class Patient:
    patid: str
    age: int
    sex: str
    admit: datetime
    arrest: datetime
    death: datetime
    archetype: str
    onset_hours: float  # 심정지 몇 시간 전부터 생리적으로 이탈했는가 (정답)
    noticed_hours: float | None  # 임상진이 관측을 강화한 시점 (정답). None = 끝내 강화 없음
    baseline: dict[str, float] = field(default_factory=dict)

    @property
    def los_hours(self) -> float:
        return (self.arrest - self.admit).total_seconds() / 3600.0

    @property
    def arrest_to_death_min(self) -> float:
        return (self.death - self.arrest).total_seconds() / 60.0


def _sample_categorical(rng: random.Random, weights: dict) -> object:
    total = sum(weights.values())
    r = rng.random() * total
    acc = 0.0
    for k, w in weights.items():
        acc += w
        if r <= acc:
            return k
    return list(weights)[-1]


def _build_cohort(rng: random.Random, n: int) -> list[Patient]:
    """설명서의 성별·연령 분포를 정확히 재현한 뒤 개인 속성을 뽑는다."""
    ages: list[int] = []
    for band, count in AGE_DISTRIBUTION.items():
        ages += [band] * count
    sexes: list[str] = []
    for s, count in SEX_DISTRIBUTION.items():
        sexes += [s] * count
    # 설명서 분포는 N=573 기준이다. 다른 n 을 요청하면 비례 축소한다.
    if n != COHORT_N:
        ages = [ages[int(i * len(ages) / n)] for i in range(n)]
        sexes = [sexes[int(i * len(sexes) / n)] for i in range(n)]
    rng.shuffle(ages)
    rng.shuffle(sexes)

    patients: list[Patient] = []
    for i in range(n):
        age, sex = ages[i], sexes[i]
        # 일자는 설명서대로 시프트 처리된 상태를 가정한다. 2023-01-01 ~ 2025-12-31.
        admit = datetime(2023, 1, 1) + timedelta(
            minutes=rng.randrange(0, 3 * 365 * 24 * 60)
        )
        # 입원 후 24시간 이내 심정지는 제외 기준이므로 하한이 24시간이다.
        los_h = 24.0 + rng.lognormvariate(math.log(70.0), 1.0)
        los_h = min(los_h, 24.0 * 120)  # 120일 상한
        arrest = admit + timedelta(hours=los_h)

        archetype = _sample_categorical(rng, ARCHETYPE_MIX)
        if archetype == "gradual":
            onset = rng.uniform(8.0, 36.0)
        elif archetype == "abrupt":
            onset = rng.uniform(0.7, 3.5)
        else:  # silent
            onset = rng.uniform(0.2, 1.0)
        onset = min(onset, los_h - 2.0)

        # 임상진의 인지. 생리 이탈보다 늦되, 일부는 먼저 알아채고 일부는 끝내 놓친다.
        roll = rng.random()
        if archetype == "silent":
            noticed = None if roll < 0.70 else max(0.1, onset * rng.uniform(0.3, 0.9))
        elif roll < 0.18:
            noticed = min(onset * rng.uniform(1.1, 1.8), los_h - 1.0)  # 먼저 알아챔
        elif roll < 0.75:
            noticed = onset * rng.uniform(0.25, 0.85)  # 뒤늦게 알아챔
        else:
            noticed = None  # 구심로 실패

        # 심정지 → 사망. 즉시 사망과 소생 후 사망의 혼합.
        if rng.random() < 0.42:
            gap_min = float(rng.randrange(0, 6))
        else:
            gap_min = rng.lognormvariate(math.log(240.0), 1.4)
            gap_min = min(gap_min, 60 * 24 * 21)
        death = arrest + timedelta(minutes=gap_min)

        base = {}
        for v, (mu, sd) in _BASE.items():
            shift = {"HR": -2.0, "SBP": +6.0, "DBP": -2.0, "BT": 0.0, "SPO2": -0.5, "RR": +0.4}[v]
            base[v] = rng.gauss(mu + shift * (age - 60) / 10.0, sd)

        patients.append(
            Patient(
                patid=f"{9000000 + i}",
                age=age,
                sex=sex,
                admit=admit,
                arrest=arrest,
                death=death,
                archetype=archetype,
                onset_hours=onset,
                noticed_hours=noticed,
                baseline=base,
            )
        )
    return patients


def _observation_times(rng: random.Random, p: Patient) -> list[float]:
    """측정 시각을 시간축(입원 후 경과 시간)으로 뽑는다.

    관측 강도는 두 겹이다.
      기저   병동 정규 관측. q4h ~ q8h 를 환자별로 뽑는다.
      강화   임상진이 악화를 인지한 뒤 간격이 짧아진다 (q1h 안팎).
    이 **간격 자체가 임상적 판단의 흔적**이라는 것이 분석의 핵심 착상이다.
    """
    base_interval = rng.choice([4.0, 4.0, 6.0, 8.0])
    escalated_interval = rng.uniform(0.5, 1.5)
    notice_t = None if p.noticed_hours is None else p.los_hours - p.noticed_hours

    times: list[float] = []
    t = rng.uniform(0.2, base_interval)
    while t < p.los_hours:
        times.append(t)
        interval = base_interval if (notice_t is None or t < notice_t) else escalated_interval
        # 실제 기록은 정확히 규칙적이지 않다. 로그정규 지터를 준다.
        t += interval * rng.lognormvariate(0.0, 0.32)
    return times


def _vital_at(rng: random.Random, p: Patient, hours_to_arrest: float, v: str) -> float:
    """심정지 h 시간 전의 활력징후 한 값."""
    base = p.baseline[v]
    if hours_to_arrest >= p.onset_hours:
        drift = 0.0
    else:
        frac = 1.0 - (hours_to_arrest / p.onset_hours)  # 0 → 1 로 진행
        shape = frac**2.2 if p.archetype == "abrupt" else frac**1.15
        amp = {"gradual": 1.0, "abrupt": 1.15, "silent": 0.22}[p.archetype]
        drift = _TERMINAL_SHIFT[v] * shape * amp
    value = base + drift + rng.gauss(0.0, _NOISE[v])
    if v == "SPO2":
        value = min(value, 100.0)
    if v == "BT":
        return round(value, 1)
    return float(round(value))


def generate(n: int = COHORT_N, seed: int = 20260814) -> tuple[list[dict], list[dict], list[Patient]]:
    """(PINFO 행들, VITAL 행들, 정답이 붙은 Patient 객체들) 을 돌려준다.

    Patient 는 **검증용**이다. 분석 파이프라인은 PINFO/VITAL 두 리스트만 본다.
    안심존 실데이터에는 정답이 없으므로, 파이프라인이 Patient 를 참조하는 순간
    그 코드는 현장에서 못 쓴다.
    """
    rng = random.Random(seed)
    patients = _build_cohort(rng, n)

    pinfo: list[dict] = []
    vital: list[dict] = []
    for p in patients:
        indd = p.admit.strftime("%Y%m%d")
        pinfo.append(
            {
                "PATID": p.patid,
                "AGE": p.age,
                "SEX": p.sex,
                "INDD": indd,
                "OUDD": p.death.strftime("%Y%m%d"),  # 전원 사망 → 퇴원일 = 사망일
                "CARDT": p.arrest.strftime("%Y%m%d%H%M"),
                "DEATHDT": p.death.strftime("%Y%m%d%H%M"),
            }
        )
        for t in _observation_times(rng, p):
            stamp = p.admit + timedelta(hours=t)
            h_to_arrest = p.los_hours - t
            # 한 관측 사건에서 6종이 모두 남지는 않는다. 설명서 예시도 그렇다.
            recorded = [v for v in VITALS if rng.random() > 0.08]
            for v in recorded:
                # 같은 사건이라도 기록 시각이 몇 분씩 흩어진다 (설명서 예시 재현).
                jitter = timedelta(minutes=rng.choice([0, 0, 0, 10]))
                vital.append(
                    {
                        "PATID": p.patid,
                        "INDD": indd,
                        "VSDT": (stamp + jitter).strftime("%Y%m%d%H%M"),
                        "VS_GBN": v,
                        "VS_RSLT": str(_vital_at(rng, p, h_to_arrest, v)),
                    }
                )
    return pinfo, vital, patients
