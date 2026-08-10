/* K-Health 제안 설계 — React 18, JSX 없이 createElement 사용 (런타임 트랜스파일 불필요) */
(function () {
  var h = React.createElement;
  var useState = React.useState;
  var useMemo = React.useMemo;

  /* ─── 정수압 감쇠 모형 ─────────────────────────────────────────────
     Q(h) = k·(h − h_v),  dh = −dV/A
     실제/이론 = [(h₀−h_v)/Δ] · ln( (h₀−h_v)/(h₀−Δ−h_v) ),  Δ = V₀/A
     닫힌 해에 다이얼 conductance k가 소거된다 → 처방시간은 영향을 주지 않는다. */
  function ratio(poleCm, veinCm, hv, volMl, areaCm2) {
    var head = poleCm - veinCm - hv;
    var delta = volMl / areaCm2;
    var rem = head - delta;
    if (head <= 0 || delta <= 0) return null;
    if (rem <= 0) return Infinity; // 액면이 천자부 아래로 → 주입 정지
    return (head / delta) * Math.log(head / rem);
  }

  function pct(r) {
    if (r === null) return "—";
    if (!isFinite(r)) return "고갈";
    return (r - 1 >= 0 ? "+" : "") + ((r - 1) * 100).toFixed(1) + "%";
  }

  /* ─── 작은 조판 도우미 ──────────────────────────────────────────── */
  function Section(props) {
    return h("section", null, h("h2", null, props.title), props.children);
  }

  function Table(props) {
    return h(
      "div",
      { className: "scroll" },
      h(
        "table",
        null,
        props.caption ? h("caption", null, props.caption) : null,
        h(
          "thead",
          null,
          h(
            "tr",
            null,
            props.head.map(function (c, i) {
              return h("th", { key: i, className: c.num ? "num" : null }, c.label);
            })
          )
        ),
        h(
          "tbody",
          null,
          props.rows.map(function (row, ri) {
            return h(
              "tr",
              { key: ri },
              row.map(function (cell, ci) {
                var cls = [];
                if (props.head[ci] && props.head[ci].num) cls.push("num");
                if (cell && cell.tone) cls.push(cell.tone);
                return h(
                  "td",
                  { key: ci, className: cls.length ? cls.join(" ") : null },
                  cell && cell.node !== undefined ? cell.node : cell
                );
              })
            );
          })
        )
      )
    );
  }

  /* ─── 상호작용: 정수압 모형 계산기 ─────────────────────────────── */
  var SLIDERS = [
    { key: "vol", label: "수액 총량", unit: "mL", min: 50, max: 1000, step: 10, init: 250 },
    { key: "area", label: "백 유효 단면적", unit: "cm²", min: 15, max: 35, step: 1, init: 25 },
    { key: "vein", label: "천자부 높이", unit: "cm", min: 60, max: 110, step: 1, init: 80 },
    { key: "hv", label: "정맥압", unit: "cmH₂O", min: 4, max: 14, step: 1, init: 8 }
  ];

  function Calculator() {
    var initial = {};
    SLIDERS.forEach(function (s) { initial[s.key] = s.init; });
    var st = useState(initial);
    var v = st[0], setV = st[1];

    var out = useMemo(function () {
      var r150 = ratio(150, v.vein, v.hv, v.vol, v.area);
      var r200 = ratio(200, v.vein, v.hv, v.vol, v.area);
      var gap = (r150 && r200 && isFinite(r150) && isFinite(r200))
        ? ((r150 - r200) * 100).toFixed(1) + "%p" : "—";
      // 수액총량 스윕 → 곡선
      var pts = { p150: [], p200: [] };
      for (var vol = 50; vol <= 1000; vol += 10) {
        pts.p150.push([vol, ratio(150, v.vein, v.hv, vol, v.area)]);
        pts.p200.push([vol, ratio(200, v.vein, v.hv, vol, v.area)]);
      }
      return { r150: r150, r200: r200, gap: gap, pts: pts };
    }, [v.vol, v.area, v.vein, v.hv]);

    function set(key, val) {
      setV(function (prev) {
        var next = {};
        for (var k in prev) next[k] = prev[k];
        next[key] = Number(val);
        return next;
      });
    }

    /* SVG 곡선 — 세로축 0~40% 고정, 넘치면 클램프 */
    var W = 640, H = 210, PADL = 44, PADB = 28, PADT = 10, PADR = 12;
    var YMAX = 40;
    function sx(vol) { return PADL + ((vol - 50) / 950) * (W - PADL - PADR); }
    function sy(r) {
      var e = (r && isFinite(r)) ? (r - 1) * 100 : YMAX;
      if (e > YMAX) e = YMAX;
      if (e < 0) e = 0;
      return PADT + (1 - e / YMAX) * (H - PADT - PADB);
    }
    function path(arr) {
      return arr.map(function (p, i) {
        return (i ? "L" : "M") + sx(p[0]).toFixed(1) + " " + sy(p[1]).toFixed(1);
      }).join(" ");
    }

    var gridY = [0, 10, 20, 30, 40];
    var gridX = [250, 500, 750, 1000];

    return h(
      "div",
      { className: "calc" },
      h("div", { className: "calc-hd" },
        h("span", { className: "hd" }, "정수압 감쇠 모형 · 조작 가능"),
        h("p", { className: "calc-lede" },
          "수액백이 비어가면 액면이 내려가고 구동 정수압이 감소한다. 다이얼은 시작 시점에 맞춰지므로 실제 주입시간은 이론보다 길어진다. 값을 움직여 예측 편차가 어떻게 변하는지 확인한다.")
      ),

      h("div", { className: "readout" },
        h("div", { className: "ro" },
          h("span", { className: "ro-k" }, "150cm 폴"),
          h("span", { className: "ro-v lo" }, pct(out.r150))),
        h("div", { className: "ro" },
          h("span", { className: "ro-k" }, "200cm 폴"),
          h("span", { className: "ro-v hi" }, pct(out.r200))),
        h("div", { className: "ro" },
          h("span", { className: "ro-k" }, "군간 차이"),
          h("span", { className: "ro-v" }, out.gap))
      ),

      h("div", { className: "chart-wrap" },
        h("svg", {
          viewBox: "0 0 " + W + " " + H,
          className: "chart",
          role: "img",
          "aria-label": "수액 총량에 따른 예측 편차 곡선. 150cm 폴과 200cm 폴 비교."
        },
          gridY.map(function (g) {
            return h("g", { key: "gy" + g },
              h("line", { x1: PADL, x2: W - PADR, y1: sy(1 + g / 100), y2: sy(1 + g / 100), className: "grid" }),
              h("text", { x: PADL - 8, y: sy(1 + g / 100) + 3.5, className: "axis", textAnchor: "end" }, g + "%")
            );
          }),
          gridX.map(function (g) {
            return h("text", { key: "gx" + g, x: sx(g), y: H - 9, className: "axis", textAnchor: "middle" }, g);
          }),
          /* MDER 2025 실측 평균 4.75% 기준선 */
          h("line", { x1: PADL, x2: W - PADR, y1: sy(1.0475), y2: sy(1.0475), className: "ref" }),
          h("text", { x: W - PADR, y: sy(1.0475) - 6, className: "axis ref-t", textAnchor: "end" },
            "MDER 2025 실측 평균 4.75%"),
          h("path", { d: path(out.pts.p150), className: "c150" }),
          h("path", { d: path(out.pts.p200), className: "c200" }),
          h("circle", { cx: sx(v.vol), cy: sy(out.r150), r: 4, className: "dot150" }),
          h("circle", { cx: sx(v.vol), cy: sy(out.r200), r: 4, className: "dot200" }),
          h("text", { x: PADL + 6, y: PADT + 11, className: "axis" }, "예측 편차")
        ),
        h("div", { className: "legend" },
          h("span", null, h("i", { className: "sw sw150" }), "150cm 폴"),
          h("span", null, h("i", { className: "sw sw200" }), "200cm 폴"),
          h("span", null, h("i", { className: "sw swref" }), "기존 실측 평균"),
          h("span", { className: "legend-x" }, "가로축 = 수액 총량(mL)")
        )
      ),

      h("div", { className: "sliders" },
        SLIDERS.map(function (s) {
          return h("label", { key: s.key, className: "slider" },
            h("span", { className: "s-top" },
              h("span", { className: "s-lab" }, s.label),
              h("span", { className: "s-val" }, v[s.key] + " " + s.unit)),
            h("input", {
              type: "range",
              min: s.min, max: s.max, step: s.step,
              value: v[s.key],
              onChange: function (e) { set(s.key, e.target.value); }
            })
          );
        })
      ),

      h("p", { className: "calc-foot" },
        "기본값(250 mL · 25 cm² · 천자부 80 cm · 정맥압 8)에서 200cm 폴의 예측 편차는 ",
        h("strong", null, "+4.7%"),
        "다. 건양대병원이 독립적으로 보고한 실측 평균은 ",
        h("strong", null, "4.75%"),
        "다. 파라미터를 맞춰 넣은 것이 아니라 통상적인 항암주사실 조건을 넣은 결과다. ",
        "단일 점 일치는 검증이 아니므로 주장은 “같은 크기를 재현했다”까지만 한다."
      )
    );
  }

  /* ─── 상호작용: 확인 사항 체크리스트 ───────────────────────────── */
  var TODOS = [
    ["“신유량조절기”가 MDER 2025의 AccuValve(Hanvit MD)와 동일 기기인가.", "설명서에 기기명이 없다. 동일하면 중복 회피가 더 중요해지고, 다르면 기기 비교 축이 열린다 — 어느 쪽이든 여섯 공백은 유효하다."],
    ["건양대 의료데이터연구단 문의 — 042-600-6801 / 602625@kyuh.ac.kr", "대회 안내의 602626과 다르므로 둘 다 시도."],
    ["식약처 의약품 제품 허가정보 OpenAPI 활용신청 후 실호출", "용법용량 전문이 반환되는지. 실패해도 openFDA가 1차 골격이라 치명적이지 않다."],
    ["병원간호사회에 지침 인덱싱 이용 문의", "명시적 재이용 허락이 없어 제안서에는 “이용 협의 예정”으로 기재한 상태."],
    ["Gemini 3.1 Flash-Lite 사양·단가 재조사", "2.5에서 전환을 확정했으므로."],
    ["MDER 2025 전문 확보 — Table 1/2 상세 수치", "표 내부 수치는 아직 신뢰 복원 불가."],
    ["심평원에 전동식 주입펌프 수가 유무 문의", "현재는 “급여 범위가 좁다”까지만 주장하므로 없어도 성립."]
  ];

  function Checklist() {
    var st = useState({});
    var done = st[0], setDone = st[1];
    var n = Object.keys(done).filter(function (k) { return done[k]; }).length;
    return h("div", { className: "todo-wrap" },
      h("div", { className: "todo-count" },
        h("span", { className: "num" }, n + " / " + TODOS.length), " 확인 완료"),
      h("ul", { className: "todo" },
        TODOS.map(function (t, i) {
          var isDone = !!done[i];
          return h("li", { key: i, className: isDone ? "is-done" : null },
            h("button", {
              type: "button",
              className: "check",
              "aria-pressed": isDone,
              onClick: function () {
                setDone(function (p) {
                  var nx = {}; for (var k in p) nx[k] = p[k];
                  nx[i] = !p[i]; return nx;
                });
              }
            }, isDone ? "✓" : ""),
            h("span", { className: "t-body" },
              h("strong", null, t[0]),
              h("span", { className: "t-note" }, t[1]))
          );
        })
      )
    );
  }

  /* ─── 상호작용: 참신성 주장 범위 ───────────────────────────────── */
  var CLAIMS = {
    yes: [
      "실환자 항암 주입에서 3요인 교호작용을 추정하는 유일한 설계 — 확인된 8편 중 어느 것도 높이 × 주입시간 × 수액종류를 교차시키지 않았다",
      "조건별 기대편차 노모그램은 세계적으로 없다. ISMP 배포 B.Braun 차트는 mL/hr → drops/min 환산뿐이고, 높이에 대해서는 “Alterations of bag height … will affect flow rate”라는 경고 한 문장만 있다",
      "정규화 없이는 조회가 불가능하다는 구조적 필요",
      "in vitro–in vivo 갭을 메운다 — Atanda 2023: “No studies reported on patient safety outcomes”"
    ],
    no: [
      "“최초의 가이드라인 RAG” · “센서-RAG 결합 최초” · “측정값 구동 검색 최초”",
      "“수액 높이가 유량에 영향을 주는가” 검증 — 이미 확립된 사실",
      "수액종류(NS vs 5% D/W)를 주 가설로 — MDER 2025에서 이미 무의미로 판정",
      "“국내 최초/유일” — 부재 확인은 전수조사가 아니다",
      "중력식 정확도 기술통계 — 주관기관이 이미 발표"
    ]
  };

  function Claims() {
    var st = useState("yes");
    var tab = st[0], setTab = st[1];
    return h("div", { className: "claims" },
      h("div", { className: "tabs", role: "tablist" },
        h("button", {
          type: "button", role: "tab", "aria-selected": tab === "yes",
          className: "tab" + (tab === "yes" ? " on yes" : ""),
          onClick: function () { setTab("yes"); }
        }, "주장한다"),
        h("button", {
          type: "button", role: "tab", "aria-selected": tab === "no",
          className: "tab" + (tab === "no" ? " on no" : ""),
          onClick: function () { setTab("no"); }
        }, "쓰지 않는다")
      ),
      h("ul", { className: "claim-list " + tab },
        CLAIMS[tab].map(function (c, i) { return h("li", { key: i }, c); })
      )
    );
  }

  /* ─── 3층 구조 ─────────────────────────────────────────────────── */
  var LAYERS = [
    ["1층", "안심존 내부 · 폐쇄망 · 4시간 완주", "오차 지도.", " 데이터 품질 진단 → 군간 공변량 균형 확인(between-subject 배정이므로 교란 가능) → 8군 오차 분포와 3요인 교호작용 → 조건별 기대편차 예측식 → 오차 부호 편향 분해"],
    ["2층", "안심존 외부 · 공개 문서만 · Gemini API", "정규화 + 근거 검색.", " 오염된 22개 문자열 → 표준 성분 12개(전수 수작업 검증) → 성분별 권고 주입 조건 검색 → 인용 없이는 판정하지 않는 abstain 설계"],
    ["3층", "결합 · 산출물", "노모그램과 허용 판정.", " 조건별 기대편차 노모그램 · 약물별 허용범위 대조표 · 오차 결정요인 지도"]
  ];

  /* ─── 발견 카드 ────────────────────────────────────────────────── */
  function Finding(props) {
    return h("article", { className: "finding" + (props.ok ? " ok" : "") },
      h("span", { className: "tag" }, props.tag),
      h("h3", null, props.title),
      props.children
    );
  }

  /* ─── 페이지 ───────────────────────────────────────────────────── */
  function App() {
    return h("div", { className: "shell" },
      h("div", { className: "rail", "aria-hidden": "true" },
        h("div", { className: "rail-line" }, h("span", { className: "rail-cap" }, "150 — 200 cm"))),

      h("main", null,
        /* 머리 */
        h("header", null,
          h("div", { className: "eyebrow" }, "2026 K-Health 미개방 의료데이터 활용 경진대회 · 예선 제안 설계"),
          h("h1", null, "±10%는 그 약에 괜찮은가"),
          h("p", { className: "sub" }, "항암 수액 주입 오차의 조건별 지도와 근거 기반 허용 판정. 오차의 크기를 다투지 않고, 오차의 허용 여부를 다툰다."),
          h("div", { className: "dataset" },
            h("span", { className: "lbl" }, "선택 데이터셋"),
            h("strong", null, "[대전] 건양대학교의료원 — 신유량조절기 수액치료 데이터"),
            h("br"),
            "환자 100명 · 실험 120회 · 23컬럼 · 8군 완전요인설계",
            h("span", { className: "num" }, " (수액높이 150·200cm × 처방시간 30·60·90·120분 × 수액종류 NS·5% D/W, 군당 15회)")
          ),
          h("div", { className: "meta" },
            h("span", null, "작성 2026-07-30"),
            h("span", null, "예선 마감 2026-08-14 16:00"),
            h("span", null, "PDF 30장 이내"),
            h("span", null, "본선 15팀")
          )
        ),

        /* 전환 */
        h(Section, { title: "데이터셋이 바뀌었다 — 세 제약이 같은 방향을 가리켰다" },
          h("p", null, "이전 설계는 관상동맥석회화 CT(320명 페어)로 “CAC 판정 신뢰도 지도”를 만드는 것이었다. 세 가지 확정 사항이 그 설계를 성립 불가능하게 만들었다."),
          h(Table, {
            caption: "제약 변경과 그 결과",
            head: [{ label: "제약" }, { label: "결과" }],
            rows: [
              [{ node: h("strong", null, "예선 안심존 방문 안 함") },
               { node: h(React.Fragment, null, "가점 5점 미획득. 그리고 ", h("strong", null, "데이터 실물을 영원히 못 본다"), " — 설명서에 없는 사실은 주장할 수 없고, 리스크 대응에 “방문해서 확인”을 쓸 수 없다. CAC 설계는 리스크 대응 전체가 예선 실측에 걸려 있었다.") }],
              [{ node: h("strong", null, "본선 방문 1회 (월차)") },
               { node: h(React.Fragment, null, "실질 분석 4시간. CT 320명 × 2시리즈 × 수백 슬라이스는 ", h("strong", null, "로딩만으로 세션이 끝난다"), ". 120행 표는 실행 수 초, 재분석 여유까지 있다.") }],
              [{ node: h("strong", null, "딥러닝 대신 RAG") },
               { node: h(React.Fragment, null, "영상 분류와 결이 맞지 않는다. 그리고 RAG 층이 이 데이터셋의 ", h("strong", null, "유일한 약점(120행 규모)을 정확히 메운다"), " — 산출물 본체를 데이터 규모가 결정하지 않게 된다.") }]
            ]
          }),
          h("p", { className: "note" }, "참신성 측면에서도 오히려 낫다. CAC는 선행연구가 두껍고 FDA 승인 제품까지 나와 있어 “이미 있잖아요”를 방어하는 데 제안서 2장을 써야 했다.")
        ),

        /* 세 발견 */
        h(Section, { title: "조사에서 나온 세 가지 치명적 사실" },
          h("p", null, "이 셋을 모르고 제안서를 냈으면 심사에서 깨졌다."),
          h("div", { className: "findings" },
            h(Finding, { tag: "주관기관이 이 데이터로 이미 논문을 냈다", title: "건양대병원이 같은 시기·같은 설계로 정확도 논문을 출판했다" },
              h("blockquote", { className: "cite" }, "Choi JG, Yang DW, Park YG, Kim JY, Park P. Accuracy of Gravity-Based Automatic Infusion System for Chemoport Intravenous Infusion. Medical Devices: Evidence and Research. 2025;18. doi:10.2147/MDER.S495996"),
              h("p", null, "암환자 59명·측정 100회, 수집 2023.10~2024.01, 평균 오차율 ", h("span", { className: "num hi" }, "4.75%"), "·최대편차 ", h("span", { className: "num" }, "14.7%"), ". ", h("strong", null, "본 데이터셋의 수집기간(2023.11.29~12.15)이 이 논문 기간 안쪽에 있다."), " 건양대학교의료원은 이 대회의 주관기관이다 — 심사위원이 모를 가능성은 낮다."),
              h("p", null, "따라서 정확도 재측정은 전면 중복이다. 대신 ", h("strong", null, "이 논문이 남긴 여섯 공백"), "에 제안을 앉힌다: 높이를 실험 인자로 조작하지 않음 · 교호작용 미추정 · 고유량(>150 mL/h) 구간만 측정(저자 자진 명시) · 구간별 오차 크기표 없음 · 약제를 2범주로만 분류 · 오차 부호 편향 미분해.")
            ),
            h(Finding, { tag: "약관이 임상 사용을 명문으로 금지한다", title: "Gemini API로는 “임상 의사결정 지원”을 만들 수 없다" },
              h("blockquote", { className: "cite" }, "“You may not use the Services in clinical practice, to provide medical advice, or in any manner that is overseen by or requires clearance or approval from a medical device regulatory agency.” — Gemini API Terms, 2026-04-28"),
              h("p", null, "회피 불가한 약관 사실이므로 ", h("strong", null, "프레이밍 자체를 바꿨다"), ": 산출물은 ", h("em", null, "연구·교육용 근거 탐색 프로토타입"), "이며, 약물 단위의 일반적 허가사항 조회에 한정하고, 환자 개별 판단을 하지 않는다. 판정을 자동 실행하지 않고 사람이 최종 판단한다."),
              h("p", null, "덤으로 ", h("code", null, "gemini-2.5-flash-lite"), "는 ", h("strong", null, "2026-10-16 퇴역 예정"), "이다 — 본선 마감(11/6) 전이다. 게다가 File Search 미지원. ", h("strong", null, h("code", null, "gemini-3.1-flash-lite"), "로 전환하면 두 문제가 동시에 해결된다."))
            ),
            h(Finding, { ok: true, tag: "설명서 원문에서 발견 — 참신성 최강 카드", title: "약물명이 오염되어 있다. 정규화 없이는 조회가 불가능하다" },
              h("p", null, "설명서의 항암제 값은 ", h("strong", null, "22개 문자열인데 실제로는 12개 성분"), "이다."),
              h("div", { className: "dirty" },
                [["Pembrolizumab", ["pembrolizumab", "Pembrolizumb", "Perbrolizumab"]],
                 ["Oxaliplatin", ["Oxailplatin", "Oxaliplati", "Oxaliplatin"]],
                 ["Cisplatin", ["Cisplain", "Cisplatin", "Cisplatine"]],
                 ["Bevacizumab", ["BevaciZumab", "Bevacizumb"]],
                 ["Trastuzumab deruxtecan", ["Trastuzumab-Deruxt"]]].map(function (row, i) {
                  return h("div", { className: "dirty-row", key: i },
                    h("span", { className: "dirty-true" }, row[0]),
                    h("span", { className: "dirty-vals" },
                      row[1].map(function (s, j) { return h("code", { key: j }, s); }))
                  );
                })
              ),
              h("p", null, h("strong", null, "어떤 의약품 데이터베이스도 ", h("code", null, "Perbrolizumab"), "을 조회하지 못한다."), " 즉 이 데이터를 약물 근거에 연결하는 일 자체가 의미 기반 정규화를 전제한다. “왜 LLM이 필요한가”에 대한 답이 여기 있다 — 성능 향상 장치가 아니라 ", h("strong", null, "연결 가능성의 전제 조건"), "이다."),
              h("p", null, "그리고 22개는 ", h("strong", null, "전수 수작업 검증이 가능한 크기"), "다. 정규화 정확도를 100% 사람이 확인해 보고할 수 있으므로 환각 리스크를 제안서에서 정면으로 닫는다.")
            )
          ),
          h("h3", null, "그리고 하나의 함정을 피했다"),
          h("p", null, "설명서 서술부는 “부작용 발생 여부를 측정”한다고 ", h("strong", null, "세 번"), " 언급한다. 그런데 데이터 포맷 23개 컬럼에 부작용이 없고, 통계 절에는 “부작용 발생률은 연구 제외 기준을 적용하여 ", h("strong", null, "최소화"), "하였습니다”라고 적혀 있다. 서술만 믿고 “오차 → 부작용 연관 분석”을 설계했다면 본선에서 데이터를 열었을 때 무너졌다.")
        ),

        /* 3층 */
        h(Section, { title: "제안 구조 — 폐쇄망이 아키텍처를 결정한다" },
          h("p", null, "안심존은 완전 폐쇄망이므로 클라우드 API를 호출할 방법이 없다. 분리 구조는 선택이 아니라 필연이고, 그 결과 ", h("strong", null, "환자 데이터가 외부로 나가지 않는 것이 정책이 아니라 물리적 보장"), "이 된다."),
          h("div", { className: "stack" },
            LAYERS.map(function (L, i) {
              return h(React.Fragment, { key: i },
                h("div", { className: "layer" },
                  h("span", { className: "n" }, L[0]),
                  h("span", { className: "where" }, L[1]),
                  h("span", { className: "what" }, h("strong", null, L[2]), L[3])),
                i === 0 ? h("div", { className: "flowgap" }, "↓ 반출 심의를 통과한 계수·요약통계·그림만")
                  : (i === 1 ? h("div", { className: "flowgap" }, "↓") : null)
              );
            })
          ),
          h("p", { className: "note" }, "심사위원이 던질 가장 날카로운 한 문장 — “결국 공개된 허가사항을 검색하는 건데 식약처 홈페이지에서 찾는 것과 뭐가 다릅니까?” 답: 차별점은 검색이 아니라 ", h("strong", null, "측정값이 질의를 생성하는 자동 연결"), "과 ", h("strong", null, "정량 임계 판정"), "이다. “이 약의 용법용량은?”이 아니라 “실측 유량이 처방 대비 +20%일 때 이 약물의 허가사항상 허용 가능한가”를 답한다.")
        ),

        /* 계산기 */
        h(Section, { title: "사전 검증 ① — 물리 모형이 기존 실측치를 재현했다" },
          h("p", null, "예선 방문을 하지 않으므로 데이터로는 아무것도 사전 검증할 수 없다. 대신 유체역학에서 ", h("strong", null, "방향과 크기를 가진 예측"), "을 도출했다. 닫힌 해는 수치적분과 1e−13 수준에서 일치한다."),
          h(Calculator),
          h(Table, {
            caption: "검증 가능한 사전 예측 — 방문 당일 그 자리에서 대조한다",
            head: [{ label: "#", num: true }, { label: "예측" }, { label: "선행연구 상태" }],
            rows: [
              ["P1", "150cm군 오차 > 200cm군, 차이 약 4~11%p", { node: h(React.Fragment, null, "효과 존재는 확립(Atanda 2023), ", h("strong", null, "크기는 미측정")) }],
              ["P2", { node: h(React.Fragment, null, h("strong", null, "수액 총량이 오차의 강한 예측 변수"), " — 8군 설계의 실험 인자가 아닌데도. ", h("code", null, "Δ = V₀/A"), "에서 직접 나오고, 컬럼으로 존재한다(10번 수액총량, 11번 항암제+수액)") },
               { node: "선행연구 없음 — 가장 강한 카드", tone: "lo" }],
              ["P3", { node: h(React.Fragment, null, "처방시간 주효과는 정수압으로 설명되지 않는다 — 닫힌 해에서 다이얼 conductance ", h("code", null, "k"), "가 ", h("strong", null, "소거"), "된다") }, "원인 분리 시도 없음"],
              ["P4", "오차 부호는 대부분 양(+) — 유량은 감소만 한다", "부호 편향 분해 없음"],
              ["P5", "높이 × 수액총량 교호작용 존재", "교호작용 추정 없음"],
              ["P6", { node: h(React.Fragment, null, "관측 오차와 모형 예측의 차이 = ", h("strong", null, "기기 보정 성능")) }, "개념 자체가 새롭다"]
            ]
          }),
          h("p", null, "P3에는 반대 방향으로 작용하는 경쟁 가설이 있다. 분 단위 기록 양자화는 ±1분 오차가 30분 처방에서 ", h("span", { className: "num" }, "3.33%"), ", 120분에서 ", h("span", { className: "num" }, "0.83%"), "다 — ", h("strong", null, "짧은 주입에서 크다"), ". 정수압·다이얼 효과는 긴 주입에서 크다. ", h("strong", null, "두 효과가 반대 방향이므로 교란 분리가 필수"), "이고, 이걸 미리 짚어두는 것 자체가 분석 설계의 신뢰도를 만든다."),
          h("h3", null, "기기가 자동 보정하더라도 설계가 무너지지 않는다"),
          h("p", null, "MDER 2025의 제목은 “Gravity-Based ", h("strong", null, "Automatic"), " Infusion System”이다. 기기가 수두 감소를 보정할 가능성이 있다. 이걸 약점으로 두지 않고 분석 축으로 삼는다 — ", h("strong", null, "모형은 보정이 없을 때를 예측하므로, 관측과 모형의 차이가 곧 보정 성능이다."), " 높이 효과가 예측대로면 노모그램이 필요하고, 작으면 보정 잔차를 정량화한 최초 결과이며, 사라지면 “왜 지침은 여전히 높이를 경고하는가”가 새 질문이 된다. ", h("strong", null, "세 경우 모두 보고서가 완성된다."))
        ),

        /* 파이프라인 실행 */
        h(Section, { title: "사전 검증 ② — 파이프라인을 실제로 돌렸다" },
          h("p", null, "설명서에 실린 약물명 문자열만으로 정규화 → 근거검색 → 대조를 끝까지 실행했다. ", h("strong", null, "데이터 실물이 없어도 재현되므로 예선 방문과 무관하다."), " 표준 라이브러리만 쓰고 외부 의존성이 없다."),

          h("div", { className: "kpis" },
            h("div", { className: "kpi" }, h("span", { className: "kpi-v hi" }, "22 → 12"), h("span", { className: "kpi-k" }, "오염 문자열 → 표준 성분")),
            h("div", { className: "kpi" }, h("span", { className: "kpi-v hi" }, "0건"), h("span", { className: "kpi-k" }, "정규화 실패")),
            h("div", { className: "kpi" }, h("span", { className: "kpi-v" }, "12 / 12"), h("span", { className: "kpi-k" }, "허가사항 조회 성공"))
          ),

          h("h3", null, "RxNorm이 오타를 전부 잡았다"),
          h("p", null, "무료·무인증 API인 RxNorm ", h("code", null, "approximateTerm"), "이 철자 오류를 정확히 매칭했다. 정규화가 LLM 없이도 공개 표준으로 ", h("strong", null, "교차검증 가능"), "하다는 뜻이라, 환각 방어 논거가 하나 더 생긴다."),
          h(Table, {
            caption: "정규화 결과 발췌 · 2026-07-30 실행",
            head: [{ label: "설명서 표기" }, { label: "→ 표준 성분" }, { label: "rxcui", num: true }, { label: "score", num: true }],
            rows: [
              [{ node: h("code", null, "Perbrolizumab") }, "pembrolizumab", "1547545", "10.6"],
              [{ node: h("code", null, "Oxailplatin") }, "oxaliplatin", "32592", "8.2"],
              [{ node: h("code", null, "Cisplain") }, "cisplatin", "2555", "8.8"],
              [{ node: h("code", null, "Bevacizumb") }, "bevacizumab", "253337", "8.0"],
              [{ node: h("code", null, "Nivolumab 옵디보주") }, "nivolumab", "1597876", "13.4"],
              [{ node: h("code", null, "Trastuzumab-Deruxt") }, "trastuzumab deruxtecan", "2267582", "12.8"]
            ]
          }),

          h("h3", null, "★ 그리고 순진한 검색이 왜 실패하는지 실증했다"),
          h("p", null, "이번 실행의 진짜 소득이다. 가설이 아니라 직접 돌려서 확인했고, ", h("strong", null, "LLM 층이 무엇을 해야 하는지를 명세로 바꿔준다."), " 셋 중 둘은 기계적으로 고쳤고, 나머지 하나는 고칠 수 없다."),
          h(Table, {
            caption: "실증된 세 가지 실패 모드",
            head: [{ label: "실패" }, { label: "증상" }, { label: "처리" }],
            rows: [
              [{ node: h("strong", null, "A. 투여 경로 혼입") },
               { node: h(React.Fragment, null, "성분명만으로 조회하면 ", h("strong", null, "피하주사 제형"), " 라벨이 잡힌다. pembrolizumab ", h("span", { className: "num lo" }, "1~2분"), ", nivolumab ", h("span", { className: "num lo" }, "3~5분"), " — 실제 IV는 둘 다 ", h("span", { className: "num hi" }, "30분"), ". 10~30배 틀린 기준값") },
               { node: h(React.Fragment, null, h("code", null, 'route:"INTRAVENOUS"'), " 한정 → 해결") }],
              [{ node: h("strong", null, "B. 접합체가 모체로 붕괴") },
               { node: h(React.Fragment, null, h("code", null, "Trastuzumab-Deruxt"), " → 성분 추출 시 ", h("code", null, "trastuzumab"), "이 된다. T-DXd는 다른 약이고 주입시간도 다르다(첫 회 90분, 이후 30분)") },
               "개념명 토큰 수 비교로 보정 → 해결"],
              [{ node: h("strong", null, "C. 병용요법 귀속 오류"), tone: "lo" },
               { node: h(React.Fragment, null, "항암 라벨은 ", h("strong", null, "병용요법 전체"), "를 서술한다. oxaliplatin에서 뽑힌 ", h("span", { className: "num lo" }, "2~4분"), "은 사실 fluorouracil bolus, irinotecan의 ", h("span", { className: "num lo" }, "1320분"), "은 5-FU 지속주입이다") },
               { node: h("strong", null, "기계적으로 불가. 문장의 의미를 이해해야 한다"), tone: "lo" }]
            ]
          }),
          h("p", { className: "note" }, h("strong", null, "이래서 LLM이 필요한 이유가 두 개가 됐다."), " ① 오염된 약물명 정규화 — 조회 자체의 전제 조건. ② ", h("strong", null, "병용요법 서술에서 해당 성분에 귀속되는 주입 조건만 골라내기"), " — 순진한 파이프라인을 실제로 돌려 실패를 확인했기 때문에 나온 논거다. “LLM을 왜 쓰나”에 대한 가장 강한 답변이다."),

          h("h3", null, "처방시간 대조표 (경로 한정 후)"),
          h(Table, {
            caption: "허가사항 권고 대비 데이터의 처방시간 · 적합 14 / 이탈 30",
            head: [{ label: "성분" }, { label: "IV 권고(분)", num: true }, { label: "30분", num: true }, { label: "60분", num: true }, { label: "90분", num: true }, { label: "120분", num: true }],
            rows: [
              ["bevacizumab", "30, 60, 90", "적합", "적합", "적합", "이탈"],
              ["cetuximab", "60", "이탈", "적합", "이탈", "이탈"],
              ["cisplatin", "360", "이탈", "이탈", "이탈", "이탈"],
              ["gemcitabine", "30", "적합", "이탈", "이탈", "이탈"],
              ["irinotecan", "90, 120", "이탈", "이탈", "적합", "적합"],
              ["leucovorin", "240", "이탈", "이탈", "이탈", "이탈"],
              ["nivolumab", "30", "적합", "이탈", "이탈", "이탈"],
              ["oxaliplatin", "120", "이탈", "이탈", "이탈", "적합"],
              ["pembrolizumab", "30", "적합", "이탈", "이탈", "이탈"],
              ["ramucirumab", "30, 60", "적합", "적합", "이탈", "이탈"],
              ["trastuzumab deruxtecan", "30, 90", "적합", "이탈", "적합", "이탈"]
            ]
          }),
          h("p", { className: "note" }, h("strong", null, "해석 주의 — “이탈”은 그 처방이 틀렸다는 뜻이 아니다."), " 실제 임상에서는 병용 regimen·환자 상태·기관 프로토콜에 따라 라벨과 다른 주입시간을 쓰는 것이 정상이다. 이 표가 말하는 것은 라벨 권고와 처방시간이 어긋나는 조합이 흔하다는 것이고, ", h("strong", null, "거기에 실측 편차가 더해질 때 어떻게 되는지가 실제 질문"), "이라는 점이다. 제안서에서 “처방이 틀렸다”로 쓰면 임상 심사위원에게 즉시 반박당하므로 ", h("strong", null, "편차 이전의 기준선"), "으로만 쓴다."),
          h("p", null, "코퍼스 라이선스는 openFDA가 ", h("strong", null, "CC0 퍼블릭 도메인"), ", RxNorm은 무료·무인증이다. 국내 코퍼스(식약처 허가정보 OpenAPI — 이용허락범위 제한 없음)는 보강분이고, 병원간호사회 말초정맥 주입요법 지침은 명시적 재이용 허락이 없어 “", h("strong", null, "이용 협의 예정"), "”으로 기재한다. 국가암정보센터·약학정보원·ONS·KIMS는 저작권·약관상 인덱싱하지 않는다.")
        ),

        /* 참신성 */
        h(Section, { title: "참신성 — 주장할 것과 주장하지 않을 것" },
          h("p", null, "“측정값 → 검색질의 → 근거 판정” 패턴 자체는 참신하지 않다. ", h("strong", null, "조사로 반증됐다."), " FHIR-RAG-MEDS(arXiv 2509.07706)가 이미 정형 환자데이터로 가이드라인을 검색하고, MEREDITH(JCO PO)는 ", h("strong", null, "Gemini 기반"), " 종양학 RAG이며, GC녹십자 RegulAItor는 국내 제약 규제업무 RAG를 실전 배치했다."),
          h(Claims),
          h("p", null, "참신성 문구는 이 수준까지만 쓴다 — “항암제 정맥주입의 실측 유량 편차를 입력으로 하여 허가사항·간호실무지침 코퍼스에 검색질의를 자동 생성하고 인용 가능한 허용범위 판정을 반환하는 파이프라인의 ", h("strong", null, "적용 사례"), "”.")
        ),

        /* 시의성 */
        h(Section, { title: "시의성 — 검증된 숫자만" },
          h(Table, {
            caption: "1차 출처를 직접 확인한 근거",
            head: [{ label: "근거" }, { label: "값", num: true }, { label: "출처" }],
            rows: [
              [{ node: h("strong", null, "투약 관련 환자안전사고 비중") }, { node: "50.9%", tone: "hi" }, "11,257 / 22,118건, 전년比 +11.6% — 의료기관평가인증원 「2024 환자안전 연례보고서」"],
              [{ node: h("strong", null, "KOPS 주의경보 중 항암제·주입속도") }, { node: "0건", tone: "lo" }, "57차 전체 전수 확인(최신 2026-07-21). 정부가 투약 안전에 반복 경보를 발령했으나 이 영역만 비어 있다"],
              ["급여 인정 조건", "2일 이상 + 중심정맥", { node: h(React.Fragment, null, "보건복지부 고시 2021-263호. ", h("strong", null, "단시간 말초정맥 외래 항암 주입은 급여 범위 밖")) }],
              ["말초정맥 주입요법 지침 근거수준 III", "47.9%", { node: h(React.Fragment, null, "284개 권고 중 136개. 항암제 주입 권고 10개 중 ", h("strong", null, "투약오류 예방은 1개"), " — 정인숙 등, 임상간호연구 2025;31(1)") }],
              ["암유병자", "273만 2,906명", "국민 19명당 1명 — 「2023년 국가암등록통계」, 2026-01-20"],
              ["중력식 유량조절기 규제", "대응 규격 없음", "주입펌프는 IEC 60601-2-24로 규율. 식약처 용역(TRKO201700017689)도 펌프만 다룬다"],
              ["질의 비용", "약 0.8원", "공식 단가 기준 자체 계산. 1,000질의 약 800원 — 비용은 리스크가 아니다"]
            ]
          }),
          h("p", { className: "note" }, h("strong", null, "피한 함정:"), " “한국 간호사 1인당 환자 13명 vs OECD 8명”은 1차 출처가 없다. OECD Health at a Glance 2025의 간호사 밀도는 한국 ", h("span", { className: "num" }, "9.5"), " vs OECD ", h("span", { className: "num" }, "9.2"), "로 ", h("strong", null, "한국이 상회"), "하므로, 간호인력 부족 논거로 쓰면 반박당한다. 의사 2.7 vs 3.9 논거만 쓴다."),
          h("p", null, "정책 타임라인이 맞는다 — 제5차 암관리종합계획(2026-02-24 의결)의 ", h("strong", null, "국가암AI·데이터센터"), " 확대 개편, 2026년 ", h("strong", null, "의료AI 실증 20개 과제 신설"), ", 그리고 ", h("strong", null, "급성기병원 인증기준 Ver.5.0이 2027년부터"), " 환자안전 성과관리에 중점을 둔다. 2026년에 만들어 2027년 인증 대응에 투입하는 그림이다.")
        ),

        /* 파급 */
        h(Section, { title: "파급 — 산출물의 1차 형태는 소프트웨어가 아니라 표다" },
          h("p", null, "조건별 기대편차 노모그램은 인쇄해서 항암주사실 벽에 붙일 수 있다. 인증도 승인도 네트워크도 필요하지 않다. 기존 ISMP 차트가 “높이가 영향을 준다”고 경고하는 자리에 숫자를 넣는 것이 전부다. ", h("strong", null, "도입 비용이 0인 개선이 실제로 존재하는 드문 경우다.")),
          h("p", null, "그 위에 근거(지침 개정에 투입할 정량 근거), 정책(급여 공백과 규제 공백을 동시에 가리킴), 확장(항생제·수혈·TPN으로 이식되는 방법론, 오염된 약물명을 가진 모든 국내 임상 데이터에 재사용되는 정규화 층)이 얹힌다.")
        ),

        /* 확인 사항 */
        h(Section, { title: "남은 확인 사항" },
          h(Checklist),
          h("p", { className: "note" }, "일정: ~8/7 팀 구성·참가 접수 → 8/7~8/12 본문 작성 → 8/13 PDF 변환 → ", h("strong", null, "8/14 16:00 팀장 계정 제출"), ". 9월 RAG 구축·합성 데이터 리허설 → 9월 하순~10월 초 ", h("strong", null, "안심존 방문 1회(분석 완주 + 당일 반출 신청)"), " → 10월 노모그램 확정 → 11/6 본선 제출. 반출 심의가 1~2주이므로 10월 초 방문이 절대 기준이다.")
        ),

        h("footer", null,
          "작업 문서 · docs/제안서-v2.md · 근거는 docs/memory/ 03~09번", h("br"),
          "데이터 설명서는 텍스트가 전부 이미지로 렌더된 PDF라, 이 환경에 pip·PyMuPDF·poppler가 없어 zlib만으로 PDF 오브젝트를 파싱해 페이지를 합성하는 렌더러를 작성해 판독했다 (docs/tools/render_image_pdf.py)."
        )
      )
    );
  }

  /* 테마 토글 */
  function ThemeToggle() {
    return h("button", {
      className: "toggle", type: "button",
      onClick: function () {
        var el = document.documentElement;
        var cur = el.getAttribute("data-theme");
        if (!cur) cur = window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
        el.setAttribute("data-theme", cur === "dark" ? "light" : "dark");
      }
    }, "테마");
  }

  var root = ReactDOM.createRoot(document.getElementById("root"));
  root.render(h(React.Fragment, null, h(ThemeToggle), h(App)));
})();
