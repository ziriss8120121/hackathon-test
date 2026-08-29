"""GitHub Pages用の静的サイト生成（設計書7.6、要件F-42、IF-04）。

公開するのは分析結果と結果ビューである。生成物は `site/` に書き、リポジトリの
`main` には置かない。`gh-pages` への掲載は人間が行う。

`runs/` を走査して HTML を複写する。データベースへの登録処理を持たないため、
コマンドから実行した結果も画面から実行した結果も同じように現れる（7.4）。
一覧の入口は実験単位にする。`analyze` が書いた `experiment.html` がある実験は
そこへ、まだない実験はケースの `result.html` へ辿れる。
"""

from __future__ import annotations

import json
import shutil
from html import escape
from pathlib import Path
from typing import Any, Dict, List, Optional

WINNER_LABELS = {"village": "村人陣営の勝ち", "werewolf": "人狼陣営の勝ち"}
STATUS_LABELS = {"done": "完了", "failed": "失敗", "running": "実行中"}

#: 一覧の先頭に出すカードの件数。全1,700ケースをカードにすると選べない。
FEATURED_LIMIT = 6
COPY_HTML_NAMES = frozenset(
    {"experiment.html", "rq1.html", "rq2.html", "trial.html", "result.html"}
)


def build_pages(
    runs_dir: Optional[Path] = None, output_dir: Optional[Path] = None
) -> Path:
    """`runs/` を走査して静的サイトを `output_dir` に書き出す。"""

    from ..runner import default_runs_dir

    source = Path(runs_dir) if runs_dir is not None else default_runs_dir()
    dest = Path(output_dir) if output_dir is not None else source.parent / "site"
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)

    experiments = collect_experiments(source)
    entries = collect_cases(source)
    _copy_html_tree(source, dest)

    # `latest.html` の転送先は runs/ からの相対パスなので、出力先でも runs/ の下に
    # 置く。置き場所を変えるとリンクが切れる。
    latest = source / "latest.html"
    if latest.is_file():
        (dest / "runs").mkdir(parents=True, exist_ok=True)
        shutil.copy2(latest, dest / "runs" / "latest.html")

    (dest / ".nojekyll").write_text("", encoding="utf-8")
    (dest / "index.html").write_text(render_index(entries, experiments), encoding="utf-8")
    (dest / "404.html").write_text(_NOT_FOUND, encoding="utf-8")
    return dest


def _copy_html_tree(source: Path, dest: Path) -> None:
    """分析HTMLとケースの result.html を、相対リンクが切れない位置へ複写する。"""

    if not source.is_dir():
        return
    for path in source.rglob("*.html"):
        if path.name not in COPY_HTML_NAMES:
            continue
        target = dest / "runs" / path.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)


def collect_experiments(runs_dir: Path) -> List[Dict[str, Any]]:
    """`e-` で始まる実験ディレクトリを新しい順に集める。"""

    items: List[Dict[str, Any]] = []
    if not runs_dir.is_dir():
        return items
    for exp_dir in sorted(d for d in runs_dir.iterdir() if d.is_dir()):
        if not exp_dir.name.startswith("e-"):
            continue
        status = _read_json(exp_dir / "status.json")
        html_path = exp_dir / "experiment.html"
        items.append(
            {
                "experiment_id": exp_dir.name,
                "status": status.get("status") or "",
                "trial_total": status.get("trial_total"),
                "case_done": status.get("case_done"),
                "started_at": status.get("started_at") or "",
                "href": "runs/{0}/experiment.html".format(exp_dir.name)
                if html_path.is_file()
                else "",
                "has_analysis": html_path.is_file(),
            }
        )
    items.sort(key=lambda item: (item["started_at"], item["experiment_id"]), reverse=True)
    return items


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, ValueError, OSError):
        return {}
    return payload if isinstance(payload, dict) else {}


def collect_cases(runs_dir: Path) -> List[Dict[str, Any]]:
    """`runs/実験/Trial/ケース/case_log.json` を新しい順に集める。"""

    entries: List[Dict[str, Any]] = []
    if not runs_dir.is_dir():
        return entries

    for exp_dir in sorted(d for d in runs_dir.iterdir() if d.is_dir()):
        for trial_dir in sorted(d for d in exp_dir.iterdir() if d.is_dir()):
            for case_dir in sorted(d for d in trial_dir.iterdir() if d.is_dir()):
                entry = _entry(exp_dir, trial_dir, case_dir)
                if entry is not None:
                    entries.append(entry)

    entries.sort(key=lambda item: (item["started_at"], item["case_id"]), reverse=True)
    return entries


def _entry(exp_dir: Path, trial_dir: Path, case_dir: Path) -> Optional[Dict[str, Any]]:
    log_path = case_dir / "case_log.json"
    if not log_path.is_file():
        return None
    try:
        log = json.loads(log_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, ValueError, OSError):
        # 書き込み途中で止まったファイルは一覧から外す。1件で生成が止まらないように。
        return None

    result = log.get("result") or {}
    brain = log.get("brain") or {}
    timing = log.get("timing") or {}
    html_path = case_dir / "result.html"

    return {
        "case_id": log.get("case_id", case_dir.name),
        "experiment_id": log.get("experiment_id", exp_dir.name),
        "composition": _composition_text(log),
        "status": log.get("status", ""),
        "winner": result.get("winner"),
        "valid": result.get("valid", True),
        "executed": result.get("executed") or [],
        "provider": brain.get("provider") or "",
        "model": brain.get("model") or "",
        "started_at": timing.get("started_at") or "",
        "elapsed_seconds": timing.get("elapsed_seconds"),
        "rounds": (log.get("discussion") or {}).get("rounds"),
        "href": "runs/{0}/{1}/{2}/result.html".format(
            exp_dir.name, trial_dir.name, case_dir.name
        ),
        "source_html": str(html_path) if html_path.is_file() else "",
        "featured": log.get("status") == "done"
        and brain.get("provider") in ("ollama", "gemini"),
    }


def _composition_text(log: Dict[str, Any]) -> str:
    if log.get("composition") == "mixed":
        return "混合構成"
    return "同質構成 {0}".format(log.get("homogeneous_type") or "")


def render_index(
    entries: List[Dict[str, Any]],
    experiments: Optional[List[Dict[str, Any]]] = None,
) -> str:
    experiments = experiments or []
    exp_featured = [e for e in experiments if e["has_analysis"]][:FEATURED_LIMIT]
    exp_cards = "\n".join(_experiment_card(e) for e in exp_featured) or (
        "<p class='muted'>分析済みの実験はまだない。`analyze` のあとで pages を再実行する。</p>"
    )
    exp_rows = "\n".join(_experiment_row(e) for e in experiments) or (
        "<tr><td colspan='5'>実験はまだない。</td></tr>"
    )
    featured = [e for e in entries if e["featured"]][:FEATURED_LIMIT]
    cards = "\n".join(_card(e) for e in featured) or (
        "<p class='muted'>実モデルで完走したケースはまだない。</p>"
    )
    rows = "\n".join(_row(e) for e in entries) or (
        "<tr><td colspan='7'>実行結果はまだない。</td></tr>"
    )
    return _INDEX.format(
        experiment_count=len(experiments),
        case_count=len(entries),
        experiment_cards=exp_cards,
        experiment_rows=exp_rows,
        cards=cards,
        rows=rows,
    )


def _winner_class(winner: Optional[str]) -> str:
    if winner == "village":
        return "village"
    if winner == "werewolf":
        return "werewolf"
    return ""


def _winner_text(entry: Dict[str, Any]) -> str:
    if not entry["valid"]:
        return "無効試合"
    return WINNER_LABELS.get(entry["winner"], "決着なし")


def _brain_text(entry: Dict[str, Any]) -> str:
    parts = [p for p in (entry["provider"], entry["model"]) if p]
    return " / ".join(parts) or "—"


def _experiment_card(entry: Dict[str, Any]) -> str:
    return (
        '<a class="card" href="{href}">'
        '<div class="label">実験</div>'
        '<div class="value">{experiment_id}</div>'
        '<div class="muted">Trial {trials} / 完了ケース {done}</div>'
        "</a>"
    ).format(
        href=escape(entry["href"]),
        experiment_id=escape(entry["experiment_id"]),
        trials=escape("—" if entry["trial_total"] is None else str(entry["trial_total"])),
        done=escape("—" if entry["case_done"] is None else str(entry["case_done"])),
    )


def _experiment_row(entry: Dict[str, Any]) -> str:
    if entry["href"]:
        link = '<a href="{href}">{experiment_id}</a>'.format(
            href=escape(entry["href"]),
            experiment_id=escape(entry["experiment_id"]),
        )
        analysis = "あり"
    else:
        link = escape(entry["experiment_id"])
        analysis = "未生成"
    return (
        '<tr><td data-label="実験" class="wrap">{link}</td>'
        '<td data-label="状態">{status}</td>'
        '<td data-label="Trial">{trials}</td>'
        '<td data-label="完了ケース">{done}</td>'
        '<td data-label="分析">{analysis}</td></tr>'
    ).format(
        link=link,
        status=escape(STATUS_LABELS.get(entry["status"], entry["status"] or "—")),
        trials=escape("—" if entry["trial_total"] is None else str(entry["trial_total"])),
        done=escape("—" if entry["case_done"] is None else str(entry["case_done"])),
        analysis=escape(analysis),
    )


def _card(entry: Dict[str, Any]) -> str:
    return (
        '<a class="card" href="{href}">'
        '<div class="label">{composition}</div>'
        '<div class="value {winner_class}">{winner}</div>'
        '<div class="muted">{brain}</div>'
        '<div class="muted">{case_id}</div>'
        "</a>"
    ).format(
        href=escape(entry["href"]),
        composition=escape(entry["composition"]),
        winner_class=_winner_class(entry["winner"]),
        winner=escape(_winner_text(entry)),
        brain=escape(_brain_text(entry)),
        case_id=escape(entry["case_id"]),
    )


def _row(entry: Dict[str, Any]) -> str:
    elapsed = entry["elapsed_seconds"]
    link = (
        '<a href="{href}">{case_id}</a>'.format(
            href=escape(entry["href"]), case_id=escape(entry["case_id"])
        )
        if entry["source_html"]
        else escape(entry["case_id"])
    )
    return (
        '<tr><td data-label="ケース" class="wrap">{link}</td>'
        '<td data-label="構成">{composition}</td>'
        '<td data-label="状態">{status}</td>'
        '<td data-label="勝敗" class="{winner_class}">{winner}</td>'
        '<td data-label="脳" class="wrap">{brain}</td>'
        '<td data-label="ラウンド">{rounds}</td>'
        '<td data-label="開始">{started}</td></tr>'
    ).format(
        link=link,
        composition=escape(entry["composition"]),
        status=escape(STATUS_LABELS.get(entry["status"], entry["status"] or "—")),
        winner_class=_winner_class(entry["winner"]),
        winner=escape(_winner_text(entry)),
        brain=escape(_brain_text(entry)),
        rounds=escape("—" if entry["rounds"] is None else str(entry["rounds"])),
        started=escape(entry["started_at"] or "—"),
    )


_INDEX = """<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MBTI人狼 実行結果</title>
<style>
:root {{
  --bg: #12141a;
  --panel: #1b1e26;
  --line: #2c303c;
  --text: #e6e8ee;
  --muted: #9aa1b1;
  --accent: #7aa2f7;
  --village: #6bc48a;
  --werewolf: #e06c75;
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0;
  padding: 24px 16px 64px;
  background: var(--bg);
  color: var(--text);
  font-family: "Hiragino Sans", "Noto Sans JP", system-ui, sans-serif;
  line-height: 1.7;
}}
main {{ max-width: 960px; margin: 0 auto; }}
h1 {{ font-size: 20px; margin: 0 0 4px; }}
h2 {{ font-size: 16px; margin: 32px 0 12px; padding-bottom: 6px; border-bottom: 1px solid var(--line); }}
.sub {{ color: var(--muted); font-size: 13px; margin: 0 0 24px; }}
.muted {{ color: var(--muted); font-size: 13px; }}
.cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }}
a.card {{
  display: block;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 14px 16px;
  color: inherit;
  text-decoration: none;
}}
a.card:hover {{ border-color: var(--accent); }}
.card .label {{ color: var(--muted); font-size: 12px; }}
.card .value {{ font-size: 17px; margin: 6px 0; }}
.village {{ color: var(--village); }}
.werewolf {{ color: var(--werewolf); }}
table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
th, td {{ padding: 8px 10px; border-bottom: 1px solid var(--line); text-align: left; white-space: nowrap; }}
th {{ color: var(--muted); font-weight: 600; }}
td.wrap, th.wrap {{ white-space: normal; overflow-wrap: anywhere; }}
.scroll {{ overflow-x: auto; }}
a {{ color: var(--accent); }}
.note {{ color: var(--muted); font-size: 12px; margin-top: 40px; border-top: 1px solid var(--line); padding-top: 16px; }}

/* 狭い画面では表を1行1ブロックへ折り返す（設計書7.6）。 */
@media (max-width: 640px) {{
  table, tbody {{ display: block; width: 100%; }}
  thead {{ display: none; }}
  tr {{ display: block; padding: 10px 0; border-bottom: 1px solid var(--line); }}
  td {{ display: flex; gap: 10px; padding: 2px 0; border: none; white-space: normal; }}
  td::before {{ content: attr(data-label); flex: 0 0 5.5em; color: var(--muted); font-size: 11px; }}
}}
</style>
</head>
<body>
<main>
  <h1>MBTI人狼 実行結果</h1>
  <p class="sub">開発環境なしで結果を見るための公開ページ。実験{experiment_count}件、ケース{case_count}件。実行はできない。<a href="runs/latest.html">最新の結果</a></p>
  <h2>実験の分析</h2>
  <div class="cards">
{experiment_cards}
  </div>
  <h2>すべての実験</h2>
  <div class="scroll">
    <table>
      <thead>
        <tr>
          <th class="wrap">実験</th><th>状態</th><th>Trial</th><th>完了ケース</th><th>分析</th>
        </tr>
      </thead>
      <tbody>
{experiment_rows}
      </tbody>
    </table>
  </div>
  <h2>実モデルで完走したケース</h2>
  <div class="cards">
{cards}
  </div>
  <h2>すべてのケース</h2>
  <div class="scroll">
    <table>
      <thead>
        <tr>
          <th class="wrap">ケース</th><th>構成</th><th>状態</th><th>勝敗</th>
          <th class="wrap">脳</th><th>ラウンド</th><th>開始</th>
        </tr>
      </thead>
      <tbody>
{rows}
      </tbody>
    </table>
  </div>
  <p class="note">
    MBTIは実在人物の診断や評価ではない。エージェントの振る舞いを分けるためのフィクション設定として扱っている。<br>
    1 Trialは混合構成1ケースと同質構成16ケースの17ケースで構成される。指標は暫定であり、版によって変わる。
  </p>
</main>
</body>
</html>
"""

_NOT_FOUND = """<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ページが見つからない</title>
<style>
body { margin: 0; padding: 48px 20px; background: #12141a; color: #e6e8ee;
  font-family: "Hiragino Sans", "Noto Sans JP", system-ui, sans-serif; line-height: 1.8; }
a { color: #7aa2f7; }
</style>
</head>
<body>
<p>ページが見つかりませんでした。<a href="/hackathon-test/">結果一覧へ戻る</a></p>
</body>
</html>
"""
