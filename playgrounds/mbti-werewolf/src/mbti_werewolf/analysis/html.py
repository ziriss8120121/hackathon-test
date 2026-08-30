"""分析HTMLの共通の枠（設計書7.5）。

上位のHTMLは集計値を `<script type="application/json">` として埋め込む。並べ替え
を後から足す余地を残すためである。一方、JavaScriptが動かない環境でも読めるよう、
同じ内容をPython側でも表として書き出す。ケースの `result.html` と同じく、CSSは
インラインに含める。
"""

from __future__ import annotations

import html
import json
from typing import Any, Dict, List, Optional, Sequence, Tuple

_STYLE = """
:root { --bg:#f5f6f8; --panel:#fff; --line:#e2e5ea; --text:#1f2328; --muted:#667085; --accent:#3b66d6; }
* { box-sizing: border-box; }
body { margin:0; padding:0 0 64px; background:var(--bg); color:var(--text);
  font-family:"Hiragino Sans","Noto Sans JP",system-ui,sans-serif; line-height:1.7; }
main { max-width:960px; margin:0 auto; padding:20px 16px 0; }
.site-header { background:#fff; border-bottom:1px solid var(--line); }
.site-header-inner { max-width:960px; margin:0 auto; padding:14px 16px; }
.brand { font-size:17px; font-weight:700; }
.brand-accent { color:var(--accent); font-weight:500; }
nav { max-width:960px; margin:0 auto; display:flex; gap:4px; overflow-x:auto; padding:0 16px 10px; }
nav a { flex-shrink:0; font-size:12px; color:var(--muted); text-decoration:none; padding:6px 12px; }
h1 { font-size:19px; margin:0 0 8px; }
h2 { font-size:16px; margin:32px 0 12px; padding-left:10px; border-left:3px solid var(--accent); }
.sub, .note { color:var(--muted); font-size:13px; }
.note { background:var(--panel); border:1px solid var(--line); border-radius:10px; padding:12px 14px; }
.scroll { overflow-x:auto; border:1px solid var(--line); border-radius:10px; background:var(--panel); }
table { width:100%; border-collapse:collapse; font-size:13px; }
th, td { padding:8px 10px; border-bottom:1px solid var(--line); text-align:left; vertical-align:top; }
th { color:var(--muted); font-weight:600; white-space:nowrap; }
ul { padding-left:1.2em; }
@media (max-width: 640px) {
  table.wrap thead { display:none; }
  table.wrap tr { display:block; padding:10px 8px; border-bottom:1px solid var(--line); }
  table.wrap td { display:flex; justify-content:space-between; gap:12px; border:0; padding:4px 0; }
  table.wrap td::before { content:attr(data-label); color:var(--muted); flex:0 0 42%; }
}
"""


def esc(value: Any) -> str:
    if value is None:
        return ""
    return html.escape(str(value), quote=True)


def md_cell(value: Any) -> str:
    if value is None:
        return "—"
    text = str(value).replace("|", "\\|").replace("\n", " ")
    return text if text else "—"


def md_table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    lines = ["| {0} |".format(" | ".join(headers))]
    lines.append("| {0} |".format(" | ".join("---" for _ in headers)))
    for row in rows:
        lines.append("| {0} |".format(" | ".join(md_cell(cell) for cell in row)))
    return "\n".join(lines)


def fmt_number(value: Any, digits: int = 4) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return "{0:.{1}f}".format(value, digits)
    return str(value)


def table_html(headers: Sequence[str], rows: Sequence[Sequence[Any]], wrap: bool = True) -> str:
    head = "".join("<th>{0}</th>".format(esc(h)) for h in headers)
    body_rows = []
    for row in rows:
        cells = []
        for header, cell in zip(headers, row):
            cells.append(
                '<td data-label="{0}">{1}</td>'.format(esc(header), esc(cell if cell is not None else "—"))
            )
        body_rows.append("<tr>{0}</tr>".format("".join(cells)))
    return (
        '<div class="scroll"><table class="{0}"><thead><tr>{1}</tr></thead>'
        "<tbody>{2}</tbody></table></div>"
    ).format("wrap" if wrap else "", head, "".join(body_rows))


def page(
    title: str,
    body: str,
    payload: Optional[Dict[str, Any]] = None,
    nav: Optional[List[Tuple[str, str]]] = None,
) -> str:
    links = ""
    if nav:
        links = "<nav>{0}</nav>".format(
            "".join('<a href="{0}">{1}</a>'.format(esc(href), esc(label)) for href, label in nav)
        )
    json_block = ""
    if payload is not None:
        json_block = (
            '<script type="application/json" id="analysis-data">{0}</script>\n'
        ).format(json.dumps(payload, ensure_ascii=False, indent=2))
    return (
        "<!DOCTYPE html>\n<html lang=\"ja\">\n<head>\n<meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        "<title>{title}</title>\n<style>{style}</style>\n</head>\n<body>\n"
        "<header class=\"site-header\"><div class=\"site-header-inner\">"
        "<div class=\"brand\">MBTI人狼 <span class=\"brand-accent\">分析</span></div>"
        "</div>{nav}</header>\n<main>\n<h1>{title}</h1>\n{body}\n</main>\n"
        "{json_block}</body>\n</html>\n"
    ).format(title=esc(title), style=_STYLE, nav=links, body=body, json_block=json_block)
