# DAKER 2026 — K-Health 미개방데이터 활용 경진대회

**예선 마감: 2026-08-14 (금) 16:00 KST** — PDF 30장 이내, `.hwp/.hwpx/PPT` 불가.
배점: 시의성 20 / 실현성 30 / 참신성 30 / 파급성 20 (+예선 기간 안심존 방문 가점 5).
대회 페이지: https://daker.ai/public/hackathons/2026-k-health-unreleased-data-utilization-competit
(SPA라 크롤링 불가 — 원문은 `.orca/drops/k-health-meta/overview.txt`, `hackathon.json`)

## 현재 상태 (2026-08-07)

제출 후보본: **`docs/khealth-proposal.pdf` (17쪽 / 한도 30쪽)**
— **[대구] 경북대학교병원 입원환자 활력징후(Vital Sign) 데이터** · 심정지 원점 역산
"세 개의 시계"(T_phys 생리 이탈 · T_rule 규칙 발화 · T_obs 관측 강화).

경위·선택 근거·정직성 제약·남은 결정사항(팀명, 안심존 방문, 본선 위치 질의)은
**`docs/khealth-README.md`** 가 단일 기준 문서다.

7/30~31의 이전 방향(대전 건양대 신유량조절기)은 `docs/archive/`에 보존되어 있다.
최종 제출을 어느 방향으로 할지는 아직 결정 전이다.

## 재현

```bash
.venv/bin/python -m src.khth.run       # 합성 코호트 → 세 시계 → docs/figures/*.png + data/khth_pipeline.json
.venv/bin/python -m src.khth.render    # docs/khealth-proposal.md → .pdf (쪽수 함께 출력)
```

`.venv`: Python 3.14 · matplotlib · reportlab · pypdf. 한글 폰트는 `assets/fonts/Pretendard-*.ttf`.

## 구조

| 경로 | 내용 |
|---|---|
| `docs/khealth-proposal.md` / `.pdf` | 제출 후보 원고. **경로가 `src/khth/render.py`에 박혀 있으니 옮기지 말 것** |
| `docs/khealth-README.md` | 작업 인수인계 — 대회 요건, 데이터셋 선택 근거, 남은 결정 |
| `docs/figures/` | 본문 그림 1~5 (`src.khth.run`이 재생성 — 합성 데이터 결과) |
| `docs/memory/` | 조사 메모 00~10 (`README.md`가 읽는 순서 인덱스) |
| `docs/data-spec/` | 공식 데이터 설명서 원문 (대전 20종 PDF + 대구·광주) |
| `docs/tools/render_image_pdf.py` | 이미지-PDF 판독용 렌더러 (zlib만 사용, 의존성 없음) |
| `docs/archive/` | 이전 세대(대전 신유량조절기) 산출물 전체 — 내부 `README.md` 참조 |
| `src/khth/` | 분석 파이프라인 + PDF 조판기 |
| `data/khth_pipeline.json` | 파이프라인 실행 요약 수치 |
| `assets/fonts/` | Pretendard (PDF 조판용) |
| `.orca/drops/` | 원본 zip · 설명서 텍스트 추출본(`k-health-text/`) · 대회 API 원문(`k-health-meta/`) |

`docs/`는 `.gitignore`로 커밋에서 제외된 작업 공간이다.
