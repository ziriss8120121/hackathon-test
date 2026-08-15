"""result.html の生成（設計書3.6、7.5、要件F-34、F-41、NF-15）。

実行結果のJSONをファイル内に埋め込んだ自己完結HTMLとして生成する。外部から
データを取得しないため、file:// で直接開いてもGitHub Pages経由でも同じように
表示される。操作画面と違ってPythonの起動を必要としないので、実行環境を持たない
メンバーがブラウザだけで結果を読める。

データを埋め込むのは、file:// から fetch で別ファイルを読むとブラウザに
拒否されるためである。
"""

from __future__ import annotations

import json
from typing import Any, Dict

_TEMPLATE = """<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MBTI人狼 結果 __RUN_ID__</title>
<style>
:root {
  --bg: #12141a;
  --panel: #1b1e26;
  --line: #2c303c;
  --text: #e6e8ee;
  --muted: #9aa1b1;
  --accent: #7aa2f7;
  --village: #6bc48a;
  --werewolf: #e06c75;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  padding: 24px 16px 64px;
  background: var(--bg);
  color: var(--text);
  font-family: "Hiragino Sans", "Noto Sans JP", system-ui, sans-serif;
  line-height: 1.7;
}
main { max-width: 960px; margin: 0 auto; }
h1 { font-size: 20px; margin: 0 0 4px; }
h2 { font-size: 16px; margin: 32px 0 12px; padding-bottom: 6px; border-bottom: 1px solid var(--line); }
.sub { color: var(--muted); font-size: 13px; margin: 0 0 24px; }
.panel { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 16px 18px; }
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; }
.card { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 14px 16px; }
.card .label { color: var(--muted); font-size: 12px; }
.card .value { font-size: 17px; margin-top: 4px; word-break: break-all; }
.village { color: var(--village); }
.werewolf { color: var(--werewolf); }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td { padding: 8px 10px; border-bottom: 1px solid var(--line); text-align: left; white-space: nowrap; }
th { color: var(--muted); font-weight: 600; }
td.wrap, th.wrap { white-space: normal; }
.scroll { overflow-x: auto; }
.turn { color: var(--accent); font-size: 13px; margin: 20px 0 8px; }
.speech { background: var(--panel); border: 1px solid var(--line); border-left: 3px solid var(--accent); border-radius: 8px; padding: 10px 14px; margin-bottom: 10px; }
.speech .who { font-size: 12px; color: var(--muted); margin-bottom: 4px; }
.badge { display: inline-block; font-size: 11px; padding: 1px 6px; border-radius: 999px; border: 1px solid var(--line); color: var(--muted); margin-left: 6px; }
.alert { background: #33212a; border: 1px solid #6c3a45; border-radius: 10px; padding: 14px 16px; margin-bottom: 20px; }
.note { color: var(--muted); font-size: 12px; margin-top: 40px; border-top: 1px solid var(--line); padding-top: 16px; }
dl.kv { display: grid; grid-template-columns: max-content 1fr; gap: 6px 20px; margin: 0; font-size: 13px; }
dl.kv dt { color: var(--muted); }
dl.kv dd { margin: 0; word-break: break-all; }
.card .sub { color: var(--muted); font-size: 12px; margin-top: 6px; line-height: 1.5; }
.roster-card { display: flex; flex-direction: column; gap: 10px; }
.roster-card-top { display: flex; align-items: center; gap: 12px; }
.mbti-icon { width: 56px; height: 56px; border-radius: 12px; background: #12141a; border: 1px solid var(--line); display: flex; align-items: center; justify-content: center; overflow: hidden; flex-shrink: 0; }
.mbti-icon-fallback { font-size: 13px; font-weight: 700; color: var(--muted); letter-spacing: 0.02em; }
.roster-card-title { min-width: 0; }
.roster-card-title .value { font-size: 15px; word-break: break-word; }
.roster-card-title .label { font-size: 11px; color: var(--muted); margin-top: 2px; }
.roster-badges, .roster-stats { display: flex; gap: 6px; flex-wrap: wrap; }
.badge.role-badge.village { border-color: var(--village); color: var(--village); }
.badge.role-badge.werewolf { border-color: var(--werewolf); color: var(--werewolf); }
.badge.result-badge.win { border-color: var(--village); color: var(--village); }
.badge.result-badge.lose { border-color: var(--werewolf); color: var(--werewolf); }
.stat-pill { font-size: 11px; color: var(--muted); background: rgba(255, 255, 255, 0.04); border: 1px solid var(--line); border-radius: 999px; padding: 2px 8px; }
</style>
</head>
<body>
<main>
  <h1>MBTI人狼 実行結果</h1>
  <p class="sub" id="head-sub"></p>
  <div id="app"></div>
  <p class="note" id="foot-note"></p>
</main>

<script type="application/json" id="run-data">__RUN_DATA__</script>
<script>
const ROLE_LABELS = { werewolf: "人狼", villager: "村人" };
const WINNER_LABELS = { village: "村人陣営の勝ち", werewolf: "人狼陣営の勝ち" };
const FUNCTION_LABELS = __FUNCTION_LABELS__;
const DOMINANT_TO_MBTI = __DOMINANT_TO_MBTI__;

const log = JSON.parse(document.getElementById("run-data").textContent);
const players = {};
(log.players || []).forEach((p) => { players[p.player_id] = p; });
const metricsByPlayer = {};
((log.metrics && log.metrics.per_player) || []).forEach((r) => { metricsByPlayer[r.player_id] = r; });

function esc(value) {
  return String(value === undefined || value === null ? "" : value)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function mbtiOf(fn) {
  const types = DOMINANT_TO_MBTI[fn] || [];
  return types.length ? types.join(" / ") : "—";
}

// MBTIタイプが確定しているプレイヤー（v1改善のMVPロースター）はタイプ名を、
// 確定していない（旧ログ、functions直接指定など）場合は候補2タイプを表示する。
function identityOf(entry) {
  if (!entry) return "—";
  if (entry.mbti_type) {
    return entry.mbti_type + (entry.display_name ? "（" + entry.display_name + "）" : "");
  }
  return mbtiOf(entry.function);
}

function hasConfirmedMbti() {
  return (log.players || []).some((p) => p.mbti_type);
}

function winningMbti() {
  const winner = (log.result || {}).winner;
  const wanted = winner === "werewolf" ? "werewolf" : (winner === "village" ? "villager" : "");
  if (!wanted) return "決着なし";
  const parts = (log.players || []).filter((p) => p.role === wanted)
    .map((p) => p.player_id + "（" + p.function + "）→ " + identityOf(p));
  return parts.join("、") || "—";
}

function who(id) {
  const p = players[id];
  if (!p) return esc(id || "—");
  const fn = FUNCTION_LABELS[p.function] ? p.function + "／" + FUNCTION_LABELS[p.function] : p.function;
  return esc(id) + "（" + esc(fn) + " / " + esc(ROLE_LABELS[p.role] || p.role) + " / " + esc(identityOf(p)) + "）";
}

function topOf(key) {
  const rows = (log.metrics && log.metrics.per_player) || [];
  if (!rows.length) return "—";
  const top = Math.max.apply(null, rows.map((r) => r[key] || 0));
  if (!top) return "該当なし";
  return rows.filter((r) => (r[key] || 0) === top)
    .map((r) => r.player_id + "（" + r.function + "）→ " + identityOf(r)).join("、") + " — " + top;
}

// このファイルは自己完結HTML（外部通信なし、F-41/NF-15）が前提のため、
// アイコンは画像ではなく文字タイル（MBTIタイプ、無ければ主機能コード）にする。
// 画像化したくなったら、このHTMLへ data URI として埋め込む形にすること。
// 外部ファイルを指すimgタグは絶対に入れない。
function mbtiIconHtml(p) {
  const text = p.mbti_type ? p.mbti_type : p.function;
  return '<div class="mbti-icon"><div class="mbti-icon-fallback">' + esc(text) + '</div></div>';
}

function renderRoster() {
  const list = log.players || [];
  if (!list.length) return "";
  const cards = list.map((p) => {
    const stack = (p.function_stack && p.function_stack.length ? p.function_stack : [p.function]).join(" / ");
    const roleKey = p.role === "werewolf" ? "werewolf" : "village";
    const m = metricsByPlayer[p.player_id] || {};
    const winLabel = m.win === true ? "勝ち" : (m.win === false ? "負け" : "—");
    const winKey = m.win === true ? "win" : (m.win === false ? "lose" : "");
    const speechCount = m.speech_count === undefined || m.speech_count === null ? "—" : m.speech_count;
    const suspectedCount = m.suspected_by_count === undefined || m.suspected_by_count === null ? "—" : m.suspected_by_count;
    return '<div class="card roster-card">'
      + '<div class="roster-card-top">'
      + mbtiIconHtml(p)
      + '<div class="roster-card-title">'
      + '<div class="value">' + esc(identityOf(p)) + '</div>'
      + '<div class="label">' + esc(p.player_id) + '</div>'
      + '</div></div>'
      + '<div class="roster-badges">'
      + '<span class="badge role-badge ' + roleKey + '">' + esc(ROLE_LABELS[p.role] || p.role) + '</span>'
      + '<span class="badge result-badge ' + winKey + '">' + esc(winLabel) + '</span>'
      + '</div>'
      + '<div class="sub">4心理機能 ' + esc(stack) + '</div>'
      + '<div class="roster-stats">'
      + '<span class="stat-pill">発言 ' + esc(speechCount) + '</span>'
      + '<span class="stat-pill">疑われ ' + esc(suspectedCount) + '</span>'
      + '</div>'
      + '</div>';
  }).join("");
  return '<div class="cards">' + cards + '</div>';
}

function renderFailure() {
  if (log.status === "done") return "";
  const f = log.failure || {};
  return '<div class="alert"><strong>この実行は完走していません（' + esc(log.status) + "）</strong><br>"
    + "種別: <code>" + esc(f.kind || "不明") + "</code><br>" + esc(f.message || "") + "<br>"
    + "到達フェーズ: " + esc(log.phase || "") + "。ここまでの発言と投票は下に表示している。</div>";
}

function renderCards() {
  const r = log.result || {};
  const winnerClass = r.winner === "village" ? "village" : (r.winner === "werewolf" ? "werewolf" : "");
  const wolves = (log.players || []).filter((p) => p.role === "werewolf")
    .map((p) => p.player_id + "（" + p.function + "）→ " + identityOf(p)).join("、") || "—";
  const cards = [
    ["勝敗", '<span class="' + winnerClass + '">' + esc(WINNER_LABELS[r.winner] || "決着なし") + "</span>"],
    ["勝ったMBTI", esc(winningMbti())],
    ["人狼だったMBTI", esc(wolves)],
    ["処刑された人", r.executed ? who(r.executed) : "—"],
    ["最も疑われた人", esc(topOf("suspected_by_count"))],
    ["最も発言した人", esc(topOf("speech_count"))],
    ["決着方法", r.tie_break ? esc("同数得票のため " + r.tie_break.method) : "最多得票が1人"],
  ];
  return '<div class="cards">' + cards.map((c) =>
    '<div class="card"><div class="label">' + esc(c[0]) + '</div><div class="value">' + c[1] + "</div></div>"
  ).join("") + "</div>";
}

function renderMetrics() {
  const rows = (log.metrics && log.metrics.per_player) || [];
  if (!rows.length) return "<p>集計はありません。</p>";
  const head = ["ID", "心理機能", "MBTI", "役職", "発言数", "平均文字数", "投票先", "勝敗", "疑い", "疑われ", "質問", "反論", "同調", "仮説"];
  const body = rows.map((r) => "<tr>" + [
    r.player_id,
    r.function + (FUNCTION_LABELS[r.function] ? "（" + FUNCTION_LABELS[r.function] + "）" : ""),
    identityOf(r),
    ROLE_LABELS[r.role] || r.role,
    r.speech_count, r.avg_chars, r.final_vote || "—",
    r.win === null || r.win === undefined ? "—" : (r.win ? "勝ち" : "負け"),
    r.suspicion_count, r.suspected_by_count, r.question_count,
    r.rebuttal_count, r.agreement_count, r.hypothesis_count,
  ].map((v) => "<td>" + esc(v) + "</td>").join("") + "</tr>").join("");
  return '<div class="scroll"><table><thead><tr>' + head.map((h) => "<th>" + esc(h) + "</th>").join("")
    + "</tr></thead><tbody>" + body + "</tbody></table></div>";
}

function renderTimeline() {
  const turns = log.turns || [];
  if (!turns.length) return "<p>発言はまだ記録されていません。</p>";
  let html = "";
  let current = null;
  turns.forEach((t) => {
    if (t.turn !== current) {
      current = t.turn;
      html += '<div class="turn">ターン ' + esc(current) + " / " + esc((log.config || {}).turn_count) + "</div>";
    }
    const flags = [];
    if (t.parse_failed) flags.push("形式が崩れた応答");
    if (t.wait_seconds) flags.push(t.wait_seconds + "秒");
    html += '<div class="speech"><div class="who">' + who(t.player_id)
      + flags.map((f) => '<span class="badge">' + esc(f) + "</span>").join("")
      + "</div>" + esc(t.speech_text) + "</div>";
  });
  return html;
}

function renderVotes() {
  const votes = log.votes || [];
  if (!votes.length) return "<p>投票はまだ記録されていません。</p>";
  const counts = (log.result || {}).vote_counts || {};
  const tally = Object.keys(counts).map((k) => k + " " + counts[k] + "票").join("、");
  const body = votes.map((v) => "<tr><td>" + who(v.voter) + "</td><td>" + esc(v.target) + "</td>"
    + '<td class="wrap">' + esc(v.reason) + "</td><td>"
    + (v.fallback ? "乱数で決定" : (v.invalid_retry_count ? "再要求" + v.invalid_retry_count + "回" : "—"))
    + "</td></tr>").join("");
  return (tally ? "<p>得票: " + esc(tally) + "</p>" : "")
    + '<div class="scroll"><table><thead><tr><th>投票者</th><th>投票先</th><th class="wrap">理由</th><th>備考</th></tr></thead><tbody>'
    + body + "</tbody></table></div>";
}

function renderConditions() {
  const c = log.config || {};
  const t = log.timing || {};
  const b = log.brain || {};
  const items = [
    ["run_id", log.run_id], ["series_id", log.series_id],
    ["参加人数", (c.player_count || "") + "人"], ["議論ターン数", c.turn_count],
    ["seed", c.seed], ["base_seed", c.base_seed],
    ["役職割当方式", c.role_assignment_mode], ["心理機能", (c.functions || []).join("、")],
    ["history_mode", c.history_mode],
    ["使用した脳", [b.provider, b.model, b.endpoint_kind].filter(Boolean).join(" / ")],
    ["実行環境", t.machine_name], ["開始", t.started_at], ["終了", t.ended_at],
    ["所要時間", (t.elapsed_seconds || 0) + "秒"], ["AI待機時間", (t.ai_wait_seconds || 0) + "秒"],
    ["プロンプト版", ((log.players || [])[0] || {}).agent_prompt_version],
    ["schema_version", log.schema_version],
  ];
  return '<div class="panel"><dl class="kv">' + items.map((i) =>
    "<dt>" + esc(i[0]) + "</dt><dd>" + esc(i[1] === undefined || i[1] === null || i[1] === "" ? "—" : i[1]) + "</dd>"
  ).join("") + "</dl></div>";
}

document.getElementById("head-sub").textContent =
  log.run_id + "  /  " + (log.timing || {}).started_at + "  /  状態: " + log.status;

document.getElementById("app").innerHTML = [
  renderFailure(),
  renderCards(),
  "<h2>参加者</h2>", renderRoster(),
  "<h2>会話タイムライン</h2>", renderTimeline(),
  "<h2>投票</h2>", renderVotes(),
  "<h2>メトリクス</h2>", renderMetrics(),
  "<h2>実行条件</h2>", renderConditions(),
].join("");

document.getElementById("foot-note").innerHTML = [
  "MBTIおよび心理機能は、実在人物の診断や評価ではない。AIエージェントの振る舞いを分けるためのフィクション設定として扱っている。",
  hasConfirmedMbti()
    ? "MBTIタイプが確定しているプレイヤーはそのタイプ名で表示している。確定していないプレイヤーは主機能からの候補2タイプ（要求定義書6.5）を表示している。"
    : "MBTIは主機能からの候補2タイプ（要求定義書6.5）。1人に心理機能を1つだけ持たせているため、タイプは一意に決まらない。",
  "このファイルは実行結果を埋め込んだ自己完結HTMLで、外部との通信を行わない。",
].map(esc).join("<br>");
</script>
</body>
</html>
"""


def render_result_html(run_log: Dict[str, Any]) -> str:
    from ..agents.functions import FUNCTION_RULES
    from ..agents.mbti_types import DOMINANT_TO_TYPES

    labels = {code: rule["label"] for code, rule in FUNCTION_RULES.items()}
    return (
        _TEMPLATE.replace("__RUN_ID__", str(run_log.get("run_id", "")))
        .replace("__FUNCTION_LABELS__", _embed(labels))
        .replace("__DOMINANT_TO_MBTI__", _embed(DOMINANT_TO_TYPES))
        .replace("__RUN_DATA__", _embed(run_log))
    )


def _embed(value: Any) -> str:
    """HTMLへ埋め込める形にJSONを直列化する。

    </script> でHTMLが途切れないように < と > をエスケープする。
    """
    return (
        json.dumps(value, ensure_ascii=False)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )
