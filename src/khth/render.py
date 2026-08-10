"""제안서 마크다운 → 제출용 PDF.

    .venv/bin/python -m src.khth.render [입력.md] [출력.pdf]

대회 규칙상 제출물은 **PDF, 30장 이내**이고 서식 규정은 없다. 그래서 조판은
읽기 쉬운 쪽으로 정했다: A4, Pretendard 10.5pt, 줄간격 1.62.

색은 도표와 같은 계열을 쓴다 (dataviz 기준 팔레트의 파랑 램프). 문서와 그림이
서로 다른 파랑을 쓰면 인쇄물에서 바로 티가 난다.

## 지원 문법

    # 제목 / ## 부제        표지
    @@META … @@ENDMETA      표지 정보표
    @@PAGEBREAK             쪽 나눔
    ## / ###                절 / 항 제목
    @@TABLE … @@ENDTABLE    표 (첫 줄 = 머리행, `|` 구분, 빈 칸은 위 칸에 이어짐)
    @@FIGSPEC … @@ENDFIGSPEC   글머리 목록 블록
    @@CALLOUT … @@ENDCALLOUT   강조 상자 (테두리)
    @@NOTE … @@ENDNOTE         보조 상자 (음영)
    @@FORMULA … @@ENDFORMULA   가운데 정렬 수식/도식 줄
    @@FIGURE 파일명 … @@ENDFIGURE  그림 + 캡션
    @@REFS … @@ENDREFS         참고문헌
    @@CLOCKS @@GAPS @@WINDOWS @@TIMELINE   본문 도식 (벡터로 직접 그린다)
    **굵게**
"""

from __future__ import annotations

import html
import re
import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Flowable,
    Frame,
    Image,
    KeepTogether,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

FONT_DIR = Path("assets/fonts")
FIG_DIR = Path("docs/figures")
DEFAULT_IN = Path("docs/khealth-proposal.md")
DEFAULT_OUT = Path("docs/khealth-proposal.pdf")
PAGE_LIMIT = 30

# dataviz 기준 팔레트와 같은 계열.
INK = colors.HexColor("#0b0b0b")
INK2 = colors.HexColor("#52514e")
MUTED = colors.HexColor("#898781")
RULE = colors.HexColor("#e1e0d9")
BAND = colors.HexColor("#f0efec")
ACCENT = colors.HexColor("#1c5cab")  # blue-550
ACCENT_LIGHT = colors.HexColor("#cde2fb")  # blue-100
WARM = colors.HexColor("#eb6834")
SURFACE = colors.HexColor("#fcfcfb")

MARGIN = 20 * mm
AVAIL = A4[0] - 2 * MARGIN


def register_fonts() -> bool:
    try:
        for weight, name in (("Regular", "KR"), ("Medium", "KR-M"),
                             ("SemiBold", "KR-SB"), ("Bold", "KR-B")):
            pdfmetrics.registerFont(TTFont(name, FONT_DIR / f"Pretendard-{weight}.ttf"))
        pdfmetrics.registerFontFamily("KR", normal="KR", bold="KR-B")
        return True
    except Exception as exc:  # 폰트가 없으면 한글이 깨지지만 조판은 되게 둔다
        print(f"[경고] Pretendard 등록 실패 → 내장 폰트로 대체합니다: {exc}")
        return False


def make_styles(ok: bool) -> dict[str, ParagraphStyle]:
    body, med, semi, bold = ("KR", "KR-M", "KR-SB", "KR-B") if ok else (("Helvetica",) * 4)
    base = dict(fontName=body, textColor=INK, leading=17.0, fontSize=10.5)
    return {
        "cover_title": ParagraphStyle("ct", **{**base, "fontName": bold, "fontSize": 30,
                                               "leading": 38, "textColor": INK}),
        "cover_sub": ParagraphStyle("cs", **{**base, "fontName": med, "fontSize": 14,
                                             "leading": 22, "textColor": ACCENT}),
        # keepWithNext: 제목만 쪽 끝에 남고 본문이 다음 쪽으로 넘어가는 것을 막는다.
        "h1": ParagraphStyle("h1", **{**base, "fontName": bold, "fontSize": 16.5,
                                      "leading": 23, "spaceBefore": 2, "spaceAfter": 7,
                                      "keepWithNext": 1}),
        "h2": ParagraphStyle("h2", **{**base, "fontName": semi, "fontSize": 12.2,
                                      "leading": 18, "spaceBefore": 11, "spaceAfter": 4,
                                      "textColor": ACCENT, "keepWithNext": 1}),
        "p": ParagraphStyle("p", **{**base, "spaceAfter": 7.5, "leading": 17.0}),
        "bullet": ParagraphStyle("b", **{**base, "leftIndent": 11, "firstLineIndent": -11,
                                         "spaceAfter": 4.5, "leading": 16.4}),
        "cell": ParagraphStyle("c", **{**base, "fontSize": 9.4, "leading": 13.6}),
        "cell_h": ParagraphStyle("ch", **{**base, "fontName": semi, "fontSize": 9.4,
                                          "leading": 13.6, "textColor": colors.white}),
        "caption": ParagraphStyle("cap", **{**base, "fontSize": 9.2, "leading": 14,
                                            "textColor": INK2, "spaceBefore": 4,
                                            "spaceAfter": 9}),
        "callout": ParagraphStyle("co", **{**base, "fontSize": 10.0, "leading": 16.2,
                                           "spaceAfter": 4}),
        "formula": ParagraphStyle("f", **{**base, "fontName": med, "fontSize": 11,
                                          "leading": 18, "alignment": 1,
                                          "textColor": ACCENT}),
        "ref": ParagraphStyle("r", **{**base, "fontSize": 9.4, "leading": 14.4,
                                      "leftIndent": 16, "firstLineIndent": -16,
                                      "spaceAfter": 5}),
        "meta_k": ParagraphStyle("mk", **{**base, "fontName": med, "fontSize": 10,
                                          "leading": 15, "textColor": MUTED}),
        "meta_v": ParagraphStyle("mv", **{**base, "fontSize": 10, "leading": 15}),
    }


def inline(text: str) -> str:
    """**굵게**, `컬럼명`, [n] 참조 표시를 처리한다."""
    out = html.escape(text)
    out = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", out)
    # 백틱은 컬럼·파일명 표시용이다. 한글 고정폭 글꼴이 없으므로 기호를 지우고
    # 옅은 색으로만 구분한다. 백틱을 그대로 남기면 인쇄물에 그냥 문자로 찍힌다.
    out = re.sub(r"`([^`]+)`", r'<font color="#52514e">\1</font>', out)
    out = re.sub(r"\[(\d+)\]", r'<font color="#1c5cab">[\1]</font>', out)
    return out


# ── 본문 도식 ─────────────────────────────────────────────────────────────
class Diagram(Flowable):
    """벡터 도식의 공통 뼈대. 폭은 프레임에 맞추고 높이는 각자 정한다."""

    def __init__(self, height: float, font: str, font_b: str):
        super().__init__()
        self.width = AVAIL
        self.height = height
        self.font = font
        self.font_b = font_b

    def wrap(self, aw, ah):
        self.width = aw
        return (aw, self.height)

    def _txt(self, x, y, s, size=8.6, color=INK2, bold=False, anchor="start"):
        c = self.canv
        c.setFont(self.font_b if bold else self.font, size)
        c.setFillColor(color)
        if anchor == "middle":
            c.drawCentredString(x, y, s)
        elif anchor == "end":
            c.drawRightString(x, y, s)
        else:
            c.drawString(x, y, s)


class ClocksDiagram(Diagram):
    """세 개의 시계 — 심정지를 원점으로 둔 역행 시간축 위의 세 시점."""

    # 가로 위치는 본문이 서술하는 전형적 순서를 따른다: 생리가 먼저 움직이고,
    # 사람이 나중에 알아채고, 규칙은 더 나중에 울린다. §3.5 도식과 같은 좌표를 쓴다.
    ROWS = [
        ("T_phys", "생리 이탈", "환자 자신의 기준에서 활력징후가 벗어난 때", 0.20, ACCENT),
        ("T_rule", "규칙 발화", "조기경보점수가 대응 기준을 넘긴 때", 0.64, WARM),
        ("T_obs", "관측 강화", "활력징후 측정 간격이 짧아진 때", 0.42,
         colors.HexColor("#1baf7a")),
    ]

    def __init__(self, font, font_b):
        super().__init__(112, font, font_b)

    def draw(self):
        c = self.canv
        x0, x1 = 74.0, self.width - 12.0
        span = x1 - x0
        top = self.height - 14

        for i, (sym, name, desc, pos, colr) in enumerate(self.ROWS):
            y = top - i * 26
            c.setStrokeColor(RULE)
            c.setLineWidth(0.8)
            c.line(x0, y, x1, y)
            self._txt(x0 - 8, y - 3, sym, 8.8, colr, bold=True, anchor="end")
            px = x0 + span * pos
            c.setFillColor(colr)
            c.circle(px, y, 3.4, stroke=0, fill=1)
            c.setStrokeColor(colr)
            c.setLineWidth(1.8)
            c.line(px, y, x1 - 1, y)
            self._txt(px + 7, y + 5.5, name, 9.0, INK, bold=True)
            self._txt(px + 7, y - 8.5, desc, 8.2, MUTED)

        # 시간축
        ay = top - 3 * 26 - 6
        c.setStrokeColor(INK2)
        c.setLineWidth(1.0)
        c.line(x0, ay, x1, ay)
        for frac, label in ((0.0, "이르다"), (1.0, "심정지 (t=0)")):
            x = x0 + span * frac
            c.line(x, ay - 3, x, ay + 3)
            self._txt(x, ay - 13, label, 8.2, MUTED,
                      anchor="end" if frac else "start")
        self._txt(x0 + span / 2, ay - 13, "← 시간을 거꾸로 읽는다 →", 8.2, MUTED, anchor="middle")


class GapsDiagram(Diagram):
    """두 격차 — 탐지 격차와 인지 격차를 같은 축 위에 괄호로 표시."""

    def __init__(self, font, font_b):
        super().__init__(122, font, font_b)

    def _bracket(self, xa, xb, y, colr):
        c = self.canv
        c.setStrokeColor(colr)
        c.setLineWidth(1.4)
        c.line(xa, y, xb, y)
        for x in (xa, xb):
            c.line(x, y - 4, x, y + 4)

    def draw(self):
        c = self.canv
        x0, x1 = 20.0, self.width - 20.0
        span = x1 - x0
        pos = {"phys": 0.20, "obs": 0.42, "rule": 0.64}
        base = self.height - 26

        c.setStrokeColor(RULE)
        c.setLineWidth(0.9)
        c.line(x0, base, x1, base)
        for key, colr, label in (("phys", ACCENT, "생리 이탈"),
                                 ("obs", colors.HexColor("#1baf7a"), "관측 강화"),
                                 ("rule", WARM, "규칙 발화")):
            x = x0 + span * pos[key]
            c.setFillColor(colr)
            c.circle(x, base, 3.6, stroke=0, fill=1)
            self._txt(x, base + 9, label, 8.6, INK, bold=True, anchor="middle")
        c.setFillColor(INK)
        c.circle(x1, base, 3.0, stroke=0, fill=1)
        self._txt(x1, base + 9, "심정지", 8.6, INK, bold=True, anchor="end")

        xp = x0 + span * pos["phys"]
        xr = x0 + span * pos["rule"]
        xo = x0 + span * pos["obs"]

        y1 = base - 22
        self._bracket(xp, xr, y1, WARM)
        self._txt((xp + xr) / 2, y1 - 13, "탐지 격차", 8.8, INK, bold=True, anchor="middle")
        self._txt((xp + xr) / 2, y1 - 24, "생리가 움직인 뒤 규칙이 울리기까지", 8.0, MUTED,
                  anchor="middle")
        self._txt(x1, y1 - 13, "→ 임계값 재보정 대상", 8.2, WARM, anchor="end")

        y2 = base - 62
        self._bracket(xo, xp, y2, colors.HexColor("#1baf7a"))
        self._txt((xo + xp) / 2, y2 - 13, "인지 격차", 8.8, INK, bold=True, anchor="middle")
        self._txt((xo + xp) / 2, y2 - 24, "생리와 사람 사이의 시간차", 8.0, MUTED, anchor="middle")
        self._txt(x1, y2 - 13, "→ 부호가 양수면 구심로 실패", 8.2, colors.HexColor("#0f8a5f"),
                  anchor="end")


class WindowsDiagram(Diagram):
    """사례교차 설계 — 사례창 1개와 같은 환자의 대조창들."""

    def __init__(self, font, font_b):
        super().__init__(104, font, font_b)

    def draw(self):
        c = self.canv
        x0, x1 = 20.0, self.width - 20.0
        span = x1 - x0
        y = self.height - 40
        h = 17.0

        c.setStrokeColor(RULE)
        c.setLineWidth(0.9)
        c.line(x0, y - 9, x1, y - 9)

        # 대조창 (왼쪽, 이른 시간대)
        n_ctrl = 5
        cw = span * 0.085
        for i in range(n_ctrl):
            cx = x0 + i * (cw + span * 0.018)
            c.setFillColor(ACCENT_LIGHT)
            c.roundRect(cx, y, cw, h, 3, stroke=0, fill=1)
        self._txt(x0, y + h + 7, "대조창 — 같은 환자의 이전 6시간 구간들", 8.8, INK, bold=True)

        # 완충
        wash_x = x0 + n_ctrl * (cw + span * 0.018)
        wash_w = span * 0.30
        c.setFillColor(BAND)
        c.roundRect(wash_x, y, wash_w, h, 3, stroke=0, fill=1)
        self._txt(wash_x + wash_w / 2, y + h / 2 - 3, "완충 24시간", 8.2, MUTED, anchor="middle")

        # 사례창
        case_x = x1 - span * 0.115
        c.setFillColor(WARM)
        c.roundRect(case_x, y, span * 0.115, h, 3, stroke=0, fill=1)
        self._txt(case_x + span * 0.0575, y + h / 2 - 3, "사례창", 8.4, colors.white,
                  bold=True, anchor="middle")
        self._txt(x1, y + h + 7, "심정지 직전 6시간", 8.8, INK, bold=True, anchor="end")

        c.setStrokeColor(INK)
        c.setLineWidth(1.2)
        c.line(x1, y - 4, x1, y + h + 4)
        self._txt(x1, y - 19, "심정지", 8.4, INK, bold=True, anchor="end")
        self._txt(x0, y - 19, "입원", 8.4, MUTED)
        self._txt(x0, y - 35,
                  "같은 사람에게서 나온 창끼리 비교하므로 나이·기저질환·평소 혈압이 설계에서 상쇄된다.",
                  8.3, INK2)


class TimelineDiagram(Diagram):
    """본선 일정."""

    TASKS = [
        ("본선 진출 발표 · 패키지 목록 제출", 0.00, 0.06, MUTED),
        ("1~2회차 — 스키마 대조 · 전처리 확정", 0.07, 0.24, ACCENT),
        ("3~5회차 — 세 시계 · 유형 분해 · 사례교차", 0.25, 0.52, ACCENT),
        ("6회차 — 민감도 분석 · 1차 반출 신청", 0.53, 0.63, WARM),
        ("반출 심의 (1~2주, 지연 대비 여유 포함)", 0.63, 0.80, MUTED),
        ("7회차 — 잔여 분석 · 2차 반출 신청", 0.72, 0.82, WARM),
        ("결과보고서 · 발표자료 작성", 0.80, 0.96, colors.HexColor("#1baf7a")),
        ("본선 제출 마감 (11월 6일 16:00)", 0.96, 1.00, INK),
    ]

    def __init__(self, font, font_b):
        super().__init__(24 + 19 * len(TimelineDiagram.TASKS), font, font_b)

    def draw(self):
        c = self.canv
        lab_w = 224.0
        x0 = lab_w + 8
        x1 = self.width - 4
        span = x1 - x0
        top = self.height - 16

        c.setStrokeColor(RULE)
        c.setLineWidth(0.6)
        for frac, label in ((0.0, "9월"), (0.34, "10월 초"), (0.68, "10월 말"), (1.0, "11월 6일")):
            x = x0 + span * frac
            c.line(x, top + 6, x, top - 19 * len(self.TASKS) + 4)
            self._txt(x, top + 10, label, 7.8, MUTED,
                      anchor="middle" if 0 < frac < 1 else ("start" if frac == 0 else "end"))

        for i, (name, a, b, colr) in enumerate(self.TASKS):
            y = top - 8 - i * 19
            self._txt(lab_w, y - 3, name, 8.4, INK2, anchor="end")
            xa, xb = x0 + span * a, x0 + span * b
            c.setFillColor(colr)
            c.roundRect(xa, y - 6.5, max(xb - xa, 3.0), 11, 2.5, stroke=0, fill=1)


# ── 파서 ──────────────────────────────────────────────────────────────────
def build_table(rows: list[list[str]], st: dict) -> Table:
    """첫 줄을 머리행으로 쓴다. 빈 칸은 위 칸에 이어지는 것으로 본다(세로 병합 대용)."""
    ncol = max(len(r) for r in rows)
    # 열이 많으면 글자를 줄이고 폭을 고르게 나눈다. 첫 열만 넓게 두는 규칙을
    # 그대로 두면 10열짜리 표에서 나머지 열이 두 글자 폭으로 찌그러진다.
    wide = ncol >= 6
    size = 8.2 if wide else 9.4
    body = ParagraphStyle("cw", parent=st["cell"], fontSize=size, leading=size * 1.42)
    head = ParagraphStyle("chw", parent=st["cell_h"], fontSize=size, leading=size * 1.42)

    data = []
    for i, raw in enumerate(rows):
        cells = raw + [""] * (ncol - len(raw))
        data.append([Paragraph(inline(c), head if i == 0 else body) for c in cells])

    if wide:
        widths = [AVAIL / ncol] * ncol
    else:
        first = 0.22 * AVAIL
        rest = (AVAIL - first) / (ncol - 1) if ncol > 1 else AVAIL
        widths = [first] + [rest] * (ncol - 1)

    t = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, RULE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
    ]
    for i in range(2, len(data), 2):
        cmds.append(("BACKGROUND", (0, i), (-1, i), SURFACE))
    t.setStyle(TableStyle(cmds))
    return t


class Boxed(Flowable):
    """상자 안에 문단을 담는다. 강조(테두리)와 보조(음영) 두 가지."""

    def __init__(self, flows: list, kind: str):
        super().__init__()
        self.flows = flows
        self.kind = kind
        self.width = AVAIL
        self.pad = 9.0

    def wrap(self, aw, ah):
        self.width = aw
        inner = aw - 2 * self.pad - (5 if self.kind == "callout" else 0)
        h = self.pad * 2
        for f in self.flows:
            h += f.wrap(inner, ah)[1]
        self.height = h
        return (aw, h)

    def draw(self):
        c = self.canv
        if self.kind == "callout":
            c.setFillColor(colors.HexColor("#f4f8fd"))
            c.rect(0, 0, self.width, self.height, stroke=0, fill=1)
            c.setFillColor(ACCENT)
            c.rect(0, 0, 3.2, self.height, stroke=0, fill=1)
            left = self.pad + 5
        else:
            c.setFillColor(BAND)
            c.roundRect(0, 0, self.width, self.height, 3, stroke=0, fill=1)
            left = self.pad
        y = self.height - self.pad
        inner = self.width - 2 * self.pad - (5 if self.kind == "callout" else 0)
        for f in self.flows:
            h = f.wrap(inner, self.height)[1]
            y -= h
            f.drawOn(c, left, y)


def parse(md: str, st: dict, fonts: tuple[str, str]) -> list:
    lines = md.split("\n")
    flow: list = []
    i = 0
    n = len(lines)
    font, font_b = fonts

    def para(buf: list[str], style="p") -> None:
        if buf:
            flow.append(Paragraph(inline(" ".join(buf)), st[style]))
            buf.clear()

    buf: list[str] = []
    while i < n:
        line = lines[i].rstrip()
        stripped = line.strip()

        def block_until(tag: str) -> list[str]:
            nonlocal i
            out = []
            i += 1
            while i < n and lines[i].strip() != tag:
                out.append(lines[i].rstrip())
                i += 1
            i += 1
            return out

        if stripped.startswith("# "):
            para(buf)
            flow.append(Spacer(1, 52))
            flow.append(Paragraph(inline(stripped[2:]), st["cover_title"]))
            i += 1
            continue

        if stripped.startswith("## ") and not flow[:1]:
            pass  # 표지 부제는 아래 분기에서 처리

        if stripped == "@@PAGEBREAK":
            para(buf)
            flow.append(PageBreak())
            i += 1
            continue

        if stripped == "@@META":
            para(buf)
            rows = block_until("@@ENDMETA")
            data = []
            for r in rows:
                parts = [p.strip() for p in r.split("|")]
                if len(parts) < 2:
                    continue
                data.append([Paragraph(inline(parts[0]), st["meta_k"]),
                             Paragraph(inline(parts[1]), st["meta_v"])])
            t = Table(data, colWidths=[0.26 * AVAIL, 0.74 * AVAIL], hAlign="LEFT")
            t.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 4.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4.5),
                ("LEFTPADDING", (0, 0), (0, -1), 0),
                ("LINEBELOW", (0, 0), (-1, -2), 0.4, RULE),
            ]))
            flow.append(Spacer(1, 42))
            flow.append(t)
            continue

        if stripped == "@@TABLE":
            para(buf)
            rows = [[c.strip() for c in r.split("|")] for r in block_until("@@ENDTABLE") if r.strip()]
            flow.append(Spacer(1, 3))
            flow.append(build_table(rows, st))
            flow.append(Spacer(1, 9))
            continue

        if stripped == "@@FIGSPEC":
            para(buf)
            # 항목 전체를 먼저 합친 다음 서식을 적용한다. 줄 단위로 `inline()` 을
            # 부르면 **굵게** 가 줄을 넘어갈 때 여는 표시와 닫는 표시가 서로 다른
            # 호출에 들어가 짝이 맞지 않고, 별표가 그대로 인쇄된다.
            items: list[str] = []
            for r in block_until("@@ENDFIGSPEC"):
                if not r.strip():
                    continue
                if r.startswith("  ") and items:  # 이어지는 줄
                    items[-1] += " " + r.strip()
                else:
                    items.append(re.sub(r"^□\s*", "", r.strip()))
            for item in items:
                flow.append(Paragraph("□  " + inline(item), st["bullet"]))
            flow.append(Spacer(1, 6))
            continue

        if stripped in ("@@CALLOUT", "@@NOTE"):
            para(buf)
            kind = "callout" if stripped == "@@CALLOUT" else "note"
            rows = block_until("@@ENDCALLOUT" if kind == "callout" else "@@ENDNOTE")
            paras, acc = [], []
            for r in rows:
                if r.strip():
                    acc.append(r.strip())
                elif acc:
                    paras.append(Paragraph(inline(" ".join(acc)), st["callout"]))
                    acc = []
            if acc:
                paras.append(Paragraph(inline(" ".join(acc)), st["callout"]))
            flow.append(Spacer(1, 3))
            flow.append(Boxed(paras, kind))
            flow.append(Spacer(1, 10))
            continue

        if stripped == "@@FORMULA":
            para(buf)
            rows = [r.strip() for r in block_until("@@ENDFORMULA") if r.strip()]
            flow.append(Spacer(1, 5))
            for r in rows:
                flow.append(Paragraph(inline(r), st["formula"]))
            flow.append(Spacer(1, 10))
            continue

        if stripped.startswith("@@FIGURE "):
            para(buf)
            name = stripped.split(None, 1)[1].strip()
            cap = " ".join(r.strip() for r in block_until("@@ENDFIGURE") if r.strip())
            path = FIG_DIR / name
            group: list = []
            if path.exists():
                from PIL import Image as PILImage

                with PILImage.open(path) as im:
                    iw, ih = im.size
                w = AVAIL
                group.append(Image(str(path), width=w, height=w * ih / iw))
            else:
                group.append(Paragraph(f"[그림 없음: {name}]", st["caption"]))
            group.append(Paragraph(inline(cap), st["caption"]))
            flow.append(Spacer(1, 4))
            flow.append(KeepTogether(group))
            continue

        if stripped == "@@REFS":
            para(buf)
            rows = block_until("@@ENDREFS")
            acc: list[str] = []
            for r in rows:
                if re.match(r"^\[\d+\]", r.strip()) and acc:
                    flow.append(Paragraph(inline(" ".join(acc)), st["ref"]))
                    acc = []
                if r.strip():
                    acc.append(r.strip())
            if acc:
                flow.append(Paragraph(inline(" ".join(acc)), st["ref"]))
            continue

        if stripped in ("@@CLOCKS", "@@GAPS", "@@WINDOWS", "@@TIMELINE"):
            para(buf)
            cls = {"@@CLOCKS": ClocksDiagram, "@@GAPS": GapsDiagram,
                   "@@WINDOWS": WindowsDiagram, "@@TIMELINE": TimelineDiagram}[stripped]
            flow.append(Spacer(1, 6))
            flow.append(cls(font, font_b))
            flow.append(Spacer(1, 10))
            i += 1
            continue

        if stripped.startswith("### "):
            para(buf)
            flow.append(Paragraph(inline(stripped[4:]), st["h2"]))
            i += 1
            continue

        if stripped.startswith("## "):
            para(buf)
            is_cover = not any(isinstance(f, PageBreak) for f in flow)
            if is_cover:
                flow.append(Spacer(1, 10))
                flow.append(Paragraph(inline(stripped[3:]), st["cover_sub"]))
            else:
                flow.append(Spacer(1, 6))
                flow.append(Paragraph(inline(stripped[3:]), st["h1"]))
            i += 1
            continue

        if not stripped:
            para(buf)
            i += 1
            continue

        buf.append(stripped)
        i += 1

    para(buf)
    return flow


def make_decorator(fonts: tuple[str, str]):
    font, _ = fonts

    def on_page(canv, doc):
        canv.saveState()
        canv.setFont(font, 8.2)
        canv.setFillColor(MUTED)
        if doc.page > 1:
            canv.drawString(MARGIN, 12 * mm, "세 개의 시계 — 2026 K-Health 미개방 의료데이터 활용 경진대회")
            canv.drawRightString(A4[0] - MARGIN, 12 * mm, str(doc.page))
            canv.setStrokeColor(RULE)
            canv.setLineWidth(0.4)
            canv.line(MARGIN, 15.5 * mm, A4[0] - MARGIN, 15.5 * mm)
        canv.restoreState()

    return on_page


def main() -> None:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_IN
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_OUT
    ok = register_fonts()
    fonts = ("KR", "KR-B") if ok else ("Helvetica", "Helvetica-Bold")
    st = make_styles(ok)
    flow = parse(src.read_text(), st, fonts)

    doc = BaseDocTemplate(str(out), pagesize=A4,
                          leftMargin=MARGIN, rightMargin=MARGIN,
                          topMargin=18 * mm, bottomMargin=20 * mm,
                          title="세 개의 시계", author="")
    frame = Frame(MARGIN, 20 * mm, AVAIL, A4[1] - 38 * mm, id="body",
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate(id="main", frames=[frame],
                                       onPage=make_decorator(fonts))])
    doc.build(flow)

    from pypdf import PdfReader

    pages = len(PdfReader(str(out)).pages)
    verdict = "한도 이내" if pages <= PAGE_LIMIT else f"**한도 초과 {pages - PAGE_LIMIT}쪽**"
    print(f"{out} · {pages}쪽 / 한도 {PAGE_LIMIT}쪽 → {verdict}")


if __name__ == "__main__":
    main()
