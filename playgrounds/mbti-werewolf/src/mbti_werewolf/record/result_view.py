"""ケースの `result.html`（設計書6.10、7.5）。

外部からデータを取得しない自己完結HTMLにする。`file://` で直接開いてもGitHub Pages
経由でも同じように表示されるため、実行環境を持たないメンバーがブラウザだけで結果を
読める（NF-15）。

中身はv1から流用せず新規に作る。v1は4人・心理機能1つ・ターン固定を前提に表示して
おり、v2は8人・自由議論・private memo・両時点の個別判断を出すため、表示する項目が
ほぼ入れ替わる。CSSと最新結果リンクの仕組みだけv1と同じ考え方を使う（設計書0.4）。
"""

from __future__ import annotations

import html
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..engine.roles import TEAM_WEREWOLF, role_label, team_of
from .case_metrics import SUSPECT_UNKNOWN, case_metrics, player_metrics
from .transcript import night_steps

_GENDER_LABELS = {"male": "男性", "female": "女性"}

PASS_TEXT = "（見送り）"
SKIP_TEXT = "（応答が得られず記録なし）"
MISSING_TEXT = "—"

_STOP_REASONS = {
    "all_pass": "そのラウンドの対象者全員が見送った",
    "max_rounds": "ラウンド数が上限に達した",
    "max_speeches": "発言数が上限に達した",
    "max_total_chars": "発言量が上限に達した",
}


def _esc(value: Any) -> str:
    if value is None:
        return ""
    return html.escape(str(value), quote=True)


def _upper(player_id: Optional[str]) -> str:
    return player_id.upper() if player_id else ""


def _suspect_text(suspect: Optional[str]) -> str:
    if suspect is None:
        return MISSING_TEXT
    if suspect == SUSPECT_UNKNOWN:
        return "判断不能"
    return _upper(suspect)


def _num(value: Any, suffix: str = "") -> str:
    if value is None:
        return MISSING_TEXT
    return "{0}{1}".format(value, suffix)


# 表示だけを担うため、HTMLは素の文字列で組む。テンプレートエンジンを入れると
# 依存が増え、`file://` で開く自己完結HTMLという性質と釣り合わない。
_STYLE = """
:root {
  --bg: #f5f6f8;
  --panel: #ffffff;
  --line: #e2e5ea;
  --text: #1f2328;
  --muted: #667085;
  --accent: #3b66d6;
  --village: #1f9d55;
  --werewolf: #d1373f;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  padding: 0 0 64px;
  background: var(--bg);
  color: var(--text);
  font-family: "Hiragino Sans", "Noto Sans JP", system-ui, sans-serif;
  line-height: 1.7;
}
main { max-width: 960px; margin: 0 auto; padding: 20px 16px 0; }
.site-header { background: #fff; border-bottom: 1px solid var(--line); }
.site-header-inner { max-width: 960px; margin: 0 auto; padding: 14px 16px; display: flex;
  align-items: baseline; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.brand { font-size: 17px; font-weight: 700; }
.brand-accent { color: var(--accent); font-weight: 500; }
.chip { font-size: 11px; padding: 3px 10px; border-radius: 999px; border: 1px solid var(--line);
  color: var(--muted); font-family: ui-monospace, Menlo, monospace; }
.chip.village { border-color: var(--village); color: var(--village); }
.chip.werewolf { border-color: var(--werewolf); color: var(--werewolf); }
.site-nav { max-width: 960px; margin: 0 auto; display: flex; gap: 4px; overflow-x: auto;
  padding: 0 16px 10px; }
.site-nav a { flex-shrink: 0; font-size: 12px; color: var(--muted); text-decoration: none;
  padding: 6px 12px; border-radius: 999px; border: 1px solid transparent; }
.site-nav a:hover { color: var(--text); border-color: var(--line); }
h1 { font-size: 19px; margin: 0 0 4px; }
h2 { font-size: 16px; margin: 36px 0 12px; padding-left: 10px; border-left: 3px solid var(--accent); }
h3 { font-size: 13px; color: var(--muted); margin: 20px 0 8px; }
.sub { color: var(--muted); font-size: 13px; margin: 0 0 20px; }
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; }
.card { background: var(--panel); border: 1px solid var(--line); border-radius: 12px; padding: 12px 14px; }
.card .label { color: var(--muted); font-size: 12px; }
.card .value { font-size: 17px; margin-top: 4px; word-break: break-word; }
.village { color: var(--village); }
.werewolf { color: var(--werewolf); }
.scroll { overflow-x: auto; border: 1px solid var(--line); border-radius: 10px; background: var(--panel); }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td { padding: 8px 10px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }
th { color: var(--muted); font-weight: 600; white-space: nowrap; }
tr:last-child td { border-bottom: none; }
tbody tr:nth-child(even) { background: rgba(15, 23, 42, 0.025); }
td.memo { color: var(--muted); font-size: 12px; }
/* 項目名と値の2列だけの表。項目名を折り返させず、値側を伸ばす。 */
table.kv th[scope="row"] { width: 1%; }
table.kv td { overflow-wrap: anywhere; }
td.quiet { color: var(--muted); }
td.id { font-family: ui-monospace, Menlo, monospace; white-space: nowrap; }
.badge { display: inline-block; font-size: 11px; padding: 1px 6px; border-radius: 999px;
  border: 1px solid var(--line); color: var(--muted); }
.badge.village { border-color: var(--village); color: var(--village); }
.badge.werewolf { border-color: var(--werewolf); color: var(--werewolf); }
.alert { background: #fdecee; border: 1px solid #f3b4bb; border-radius: 10px; padding: 12px 16px;
  margin-bottom: 20px; }
.note { color: var(--muted); font-size: 12px; margin-top: 36px; border-top: 1px solid var(--line);
  padding-top: 16px; }
.links { display: flex; gap: 12px; flex-wrap: wrap; font-size: 13px; margin: 0 0 8px; }

/* 狭い画面では表を1行1ブロックへ折り返す。要求定義書がスマートフォンから結果を
   開くことを重視項目に挙げており、横スクロールのままだとprivate memoの列が画面外
   に出て読めない。各セルの見出しは data-label から出す。

   table と tbody も display: block にする。display: table のままだと表のレイアウト
   計算が働き、width: 100% より内容の最小幅が優先されて画面からはみ出す。 */
@media (max-width: 640px) {
  table.stack, table.stack tbody { display: block; width: 100%; }
  table.stack thead { display: none; }
  table.stack tr { display: block; padding: 10px 12px; border-bottom: 1px solid var(--line); }
  table.stack tr:last-child { border-bottom: none; }
  table.stack td { display: flex; gap: 10px; padding: 2px 0; border: none; white-space: normal; }
  table.stack td::before {
    content: attr(data-label);
    flex: 0 0 6.5em;
    color: var(--muted);
    font-size: 11px;
    padding-top: 2px;
  }
  table.stack td > span.grow { flex: 1; min-width: 0; overflow-wrap: anywhere; }
  /* 中身が空のセルは行から消す。横並びの表では列を揃えるために必要だが、
     縦に積むと項目名だけの行になって読みにくい。 */
  table.stack td.blank { display: none; }
  th, td { padding: 7px 8px; font-size: 12px; overflow-wrap: anywhere; }
}
"""

_NAV = (
    ("sec-result", "結果"),
    ("sec-roster", "参加者"),
    ("sec-night", "夜処理"),
    ("sec-discussion", "公開議論"),
    ("sec-votes", "投票"),
    ("sec-answers", "個別判断"),
    ("sec-metrics", "指標"),
    ("sec-conditions", "実行条件"),
)


def render_result_html(case_log: Dict[str, Any]) -> str:
    metrics = case_metrics(case_log)
    rows = player_metrics(case_log)
    result = case_log["result"]

    nav = "".join(
        '<a href="#{0}">{1}</a>'.format(anchor, label) for anchor, label in _NAV
    )

    parts = [
        "<!DOCTYPE html>",
        '<html lang="ja">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>ケース {0}</title>".format(_esc(case_log["case_id"])),
        "<style>{0}</style>".format(_STYLE),
        "</head>",
        "<body>",
        '<header class="site-header">',
        '  <div class="site-header-inner">',
        '    <div class="brand">MBTI人狼 <span class="brand-accent">ケース結果</span></div>',
        "    {0}".format(_status_chip(case_log)),
        "  </div>",
        '  <nav class="site-nav">{0}</nav>'.format(nav),
        "</header>",
        "<main>",
        "<h1>{0}</h1>".format(_esc(case_log["case_id"])),
        '<p class="sub">{0}</p>'.format(_esc(_headline(case_log))),
        _links(),
    ]

    if case_log.get("failure"):
        parts.append(_failure(case_log))

    parts.append(_result_section(case_log, metrics, result))
    parts.append(_roster_section(case_log, rows))
    parts.append(_night_section(case_log))
    parts.append(_discussion_section(case_log))
    parts.append(_votes_section(case_log))
    parts.append(_answers_section(rows))
    parts.append(_metrics_section(metrics))
    parts.append(_conditions_section(case_log))
    parts.append(
        '<p class="note">この画面は実行時に生成された自己完結HTMLである。'
        "会話全文は <code>transcript.md</code>、生データは <code>case_log.json</code> にある。"
        "MBTIタイプは参加者本人へは一切渡していない。</p>"
    )
    parts.extend(["</main>", "</body>", "</html>", ""])
    return "\n".join(parts)


def _status_chip(case_log: Dict[str, Any]) -> str:
    result = case_log["result"]
    if case_log["status"] != "done":
        return '<div class="chip werewolf">{0}</div>'.format(_esc(case_log["status"]))
    if not result["valid"]:
        return '<div class="chip">無効試合</div>'
    winner = result["winner"]
    label = "村人陣営の勝利" if winner == "village" else "人狼陣営の勝利"
    css = "village" if winner == "village" else "werewolf"
    return '<div class="chip {0}">{1}</div>'.format(css, label)


def _headline(case_log: Dict[str, Any]) -> str:
    if case_log["composition"] == "mixed":
        composition = "混合構成（人物プールのMBTIをそのまま使用）"
    else:
        composition = "同質構成（8人全員が {0}）".format(case_log["homogeneous_type"])
    return "{0} / Trial {1} / ルール {2}".format(
        composition,
        case_log["config"]["trial_index"],
        case_log["versions"]["rule_set_id"],
    )


def _links() -> str:
    return (
        '<p class="links">'
        '<a href="./transcript.md">会話全文（transcript.md）</a>'
        '<a href="./summary.md">要約（summary.md）</a>'
        '<a href="./case_log.json">生データ（case_log.json）</a>'
        "</p>"
    )


def _failure(case_log: Dict[str, Any]) -> str:
    failure = case_log["failure"] or {}
    return (
        '<div class="alert"><strong>このケースは失敗して終わった。</strong><br>'
        "種別: {0}<br>内容: {1}<br>試行回数: {2}</div>".format(
            _esc(failure.get("kind")),
            _esc(failure.get("message")),
            _esc(case_log.get("attempt")),
        )
    )


def _card(label: str, value: str, css: str = "") -> str:
    return '<div class="card"><div class="label">{0}</div><div class="value {2}">{1}</div></div>'.format(
        _esc(label), value, css
    )


def _result_section(
    case_log: Dict[str, Any], metrics: Dict[str, Any], result: Dict[str, Any]
) -> str:
    if not result["valid"]:
        return (
            '<h2 id="sec-result">結果</h2>'
            '<div class="cards">{0}{1}</div>'.format(
                _card("結果", "無効試合"),
                _card("理由", _esc("有効投票なし")),
            )
        )

    winner = result["winner"]
    winner_label = "村人陣営" if winner == "village" else "人狼陣営"
    executed = (
        "、".join(_upper(pid) for pid in result["executed"])
        if result["executed"]
        else "なし（最多得票が1票）"
    )
    tally = "、".join(
        "{0} {1}票".format(_upper(pid), count)
        for pid, count in sorted(
            result["vote_tally"].items(), key=lambda kv: (-kv[1], kv[0])
        )
    )

    cards = [
        _card("勝敗", _esc(winner_label), "village" if winner == "village" else "werewolf"),
        _card("追放者", _esc(executed)),
        _card("得票", _esc(tally or "なし")),
        _card(
            "有効票 / 棄権",
            _esc("{0}票 / {1}件".format(result["valid_vote_count"], result["abstain_count"])),
        ),
        _card("議論ラウンド", _esc("{0}（{1}）".format(
            case_log["discussion"]["rounds"],
            _STOP_REASONS.get(case_log["discussion"]["stop_reason"] or "", "不明"),
        ))),
        _card("推論呼び出し", _esc("{0}回".format(case_log["timing"]["inference_calls"]))),
    ]
    return '<h2 id="sec-result">結果</h2><div class="cards">{0}</div>'.format("".join(cards))


def _cells(*pairs: Any) -> str:
    """`(見出し, 中身, css)` の並びを `<td>` へ変える。

    見出しを `data-label` へ入れる。狭い画面で表を1行1ブロックへ折り返すとき、
    CSSがこの属性から項目名を出す（`table.stack`）。
    """

    parts = []
    for pair in pairs:
        label, value = pair[0], pair[1]
        classes = [pair[2]] if len(pair) > 2 and pair[2] else []
        if not value:
            classes.append("blank")
        attr = ' class="{0}"'.format(" ".join(classes)) if classes else ""
        parts.append(
            '<td data-label="{0}"{1}><span class="grow">{2}</span></td>'.format(
                _esc(label), attr, value
            )
        )
    return "".join(parts)


def _roster_section(case_log: Dict[str, Any], rows: List[Dict[str, Any]]) -> str:
    by_id = {row["player_id"]: row for row in rows}
    executed = set(case_log["result"]["executed"])

    body = []
    for player in case_log["players"]:
        row = by_id[player["player_id"]]
        team = team_of(player["final_role"])
        badge = '<span class="badge {0}">{1}</span>'.format(
            "werewolf" if team == TEAM_WEREWOLF else "village",
            "人狼陣営" if team == TEAM_WEREWOLF else "村人陣営",
        )
        body.append(
            "<tr>{0}</tr>".format(
                _cells(
                    ("ID", _esc(_upper(player["player_id"])), "id"),
                    ("MBTI", _esc(player["mbti"])),
                    ("人物", _esc(player["person_id"]), "id"),
                    (
                        "属性",
                        _esc(
                            "{0}歳・{1}".format(
                                player["age"],
                                _GENDER_LABELS.get(player["gender"], player["gender"]),
                            )
                        ),
                    ),
                    ("開始時役職", _esc(role_label(player["initial_role"]))),
                    (
                        "最終役職",
                        "{0} {1}".format(_esc(role_label(player["final_role"])), badge),
                    ),
                    ("発言", _esc("{0}回".format(row["speech_count"]))),
                    ("見送り", _esc("{0}回".format(row["pass_count"]))),
                    ("投票結果", "追放" if player["player_id"] in executed else ""),
                )
            )
        )

    return (
        '<h2 id="sec-roster">参加者</h2>'
        '<div class="scroll"><table class="stack"><thead><tr>'
        "<th>ID</th><th>MBTI</th><th>人物</th><th>属性</th>"
        "<th>開始時役職</th><th>最終役職</th><th>発言</th><th>見送り</th><th></th>"
        "</tr></thead><tbody>{0}</tbody></table></div>"
        '<p class="sub">MBTIはこの画面と <code>summary.md</code> だけに出る。'
        "参加者本人へは渡していない。</p>".format("".join(body))
    )


def _night_section(case_log: Dict[str, Any]) -> str:
    """夜処理は表ではなく文章にする。`transcript.md` と同じ文言を使う。"""

    steps = night_steps(case_log)
    if not steps:
        return '<h2 id="sec-night">夜処理</h2><p class="sub">夜処理はなかった。</p>'
    body = "".join("<li>{0}</li>".format(_esc(step)) for step in steps)
    return '<h2 id="sec-night">夜処理</h2><ol>{0}</ol>'.format(body)


def _discussion_section(case_log: Dict[str, Any]) -> str:
    discussion = case_log["discussion"]
    events = discussion["events"]
    if not events:
        return '<h2 id="sec-discussion">公開議論</h2><p class="sub">発言はなかった。</p>'

    rounds: Dict[int, List[Dict[str, Any]]] = {}
    for event in events:
        rounds.setdefault(event["round"], []).append(event)

    parts = ['<h2 id="sec-discussion">公開議論</h2>']
    parts.append(
        '<p class="sub">private memo は本人だけが持つ非公開の一言である。'
        "他の参加者へは渡していない。</p>"
    )
    for round_no in sorted(rounds):
        body = []
        for event in rounds[round_no]:
            if event["spoke"]:
                speech = _esc(event.get("speech_text", ""))
                css = ""
            else:
                speech = _esc(SKIP_TEXT if event["skipped"] else PASS_TEXT)
                css = "quiet"
            memo = _esc(event.get("memo") or "") or MISSING_TEXT
            body.append(
                "<tr>{0}</tr>".format(
                    _cells(
                        ("ID", _esc(_upper(event["player_id"])), "id"),
                        ("公開発言", speech, css),
                        ("memo", memo, "memo"),
                    )
                )
            )
        parts.append("<h3>第{0}ラウンド</h3>".format(round_no))
        parts.append(
            '<div class="scroll"><table class="stack"><thead><tr><th>ID</th>'
            "<th>公開発言</th><th>private memo</th></tr></thead>"
            "<tbody>{0}</tbody></table></div>".format("".join(body))
        )

    parts.append(
        '<p class="sub">終了理由: {0}（{1}ラウンド、発言{2}件、見送り{3}件、スキップ{4}件）</p>'.format(
            _esc(_STOP_REASONS.get(discussion["stop_reason"] or "", "不明")),
            discussion["rounds"],
            sum(1 for e in events if e["spoke"]),
            sum(1 for e in events if not e["spoke"] and not e["skipped"]),
            sum(1 for e in events if e["skipped"]),
        )
    )
    return "".join(parts)


def _votes_section(case_log: Dict[str, Any]) -> str:
    body = []
    for vote in case_log["votes"]:
        target = "（棄権）" if vote["abstained"] else _upper(vote["target"])
        memo = _esc(vote.get("memo") or "") or MISSING_TEXT
        body.append(
            "<tr>{0}</tr>".format(
                _cells(
                    ("ID", _esc(_upper(vote["voter"])), "id"),
                    ("投票先", _esc(target), "id"),
                    ("memo", memo, "memo"),
                )
            )
        )
    return (
        '<h2 id="sec-votes">投票</h2>'
        '<div class="scroll"><table class="stack"><thead><tr><th>ID</th>'
        "<th>投票先</th><th>private memo</th></tr></thead>"
        "<tbody>{0}</tbody></table></div>".format("".join(body))
    )


def _answers_section(rows: List[Dict[str, Any]]) -> str:
    body = []
    for row in rows:
        correct = row["vote_correct"]
        body.append(
            "<tr>{0}</tr>".format(
                _cells(
                    ("ID", _esc(_upper(row["player_id"])), "id"),
                    ("議論前の疑い", _esc(_suspect_text(row["pre_suspect"]))),
                    ("議論前の自信", _esc(_num(row["pre_confidence"]))),
                    ("投票前の疑い", _esc(_suspect_text(row["final_suspect"]))),
                    ("投票前の自信", _esc(_num(row["final_confidence"]))),
                    ("投票予定", _esc(_suspect_text(row["planned_vote"]))),
                    (
                        "実際の投票",
                        _esc("（棄権）" if row["abstained"] else _upper(row["actual_vote"])),
                    ),
                    (
                        "正答",
                        "○" if correct == 1 else ("×" if correct == 0 else MISSING_TEXT),
                    ),
                )
            )
        )
    return (
        '<h2 id="sec-answers">個別判断（議論前 → 投票前）</h2>'
        '<div class="scroll"><table class="stack"><thead><tr><th>ID</th>'
        "<th>議論前の疑い</th><th>自信</th>"
        "<th>投票前の疑い</th><th>自信</th><th>投票予定</th><th>実際の投票</th><th>正答</th>"
        "</tr></thead><tbody>{0}</tbody></table></div>"
        '<p class="sub">「正答」は投票先の最終役職が人狼だったかを示す。'
        "棄権と応答なしは {1} にする。</p>".format("".join(body), MISSING_TEXT)
    )


def _metrics_section(metrics: Dict[str, Any]) -> str:
    shown = (
        ("village_correct", "追放者に人狼が含まれたか"),
        ("village_vote_accuracy", "人狼以外6人の投票が人狼へ向いた割合"),
        ("vote_concentration", "最多得票数 ÷ 有効票数"),
        ("final_entropy", "最終発言時点の疑念の散らばり"),
        ("convergence_round", "疑いが固定した最初のラウンド"),
        ("correction_rate", "誤った判断を投票前に正した割合"),
        ("deterioration_rate", "正しい判断を投票前に誤った割合"),
        ("mean_confidence_delta", "自信度の平均変化"),
        ("plan_vote_mismatch_rate", "投票予定と実際の投票のずれ"),
        ("pass_rate", "見送り ÷ 問い合わせ"),
        ("speech_count_gini", "発言回数の偏り（0が均等）"),
    )
    body = "".join(
        "<tr>{0}</tr>".format(
            _cells(
                ("指標", "<code>{0}</code>".format(_esc(key))),
                ("値", _esc(_num(metrics[key]))),
                ("意味", _esc(label)),
            )
        )
        for key, label in shown
    )
    return (
        '<h2 id="sec-metrics">指標</h2>'
        '<div class="scroll"><table class="stack"><thead><tr><th>指標</th><th>値</th>'
        "<th>意味</th>"
        "</tr></thead><tbody>{0}</tbody></table></div>"
        '<p class="sub"><code>final_entropy</code> と <code>convergence_round</code> は'
        "公開スタンス系列が必要なため、Judgeを実行するまで {1} のままである。</p>".format(
            body, MISSING_TEXT
        )
    )


def _conditions_section(case_log: Dict[str, Any]) -> str:
    versions = case_log["versions"]
    config = case_log["config"]
    brain = case_log["brain"]
    timing = case_log["timing"]
    limits = case_log["discussion"]["limits"]

    items = [
        ("ルールセット", "{0} v{1}".format(versions["rule_set_id"], versions["rule_set_version"])),
        ("人格プロンプト版", versions["persona_prompt_version"]),
        ("Judge評価基準版", versions["judge_criteria_version"]),
        (
            "指標版",
            "{0}（確定日 {1}）".format(
                config["indicator_version"], config["indicator_frozen_at"] or "未確定"
            ),
        ),
        ("人物プール / パターン", "{0} / {1}".format(versions["pool_id"], versions["pattern_id"])),
        ("Trial / seed", "{0} / {1}".format(config["trial_index"], config["trial_seed"])),
        ("使用モデル", "{0}（{1}）".format(brain.get("model") or MISSING_TEXT, brain.get("provider"))),
        (
            "議論の上限",
            "max_rounds={0}、max_speeches={1}、max_total_chars={2}、"
            "max_speech_chars={3}、max_consecutive_speeches={4}".format(
                limits["max_rounds"],
                limits["max_speeches"],
                limits["max_total_chars"],
                limits["max_speech_chars"],
                limits["max_consecutive_speeches"],
            ),
        ),
        (
            "実行時間",
            "{0}秒（うちAI待機 {1}秒、呼び出し{2}回）".format(
                timing["elapsed_seconds"], timing["ai_wait_seconds"], timing["inference_calls"]
            ),
        ),
        ("実行機", timing["machine_name"]),
    ]
    body = "".join(
        '<tr><th scope="row">{0}</th><td>{1}</td></tr>'.format(_esc(label), _esc(value))
        for label, value in items
    )
    return (
        '<h2 id="sec-conditions">実行条件</h2>'
        '<div class="scroll"><table class="kv"><tbody>{0}</tbody></table></div>'.format(body)
    )


def write_result_html(path: Path, case_log: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_result_html(case_log), encoding="utf-8")


def render_failure_html(
    case_id: str,
    composition: str,
    homogeneous_type: Optional[str],
    error: Dict[str, str],
    attempt: int,
) -> str:
    """ケースが失敗して `case_log.json` が無いときの `result.html`（設計書7.5）。

    通常の結果ページと同じ場所に同じ名前で置く。失敗したケースだけHTMLが無い形に
    すると、一覧から開いたときに404になり、失敗したのか未実行なのかが分からない。
    """

    if composition == "mixed":
        composition_text = "混合構成"
    else:
        composition_text = "同質構成（{0}）".format(homogeneous_type)

    return "\n".join(
        [
            "<!DOCTYPE html>",
            '<html lang="ja">',
            "<head>",
            '<meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            "<title>ケース {0}（失敗）</title>".format(_esc(case_id)),
            "<style>{0}</style>".format(_STYLE),
            "</head>",
            "<body>",
            '<header class="site-header"><div class="site-header-inner">',
            '<div class="brand">MBTI人狼 <span class="brand-accent">ケース結果</span></div>',
            '<div class="chip werewolf">失敗</div>',
            "</div></header>",
            "<main>",
            "<h1>{0}</h1>".format(_esc(case_id)),
            '<p class="sub">{0}</p>'.format(_esc(composition_text)),
            '<div class="alert"><strong>このケースは完走しなかった。</strong><br>'
            "種別: {0}<br>内容: {1}<br>試行回数: {2}</div>".format(
                _esc(error.get("kind")), _esc(error.get("message")), _esc(attempt)
            ),
            '<p class="note">再実行するには <code>--resume</code> を付けて同じ実験IDを'
            "指定する。完了済みのケースは実行されない。</p>",
            "</main>",
            "</body>",
            "</html>",
            "",
        ]
    )


def write_failure_html(
    path: Path, case, error: Dict[str, str], attempt: int
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        render_failure_html(
            case.case_id, case.composition, case.homogeneous_type, error, attempt
        ),
        encoding="utf-8",
    )


_LATEST_TEMPLATE = """<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="0; url=./__TARGET__">
<title>最新のケース結果へ移動</title>
<style>
body { font-family: "Hiragino Sans", "Noto Sans JP", system-ui, sans-serif; margin: 0;
  padding: 48px 20px; line-height: 1.8; color: #1f2328; }
a { color: #3b66d6; }
code { font-family: ui-monospace, Menlo, monospace; }
</style>
</head>
<body>
<p>最新の結果（<code>__CASE_ID__</code>）へ移動します。
自動で切り替わらない場合は<a href="./__TARGET__">こちらをタップ</a>してください。</p>
</body>
</html>
"""


def render_latest_redirect(case_id: str, target: str) -> str:
    """最新のケース結果への転送ページ（設計書7.6）。

    メタリフレッシュに対応しないブラウザ（アプリ内ブラウザなど）でも辿れるよう、
    手動リンクを必ず添える。v1の `latest.html` と同じ考え方である。

    M3では最新ケースの `result.html` を指す。`analyze` の後は実験の `experiment.html` へ向け直す（7.6）。
    """

    return _LATEST_TEMPLATE.replace("__TARGET__", target).replace("__CASE_ID__", case_id)


def write_latest_redirect(runs_dir: Path, case_id: str, target: str) -> Path:
    path = runs_dir / "latest.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_latest_redirect(case_id, target), encoding="utf-8")
    return path
