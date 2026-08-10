"""
중력식 수액 주입의 정수압 감쇠 모형 — 사전 예측 계산
표준 라이브러리만 사용 (이 환경엔 numpy/pip 없음)

모형
----
수액백이 비어가면서 액면이 내려가고 구동 정수압이 감소한다.
  Q(h) = k · (h - h_v)          h = 정맥 기준 유효 수두(cmH2O), h_v = 정맥압
  액면 강하: dh = -dV / A       A = 백의 유효 단면적
유량조절기 다이얼은 주입 시작 시점(h = h0)에서 처방속도에 맞춰 설정된다고 가정.

이론 주입시간 = V0 / Q(h0)            (처방속도가 끝까지 유지된다고 가정한 값)
실제 주입시간 = ∫ dV / Q(h)           (수두가 감소하므로 더 길어진다)

닫힌 해:
  실제/이론 = [(h0 - h_v) / Δ] · ln( (h0 - h_v) / (h0 - Δ - h_v) )
  Δ = V0 / A = 총 수두 강하량

핵심 성질: 이 비율에 다이얼 설정(k)이 들어가지 않는다.
→ 정수압 감쇠만으로는 **처방 주입시간이 오차율에 영향을 주지 않는다.**
"""
import math


def ratio_closed(h0, hv, delta):
    """실제/이론 주입시간 비 (닫힌 해)"""
    a = h0 - hv
    b = h0 - delta - hv
    if b <= 0:
        return float('inf')
    return (a / delta) * math.log(a / b)


def ratio_sim(h0, hv, delta, n=200000):
    """수치 적분으로 닫힌 해 검증"""
    dv = delta / n          # 수두 단위로 적분
    t = 0.0
    for i in range(n):
        h = h0 - (i + 0.5) * dv
        t += dv / (h - hv)
    t_theory = delta / (h0 - hv)
    return t / t_theory


# ── 파라미터 범위 ──────────────────────────────────────────────
# 수액백 유효 단면적: 500mL 백이 액면 20~30cm 구간에 걸친다고 보면 A ≈ 17~25 cm²
# → Δ = V0/A. 수액 총량이 클수록 Δ가 커진다.
HV = 8.0                    # 정맥압 cmH2O (앉은 자세 말초정맥, 통상 5~12)
VEIN = 80.0                 # 항암주사실 리클라이너 착석 시 천자부 높이 cm

print("=" * 74)
print("정수압 감쇠 모형 — 실제/이론 주입시간 비 (1.20 = 오차 +20%)")
print("=" * 74)
print(f"가정: 정맥압 {HV:.0f} cmH2O, 천자부 높이 {VEIN:.0f} cm")
print()

print(f"{'수액총량':>8} {'A(cm2)':>7} {'Δ(cm)':>7} | {'150cm 폴':>10} {'200cm 폴':>10} {'차이':>8}")
print("-" * 74)
rows = []
for v0 in (100, 250, 500, 1000):
    for A in (20.0, 25.0):
        delta = v0 / A
        r150 = ratio_closed(150 - VEIN, HV, delta)
        r200 = ratio_closed(200 - VEIN, HV, delta)
        rows.append((v0, A, delta, r150, r200))
        d = "n/a" if math.isinf(r150) else f"{(r150-r200)*100:+.1f}%p"
        s150 = "고갈" if math.isinf(r150) else f"{r150:.3f}"
        print(f"{v0:>8} {A:>7.0f} {delta:>7.1f} | {s150:>10} {r200:>10.3f} {d:>8}")

print()
print("닫힌 해 vs 수치적분 검증 (V0=250mL, A=25 → Δ=10cm):")
for pole in (150, 200):
    c = ratio_closed(pole - VEIN, HV, 10.0)
    s = ratio_sim(pole - VEIN, HV, 10.0)
    print(f"  {pole}cm 폴: 닫힌해 {c:.6f} / 수치적분 {s:.6f} / 차이 {abs(c-s):.2e}")

print()
print("=" * 74)
print("처방 주입시간(다이얼 설정)이 오차율에 미치는 영향")
print("=" * 74)
print("모형상 실제/이론 비에 다이얼 conductance k가 소거된다.")
print("→ 30/60/90/120분 군의 오차율은 정수압 감쇠만으로는 동일해야 한다.")
print("→ 만약 데이터에서 처방시간 주효과가 나타나면 그 원인은 정수압이 아니라")
print("   (a) 낮은 유량에서 조절기 다이얼 분해능·크립 (b) 분 단위 기록 양자화")
print("   (c) 장시간 노출 중 체위변화·정맥압 변동 중 하나다. 이 구분이 분석의 핵심.")
print()

print("분 단위 기록 양자화가 만드는 겉보기 오차 (경쟁 가설 (b)):")
print(f"{'처방시간':>8} {'±1분 기록오차의 상대크기':>26}")
print("-" * 40)
for m in (30, 60, 90, 120):
    print(f"{m:>6}분 {1.0/m*100:>24.2f}%")
print()
print("→ 짧은 주입일수록 양자화 잡음이 크다. 정수압·다이얼 효과는 긴 주입에서 크다.")
print("   두 효과가 반대 방향이므로 처방시간 주효과는 반드시 교란을 분리해 해석해야 한다.")
