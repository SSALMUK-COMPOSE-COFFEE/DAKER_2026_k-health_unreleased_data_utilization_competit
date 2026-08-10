#!/usr/bin/env python3
"""shell.html + React UMD + app.js → 단일 HTML로 합성.

Artifact는 CSP로 외부 호스트를 차단하므로 React를 인라인해야 한다.
빌드 시점에 UMD 빌드를 받아 스크립트 태그 안에 그대로 넣는다.

  curl -sLo react.js     https://unpkg.com/react@18.3.1/umd/react.production.min.js
  curl -sLo react-dom.js https://unpkg.com/react-dom@18.3.1/umd/react-dom.production.min.js
  python3 build.py
"""
import pathlib

here = pathlib.Path(__file__).parent
shell = (here / "shell.html").read_text(encoding="utf-8")
parts = {
    "/*__REACT__*/": (here / "react.js"),
    "/*__REACTDOM__*/": (here / "react-dom.js"),
    "/*__APP__*/": (here / "app.js"),
}
out = shell
for token, path in parts.items():
    src = path.read_text(encoding="utf-8")
    if "</script" in src.lower():
        raise SystemExit(f"닫는 script 태그가 {path.name} 안에 있다 — 인라인 불가")
    out = out.replace(token, src)
for token in parts:
    assert token not in out, f"치환 실패: {token}"
(here / "kh-proposal.html").write_text(out, encoding="utf-8")
print("kh-proposal.html", len(out), "bytes")
