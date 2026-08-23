"""GitHub Pages用の静的サイト生成（設計書7.6、要件F-42、IF-04）。

公開するのは自己完結の result.html、それを選ぶ一覧、および操作画面の見た目
（実行なし）である。生成物は出力先に書き、リポジトリの main には置かない。
"""

from __future__ import annotations

import json
import shutil
from html import escape
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..agents.mbti_types import winning_mbti_text
from ..config import runs_root

WINNER_LABELS = {"village": "村人陣営の勝ち", "werewolf": "人狼陣営の勝ち"}
STATUS_LABELS = {
    "done": "完了",
    "failed": "失敗",
    "partial": "一部失敗",
    "running": "実行中",
}


def build_pages(runs_dir: Optional[Path] = None, output_dir: Optional[Path] = None) -> Path:
    """runs/ を走査して静的サイトを output_dir に書き出す。"""
    source = Path(runs_dir) if runs_dir is not None else runs_root()
    dest = Path(output_dir) if output_dir is not None else source.parent / "site"
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)

    entries = collect_runs(source)
    for entry in entries:
        if not entry["source_html"]:
            continue
        target = dest / entry["href"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(entry["source_html"], target)

    latest = source / "latest.html"
    if latest.is_file():
        (dest / "runs").mkdir(parents=True, exist_ok=True)
        shutil.copy2(latest, dest / "runs" / "latest.html")

    static_dir = Path(__file__).resolve().parents[1] / "web" / "static"
    shutil.copy2(static_dir / "style.css", dest / "style.css")
    (dest / "simulator.html").write_text(render_simulator_preview(), encoding="utf-8")

    (dest / ".nojekyll").write_text("", encoding="utf-8")
    (dest / "index.html").write_text(render_index(entries), encoding="utf-8")
    (dest / "404.html").write_text(_NOT_FOUND, encoding="utf-8")
    return dest


def collect_runs(runs_dir: Path) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    if not runs_dir.is_dir():
        return entries
    for series_dir in sorted(runs_dir.iterdir()):
        if not series_dir.is_dir():
            continue
        for run_dir in sorted(series_dir.iterdir()):
            log_path = run_dir / "run_log.json"
            if not log_path.is_file():
                continue
            log = json.loads(log_path.read_text(encoding="utf-8"))
            html_path = run_dir / "result.html"
            result = log.get("result") or {}
            brain = log.get("brain") or {}
            config = log.get("config") or {}
            timing = log.get("timing") or {}
            href = "runs/{}/r{:03d}/result.html".format(
                log.get("series_id") or series_dir.name,
                int(log.get("run_index") or 1),
            )
            entries.append(
                {
                    "run_id": log.get("run_id", run_dir.name),
                    "series_id": log.get("series_id", series_dir.name),
                    "status": log.get("status", ""),
                    "winner": result.get("winner"),
                    "executed": result.get("executed"),
                    "provider": brain.get("provider") or "",
                    "model": brain.get("model") or "",
                    "started_at": timing.get("started_at") or "",
                    "elapsed_seconds": timing.get("elapsed_seconds"),
                    "player_count": config.get("player_count"),
                    "winning_mbti": winning_mbti_text(
                        log.get("players") or [], result.get("winner")
                    ),
                    "href": href,
                    "source_html": str(html_path) if html_path.is_file() else "",
                    "featured": _is_featured(log),
                }
            )
    entries.sort(key=lambda item: item.get("started_at") or "", reverse=True)
    return entries


def render_index(entries: List[Dict[str, Any]]) -> str:
    featured = [entry for entry in entries if entry.get("featured")]
    cards = "\n".join(_card(entry) for entry in featured) or "<p class='muted'>まだ公開できる完走結果はない。</p>"
    rows = "\n".join(_row(entry) for entry in entries) or (
        "<tr><td colspan='8'>実行結果はまだない。</td></tr>"
    )
    return _INDEX.format(
        count=len(entries),
        cards=cards,
        rows=rows,
    )


def _is_featured(log: Dict[str, Any]) -> bool:
    if log.get("status") != "done":
        return False
    return (log.get("brain") or {}).get("provider") in ("ollama", "gemini")


def _card(entry: Dict[str, Any]) -> str:
    winner = entry.get("winner")
    winner_class = "village" if winner == "village" else ("werewolf" if winner == "werewolf" else "")
    brain = " / ".join(part for part in (entry.get("provider"), entry.get("model")) if part)
    return (
        '<a class="card" href="{href}">'
        '<div class="label">{brain}</div>'
        '<div class="value {winner_class}">{winner}</div>'
        '<div class="muted">{mbti}</div>'
        '<div class="muted">{run_id}</div>'
        "</a>"
    ).format(
        href=escape(entry["href"]),
        brain=escape(brain or "—"),
        winner_class=winner_class,
        winner=escape(WINNER_LABELS.get(winner, "決着なし")),
        mbti=escape(entry.get("winning_mbti") or "—"),
        run_id=escape(entry.get("run_id") or ""),
    )


def _row(entry: Dict[str, Any]) -> str:
    winner = entry.get("winner")
    winner_class = "village" if winner == "village" else ("werewolf" if winner == "werewolf" else "")
    elapsed = entry.get("elapsed_seconds")
    elapsed_text = "—" if elapsed in (None, "") else "{}秒".format(elapsed)
    link = (
        '<a href="{href}">{run_id}</a>'.format(
            href=escape(entry["href"]),
            run_id=escape(entry.get("run_id") or ""),
        )
        if entry.get("source_html")
        else escape(entry.get("run_id") or "")
    )
    return (
        "<tr><td>{link}</td><td>{status}</td>"
        '<td class="{winner_class}">{winner}</td>'
        "<td class='wrap'>{mbti}</td><td>{brain}</td>"
        "<td>{elapsed}</td><td>{started}</td><td>{players}</td></tr>"
    ).format(
        link=link,
        status=escape(STATUS_LABELS.get(entry.get("status"), entry.get("status") or "—")),
        winner_class=winner_class,
        winner=escape(WINNER_LABELS.get(winner, "—")),
        mbti=escape(entry.get("winning_mbti") or "—"),
        brain=escape(
            " / ".join(part for part in (entry.get("provider"), entry.get("model")) if part)
            or "—"
        ),
        elapsed=escape(str(elapsed_text)),
        started=escape(entry.get("started_at") or "—"),
        players=escape(str(entry.get("player_count") or "—")),
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
td.wrap, th.wrap {{ white-space: normal; }}
.scroll {{ overflow-x: auto; }}
a {{ color: var(--accent); }}
.note {{ color: var(--muted); font-size: 12px; margin-top: 40px; border-top: 1px solid var(--line); padding-top: 16px; }}
</style>
</head>
<body>
<main>
  <h1>MBTI人狼 実行結果</h1>
  <p class="sub">開発環境なしで結果を見るための公開ページ。{count}件。対戦の新規実行はできない。<a href="simulator.html">操作画面の見た目</a> / <a href="runs/latest.html">最新の試合</a></p>
  <h2>観察用の試合</h2>
  <div class="cards">
{cards}
  </div>
  <h2>すべての実行</h2>
  <div class="scroll">
    <table>
      <thead>
        <tr>
          <th>run_id</th><th>状態</th><th>勝敗</th><th class="wrap">勝ったMBTI</th>
          <th>脳</th><th>所要</th><th>開始</th><th>人数</th>
        </tr>
      </thead>
      <tbody>
{rows}
      </tbody>
    </table>
  </div>
  <p class="note">
    MBTIおよび心理機能は、実在人物の診断や評価ではない。エージェントの振る舞いを分けるためのフィクション設定として扱っている。<br>
    MBTIは主機能からの候補2タイプ（要求定義書6.5）。1人に心理機能を1つだけ持たせているため、タイプは一意に決まらない。
  </p>
</main>
</body>
</html>
"""


def render_simulator_preview() -> str:
    """操作画面と同じ項目を、実行できない見た目として出す。"""
    return _SIMULATOR


_SIMULATOR = """<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MBTI人狼シミュレーター（見た目）</title>
<link rel="stylesheet" href="style.css">
<style>
.preview-banner {
  background: #332812;
  border: 1px solid #6c5230;
  color: #f0d9a8;
  border-radius: 10px;
  padding: 12px 14px;
  margin-bottom: 16px;
  font-size: 13px;
}
fieldset {
  border: 0;
  padding: 0;
  margin: 0;
  min-inline-size: 0;
}
</style>
</head>
<body>
<header>
  <h1>MBTI人狼シミュレーター</h1>
  <p class="sub">条件を設定して対戦を開始し、完了後に同じ画面で会話と結果を確認する。会話は逐次表示しない。</p>
</header>
<main>
  <p class="preview-banner">
    これは操作画面の見た目です。公開ページからは対戦を開始できません。
    実行するには、リポジトリを clone してローカルで <code>python -m mbti_werewolf ui</code> を起動してください。
    <a href="./">結果一覧へ戻る</a>
  </p>
  <section class="panel" id="setup-panel">
    <h2>1. 実験条件</h2>
    <form id="config-form">
      <fieldset disabled>
      <div class="grid">
        <label>参加人数
          <input type="number" name="player_count" value="4">
        </label>
        <label>議論ターン数
          <input type="number" name="turn_count" value="3">
        </label>
        <label>試合回数
          <input type="number" name="game_count" value="1">
        </label>
        <label>seed
          <input type="number" name="seed" value="42">
        </label>
        <label>役職割当方法
          <select name="role_assignment_mode">
            <option selected>seeded_random（seed付きランダム）</option>
          </select>
        </label>
        <label>history_mode
          <select name="history_mode">
            <option selected>none（過去ログを渡さない）</option>
          </select>
        </label>
        <label>人狼の人数
          <input type="number" name="werewolf_count" value="1">
        </label>
        <label>脳（provider）
          <select name="provider">
            <option selected>stub（LLMを呼ばない・即時）</option>
            <option>ollama（ローカル実行）</option>
            <option>gemini（無料枠API）</option>
          </select>
        </label>
        <label>モデル名
          <input type="text" name="model" placeholder="例: gemma3:4b" value="">
        </label>
        <label>発言の文字数上限
          <input type="number" name="max_output_chars" value="200">
        </label>
      </div>
      <label class="inline">心理機能（上級者向け・主機能を直接指定）
        <input type="text" name="functions" value="Ne, Si, Fi, Te">
      </label>
      <p class="hint">
        既定はMBTIタイプそのもので定義した4人ロースター（討論者ENTP・擁護者ISFJ・仲介者INFP・幹部ESTJ）です。
        上の欄は、その4人の主機能がそのまま入っています。ここを書き換えると参加人数以上の主機能を上から順に割り当てる旧来の指定方法になり、
        MBTIタイプの表示は書き換えた分だけ外れます（候補2タイプ表示に戻ります）。
      </p>
      <h2>2. 実行</h2>
      <div class="actions">
        <button type="button" disabled>対戦開始</button>
        <button type="button" class="ghost" disabled>条件を編集し直す</button>
      </div>
      <p class="hint">公開ページでは実行できません。</p>
      </fieldset>
    </form>
  </section>
  <section class="panel">
    <h2>3. 状態</h2>
    <div class="status-line">
      <span class="dot"></span>
      <strong>未実行</strong>
      <span class="muted">この公開ページでは試合を回せません。</span>
    </div>
    <div class="progress"><div class="bar"></div></div>
  </section>
  <section class="panel">
    <h2>5. 過去の実行</h2>
    <p class="muted">過去の試合は <a href="./">結果一覧</a> から開きます。</p>
  </section>
</main>
<footer>
  MBTIおよび心理機能は、実在人物の診断や評価ではない。エージェントの振る舞いを分けるためのフィクション設定として扱っている。
</footer>
</body>
</html>
"""


_NOT_FOUND = """<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ページが見つかりません</title>
</head>
<body>
<p>このURLには結果がありません。<a href="./">一覧へ戻る</a></p>
</body>
</html>
"""
