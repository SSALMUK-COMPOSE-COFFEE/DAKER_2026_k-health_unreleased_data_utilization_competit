"""제안서 도표 — 전부 **합성 코호트** 위에서 그린다.

여기서 나오는 어떤 수치도 임상적 발견이 아니다. 파이프라인이 끝까지 돌아
그림까지 나온다는 사실만 증명한다. 모든 그림의 부제에 그 사실을 박아 둔다.

색은 dataviz 스킬의 기준 팔레트를 쓴다. 3슬롯(파랑·주황·아쿠아)은 전(全)쌍
검증을 통과한 조합이고, 아쿠아가 밝은 배경에서 대비 3:1 미만이라 **모든 계열에
직접 라벨을 붙이는 것**으로 완화한다. 인쇄물이라 호버 계층은 없다.
"""

from __future__ import annotations

import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402

from .clocks import _median, _observed_at  # noqa: E402
from .ews import news2_partial  # noqa: E402
from .schema import VITAL_LABEL_KO, VITAL_UNIT, VITALS  # noqa: E402

FIG_DIR = Path("docs/figures")

# ── 팔레트 (dataviz 기준 인스턴스, light) ────────────────────────────────
S1, S2, S3 = "#2a78d6", "#eb6834", "#1baf7a"  # 카테고리 슬롯 1·2·3
DIV_COOL, DIV_WARM, DIV_MID = "#2a78d6", "#e34948", "#f0efec"  # 발산 쌍
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"


def setup_fonts() -> None:
    for f in Path("assets/fonts").glob("Pretendard-*.ttf"):
        font_manager.fontManager.addfont(str(f))
    plt.rcParams.update(
        {
            "font.family": "Pretendard",
            "font.size": 9,
            "axes.facecolor": SURFACE,
            "figure.facecolor": SURFACE,
            "savefig.facecolor": SURFACE,
            "axes.edgecolor": AXIS,
            "axes.labelcolor": INK2,
            "xtick.color": MUTED,
            "ytick.color": MUTED,
            "xtick.labelsize": 8,
            "ytick.labelsize": 8,
            "axes.titlesize": 9.5,
            "axes.titlecolor": INK,
            "axes.unicode_minus": False,
            "grid.color": GRID,
            "grid.linewidth": 0.6,
            "legend.frameon": False,
        }
    )


def _clean(ax, *, grid_axis="y") -> None:
    """축을 물러나게 한다. 데이터가 가장 진해야 한다."""
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_linewidth(0.8)
    ax.grid(True, axis=grid_axis, linewidth=0.6, color=GRID, zorder=0)
    ax.set_axisbelow(True)


def _tag(ax, x, y, text, color, *, ha="left", va="center") -> None:
    """직접 라벨. 글자는 잉크색으로 두고 **색은 옆의 점이 나른다** (팔레트 규칙)."""
    ax.plot([x], [y], "o", color=color, markersize=5.5, clip_on=False, zorder=6)
    ax.annotate(text, (x, y), xytext=(9 if ha == "left" else -9, 0),
                textcoords="offset points", ha=ha, va=va,
                fontsize=8.5, color=INK2, clip_on=False, zorder=6)


def _quantiles(xs: list[float], qs=(0.25, 0.5, 0.75)) -> list[float]:
    s = sorted(xs)
    out = []
    for q in qs:
        if not s:
            out.append(float("nan"))
            continue
        i = q * (len(s) - 1)
        lo, hi = math.floor(i), math.ceil(i)
        out.append(s[lo] + (s[hi] - s[lo]) * (i - lo))
    return out


# ── 그림 1: 역행 정렬 활력징후 궤적 ──────────────────────────────────────
def fig_trajectories(cohort: dict, path: Path, max_h: float = 48.0, bin_h: float = 3.0) -> None:
    """심정지를 원점(오른쪽 끝)으로 두고 6종을 각각 따로 그린다.

    단위가 다른 6개를 한 축에 겹치는 것은 금지 규칙(이중 축)에 걸린다.
    소반복(small multiples)이 정답이다.
    """
    nb = int(max_h / bin_h)
    fig, axes = plt.subplots(2, 3, figsize=(7.4, 3.9), dpi=300)
    for ax, v in zip(axes.ravel(), VITALS):
        centres, med, q1, q3 = [], [], [], []
        for b in range(nb):
            hi, lo = max_h - b * bin_h, max_h - (b + 1) * bin_h
            vals = [x for rec in cohort.values() for h, x in rec["series"][v] if lo <= h < hi]
            if len(vals) < 20:
                continue
            a, m, c = _quantiles(vals)
            centres.append((hi + lo) / 2)
            q1.append(a)
            med.append(m)
            q3.append(c)
        ax.fill_between(centres, q1, q3, color=S1, alpha=0.15, linewidth=0, zorder=2)
        ax.plot(centres, med, color=S1, linewidth=2.0, zorder=3, solid_capstyle="round")
        ax.set_title(f"{VITAL_LABEL_KO[v]} ({VITAL_UNIT[v]})", pad=4, loc="left")
        ax.set_xlim(max_h, 0)
        ax.axvline(0, color=AXIS, linewidth=1.0, zorder=1)
        _clean(ax)
    for ax in axes[1]:
        ax.set_xlabel("심정지 전 경과시간 (h)", fontsize=8, color=MUTED)
    fig.suptitle("활력징후 역행 정렬 궤적 — 중앙값과 사분위 범위",
                 x=0.012, y=0.995, va="top", ha="left", fontsize=11, color=INK, weight="bold")
    fig.text(0.012, 0.925, "합성 코호트 N=573 · 실데이터 아님 (파이프라인 실행 검증용)",
             ha="left", va="top", fontsize=8, color=MUTED)
    fig.tight_layout(rect=(0, 0, 1, 0.885))
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


# ── 그림 2: 세 시계의 리드타임 ECDF ──────────────────────────────────────
def fig_leadtime_ecdf(clocks: list, path: Path, max_h: float = 48.0) -> None:
    """"심정지 X시간 전까지 몇 %의 환자에게 신호가 있었는가" 를 바로 읽는 형태."""
    ok = [c for c in clocks if c.ref_ok]
    n = len(ok)
    series = [
        ("생리 이탈", [c.t_phys for c in ok if c.t_phys is not None], S1),
        ("규칙 발화", [c.t_rule_lo for c in ok if c.t_rule_lo is not None], S2),
        ("관측 강화", [c.t_obs for c in ok if c.t_obs is not None], S3),
    ]
    fig, ax = plt.subplots(figsize=(7.4, 3.5), dpi=300)
    grid = [max_h * i / 240 for i in range(241)]
    for label, vals, color in series:
        y = [100.0 * sum(1 for v in vals if v >= g) / n for g in grid]
        ax.plot(grid, y, color=color, linewidth=2.0, zorder=4, solid_capstyle="round")
        # 라벨은 선 오른쪽 끝 **바깥**에 놓는다. 안쪽에 두면 선 위에 겹친다.
        _tag(ax, 0.0, y[0], f"{label}  {y[0]:.0f}%", color)
    ax.set_xlim(max_h, 0)
    ax.set_ylim(0, 100)
    ax.set_xlabel("심정지 전 경과시간 (h)", fontsize=8.5, color=MUTED)
    ax.set_ylabel("이 시점까지 신호가 발생한 환자 비율 (%)", fontsize=8.5, color=INK2)
    ax.axvline(0, color=AXIS, linewidth=1.0, zorder=1)
    _clean(ax)
    fig.suptitle("세 개의 시계 — 신호 발생 시점의 누적 분포",
                 x=0.012, ha="left", fontsize=11, color=INK, weight="bold")
    fig.text(0.012, 0.905,
             "오른쪽 끝(0h)이 심정지 시점. 왼쪽으로 갈수록 이르다. 합성 코호트 · 실데이터 아님",
             ha="left", fontsize=8, color=MUTED)
    fig.tight_layout(rect=(0, 0, 0.99, 0.88))
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


# ── 그림 3: 민감도–리드타임 트레이드오프 ─────────────────────────────────
def fig_tradeoff(curve: list[dict], curve_sustained: list[dict], path: Path) -> None:
    """임계값을 매개변수로 둔 운영특성 곡선.

    **특이도 축은 없다.** 음성 환자가 코호트에 존재하지 않아 계산이 불가능하다.
    곡선의 절반만 그릴 수 있다는 사실을 그림 안에 적어 둔다.
    """
    fig, ax = plt.subplots(figsize=(7.4, 3.6), dpi=300)
    for rows, color, label in ((curve, S1, "1회 발화"), (curve_sustained, S2, "지속 발화(4h 내 재발화)")):
        xs = [r["median_lead_h"] for r in rows]
        ys = [100 * r["sensitivity"] for r in rows]
        ax.plot(xs, ys, color=color, linewidth=2.0, marker="o", markersize=5,
                markerfacecolor=SURFACE, markeredgewidth=1.6, markeredgecolor=color, zorder=4)
        for r, x, y in zip(rows, xs, ys):
            if r["threshold"] in (3, 5, 7, 10):
                ax.annotate(f"≥{r['threshold']}", (x, y), xytext=(0, -13),
                            textcoords="offset points", ha="center",
                            fontsize=7.5, color=MUTED)
        _tag(ax, xs[0], ys[0], label, color)
    ax.set_xlabel("발화 시점의 리드타임 중앙값 (심정지 전 h)", fontsize=8.5, color=MUTED)
    ax.set_ylabel("민감도 (%)", fontsize=8.5, color=INK2)
    ax.set_ylim(0, 100)
    _clean(ax)
    fig.suptitle("NEWS2 합계 임계값에 따른 민감도–리드타임 교환",
                 x=0.012, ha="left", fontsize=11, color=INK, weight="bold")
    fig.text(0.012, 0.905,
             "특이도·오경보율 축은 그릴 수 없다 — 이 코호트에 심정지가 없었던 환자가 없기 때문이다. "
             "합성 코호트 · 실데이터 아님",
             ha="left", fontsize=8, color=MUTED)
    fig.tight_layout(rect=(0, 0, 1, 0.88))
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


# ── 그림 4: 유형 분해 ────────────────────────────────────────────────────
def fig_archetypes(summary: dict, path: Path) -> None:
    """100% 가로 막대 하나. 세 유형은 서로 다른 개입 지점을 뜻한다."""
    order = [
        ("규칙포착", S1, "규칙이 울렸다 → 남은 문제는 대응"),
        ("규칙미발화", S2, "생리는 움직였는데 규칙이 안 울렸다 → 임계값 재보정"),
        ("무신호", S3, "활력징후에 안 드러났다 → 다른 접근 필요"),
    ]
    fig, ax = plt.subplots(figsize=(7.4, 2.05), dpi=300)
    left = 0.0
    n = summary["n_analysable"]
    for name, color, _ in order:
        frac = 100.0 * summary["types"].get(name, 0) / n
        ax.barh([0], [frac - 0.35], left=left, color=color, height=0.42, zorder=3)  # 0.35 = 표면 간극
        if frac >= 8.0:
            ax.text(left + frac / 2, 0, f"{frac:.0f}%", ha="center", va="center",
                    fontsize=9.5, color="white", weight="bold", zorder=5)
        else:
            # 좁은 칸에 흰 글씨를 욱여넣으면 잘린다. 막대 위 잉크색으로 뺀다.
            ax.text(left + frac / 2, 0.27, f"{frac:.0f}%", ha="center", va="bottom",
                    fontsize=9.0, color=INK, weight="bold", zorder=5)
        left += frac
    for i, (name, color, note) in enumerate(order):
        y = -0.62 - i * 0.30
        ax.add_patch(Rectangle((0.0, y - 0.045), 1.6, 0.09, color=color, clip_on=False, zorder=5))
        ax.text(2.6, y, f"{name}  ", ha="left", va="center", fontsize=8.6, color=INK, weight="bold")
        ax.text(13.5, y, note, ha="left", va="center", fontsize=8.4, color=INK2)
    ax.set_xlim(0, 100)
    ax.set_ylim(-1.62, 0.42)
    ax.axis("off")
    fig.suptitle("심정지 573례의 유형 분해 — 개입 지점이 다르다",
                 x=0.012, ha="left", fontsize=11, color=INK, weight="bold")
    fig.text(0.012, 0.845, f"분석가능 {n}명 · 합성 코호트 · 실데이터 아님",
             ha="left", fontsize=8, color=MUTED)
    fig.tight_layout(rect=(0, 0, 1, 0.82))
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


# ── 그림 5: 인지 격차 (발산) ─────────────────────────────────────────────
def fig_recognition_gap(clocks: list, path: Path, span: float = 24.0) -> None:
    """생리 이탈과 관측 강화 사이의 부호 있는 간격. 0 을 기준으로 방향이 갈린다."""
    gaps = [c.recognition_gap_h for c in clocks if c.recognition_gap_h is not None]
    gaps = [max(-span, min(span, g)) for g in gaps]
    nbin = 24
    width = 2 * span / nbin
    counts = [0] * nbin
    for g in gaps:
        counts[min(nbin - 1, int((g + span) / width))] += 1

    fig, ax = plt.subplots(figsize=(7.4, 3.1), dpi=300)
    for i, c in enumerate(counts):
        lo = -span + i * width
        colour = DIV_COOL if lo + width / 2 < 0 else DIV_WARM
        ax.bar([lo + width / 2], [c], width=width - 0.28, color=colour, zorder=3)
    ax.axvline(0, color=INK2, linewidth=1.2, zorder=4)
    late = 100.0 * sum(1 for g in gaps if g > 0) / len(gaps)
    ax.set_xlabel("생리 이탈 시점 − 관측 강화 시점 (h)", fontsize=8.5, color=MUTED)
    ax.set_ylabel("환자 수", fontsize=8.5, color=INK2)
    ax.set_xlim(-span, span)
    _clean(ax)
    # 막대 안에 두면 가장 높은 막대와 겹친다. 축 바로 위로 뺀다.
    ax.text(0.0, 1.04, f"◀ 사람이 먼저 알아챔  {100 - late:.0f}%", transform=ax.transAxes,
            fontsize=8.6, color=INK2, va="bottom")
    ax.text(1.0, 1.04, f"생리가 먼저 움직임  {late:.0f}% ▶", transform=ax.transAxes,
            fontsize=8.6, color=INK2, ha="right", va="bottom")
    fig.suptitle("인지 격차 — 활력징후가 움직인 뒤 사람이 알아채기까지",
                 x=0.012, y=0.995, va="top", ha="left", fontsize=11, color=INK, weight="bold")
    fig.text(0.012, 0.912,
             "오른쪽(붉은 쪽)이 놓친 시간이다. 합성 코호트 · 실데이터 아님",
             ha="left", va="top", fontsize=8, color=MUTED)
    fig.tight_layout(rect=(0, 0, 1, 0.84))
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


def render_all(cohort: dict, clocks: list, summary: dict,
               curve: list[dict], curve_sustained: list[dict]) -> list[Path]:
    setup_fonts()
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    jobs = [
        ("fig1-trajectories.png", lambda p: fig_trajectories(cohort, p)),
        ("fig2-leadtime-ecdf.png", lambda p: fig_leadtime_ecdf(clocks, p)),
        ("fig3-tradeoff.png", lambda p: fig_tradeoff(curve, curve_sustained, p)),
        ("fig4-archetypes.png", lambda p: fig_archetypes(summary, p)),
        ("fig5-recognition-gap.png", lambda p: fig_recognition_gap(clocks, p)),
    ]
    out = []
    for name, fn in jobs:
        path = FIG_DIR / name
        fn(path)
        out.append(path)
        print(f"      → {path}")
    return out
