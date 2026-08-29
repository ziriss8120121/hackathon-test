"""ケースの通読用Markdown（設計書6.10）。

先行実験の[WORLD A結果](../../../../docs/m-plus-experiment/04_world-A-result_v1.md)と
[WORLD B結果](../../../../docs/m-plus-experiment/05_world-B-result_v1.md)と同じ構成に
する。章の順序と表の列を揃えているため、先行実験の結果と本システムの出力を並べて
読める。

MBTIタイプ名はここへ書かない。先行実験の結果文書が結果側にタイプ名を出していない
ため、形式を揃えている。MBTIは `summary.md` と `case_log.json` で確認する。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from ..engine.roles import role_label

PASS_TEXT = "（見送り）"
SKIP_TEXT = "（応答が得られず記録なし）"
EMPTY_MEMO = "—"

_GENDER_LABELS = {"male": "男性", "female": "女性"}

_NIGHT_ORDER_TEXT = "占い師 → 人狼 → 怪盗"


def _upper(player_id: Optional[str]) -> str:
    return player_id.upper() if player_id else ""


def _cell(text: str) -> str:
    """表のセル。改行と縦棒が入ると表が壊れるため落とす。"""

    if not text:
        return ""
    return " ".join(str(text).split()).replace("|", "／")


def render_transcript(case_log: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("# ケース {0}".format(case_log["case_id"]))
    lines.append("")
    lines.extend(_conditions(case_log))
    lines.extend(_initial_roles(case_log))
    lines.extend(_night(case_log))
    lines.extend(_discussion(case_log))
    lines.extend(_votes(case_log))
    lines.extend(_result(case_log))
    return "\n".join(lines).rstrip() + "\n"


def _conditions(case_log: Dict[str, Any]) -> List[str]:
    versions = case_log["versions"]
    config = case_log["config"]
    limits = case_log["discussion"]["limits"]
    brain = case_log["brain"]
    players = case_log["players"]

    composition = case_log["composition"]
    if composition == "mixed":
        composition_text = "混合構成"
    else:
        composition_text = "同質構成（全員が同じ性格傾向）"

    attributes = "、".join(
        "{0} {1}歳・{2}".format(
            _upper(p["player_id"]), p["age"], _GENDER_LABELS.get(p["gender"], p["gender"])
        )
        for p in players
    )

    limit_text = "、".join(
        [
            "max_rounds={0}".format(limits["max_rounds"]),
            "max_speeches={0}".format(limits["max_speeches"]),
            "max_total_chars={0}".format(limits["max_total_chars"]),
            "max_speech_chars={0}".format(limits["max_speech_chars"]),
            "max_consecutive_speeches={0}".format(limits["max_consecutive_speeches"]),
        ]
    )

    lines = [
        "## 実行条件（固定記録）",
        "",
        "- ルール正本: `01_werewolf-rules_v{0}.md`（v{0}）".format(
            versions["rule_set_version"]
        ),
        "- Agent設定正本: `02_agent-settings_v1.md`（v1）",
        "- 実験計画正本: `03_experiment-plan_v1.md`（v1）",
        "- ルールセット: `{0}`".format(versions["rule_set_id"]),
        "- 人格プロンプト版: `{0}`".format(versions["persona_prompt_version"]),
        "- 人物プール / パターン: `{0}` / `{1}`".format(
            versions["pool_id"], versions["pattern_id"]
        ),
        "- seed: `{0}`（Trial {1}）".format(config["trial_seed"], config["trial_index"]),
        "- 役職配布手順: `random.Random({0})` で `[人狼, 人狼, 占い師, 怪盗, 村人, 村人, 村人, 村人]` をシャッフルし、P1から順に配布".format(
            config["trial_seed"]
        ),
        "- 使用モデル: {0}（{1}）".format(
            brain.get("model") or brain.get("provider"), brain.get("provider")
        ),
        "- Agent生成条件: 8体を独立起動し、各Agentに渡した公開情報・個別通知・公開ログだけを保持。ゲーム開始前の自伝的記憶および人狼経験なし。",
        "- 参加者属性: {0}。".format(attributes),
        "- 構成種別: {0}".format(composition_text),
        "- 議論方式: 自由議論。ラウンドごとに全員へ発言機会を与え、各自が発言か見送りを選ぶ。",
        "- 議論の上限: {0}".format(limit_text),
        "- 問い合わせ順: ラウンドごとに `random.Random(\"{0}:ラウンド番号\")` で決定".format(
            config["trial_seed"]
        ),
        "- 夜処理順: {0}".format(_NIGHT_ORDER_TEXT),
        "- 個別の行動傾向: 参加者ごとに1文を付与。タイプ名は参加者へ渡していない。",
        "- 異常処理: {0}".format(_anomaly_text(case_log)),
        "",
    ]
    return lines


def _anomaly_text(case_log: Dict[str, Any]) -> str:
    """応答が得られなかった箇所をまとめる。なければ「なし」と書く。"""

    notes: List[str] = []
    for action in case_log["night_actions"]:
        if action.get("skip_reason"):
            notes.append(
                "{0}の{1}で有効な回答が得られず能力未使用".format(
                    _upper(action["actor"]), _phase_label(action["phase"])
                )
            )
    skips = [e for e in case_log["discussion"]["events"] if e.get("skipped")]
    if skips:
        notes.append("公開議論で{0}件のスキップ".format(len(skips)))
    abstains = [v for v in case_log["votes"] if v.get("abstained")]
    if abstains:
        notes.append(
            "投票で{0}件の棄権（{1}）".format(
                len(abstains), "、".join(_upper(v["voter"]) for v in abstains)
            )
        )
    failed_answers = [
        a
        for a in case_log["pre_discussion_answers"] + case_log["pre_vote_answers"]
        if a.get("parse_failed")
    ]
    if failed_answers:
        notes.append("個別判断で{0}件の応答失敗".format(len(failed_answers)))
    return "、".join(notes) if notes else "なし"


def _phase_label(phase: str) -> str:
    return {
        "seer_inspection": "占い師の確認",
        "werewolf_recognition": "人狼の相互確認",
        "thief_inspection": "怪盗の確認",
        "thief_swap": "怪盗の交換判断",
    }.get(phase, phase)


def _initial_roles(case_log: Dict[str, Any]) -> List[str]:
    lines = ["## 開始時役職割当", "", "| ID | 開始時役職 |", "| --- | --- |"]
    for player in case_log["players"]:
        lines.append(
            "| {0} | {1} |".format(
                _upper(player["player_id"]), role_label(player["initial_role"])
            )
        )
    lines.append("")
    return lines


def _night(case_log: Dict[str, Any]) -> List[str]:
    """先行実験の結果文書と同じ、番号付きの文章にする。

    怪盗の確認と交換は2つのフェーズだが、1つの番号にまとめる。先行実験が
    「怪盗P2はP1を確認。結果は…。P2は「交換しない」を選択。」と1項目で
    書いているため、形式を揃えている。
    """

    lines = ["## 夜処理", ""]
    step = 0
    seen_wolves = False
    swaps = {
        a["actor"]: a for a in case_log["night_actions"] if a["phase"] == "thief_swap"
    }

    for action in case_log["night_actions"]:
        phase = action["phase"]

        if phase == "seer_inspection":
            step += 1
            lines.append("{0}. {1}".format(step, _seer_text(action)))
        elif phase == "werewolf_recognition":
            if seen_wolves:
                continue
            seen_wolves = True
            step += 1
            lines.append("{0}. {1}".format(step, _wolf_text(case_log)))
        elif phase == "thief_inspection":
            step += 1
            parts = [_thief_inspect_text(action)]
            swap = swaps.get(action["actor"])
            if swap is not None:
                parts.append(_thief_swap_text(swap))
            lines.append("{0}. {1}".format(step, "".join(parts)))

    lines.append("")
    return lines


def _seer_text(action: Dict[str, Any]) -> str:
    actor = _upper(action["actor"])
    if not action.get("ability_used"):
        return "占い師{0}は3回とも有効な回答を返さず、その夜の能力を使用しなかった。".format(actor)
    return "占い師{0}は{1}を確認。結果は「{1}の開始時役職は{2}」。".format(
        actor, _upper(action["target"]), role_label(action["revealed_initial_role"])
    )


def _wolf_text(case_log: Dict[str, Any]) -> str:
    wolves = [
        _upper(a["actor"])
        for a in case_log["night_actions"]
        if a["phase"] == "werewolf_recognition"
    ]
    return "人狼{0}は互いを人狼仲間として確認。".format("と".join(wolves))


def _thief_inspect_text(action: Dict[str, Any]) -> str:
    actor = _upper(action["actor"])
    if not action.get("ability_used"):
        return "怪盗{0}は3回とも有効な回答を返さず、確認も交換も行わなかった。".format(actor)
    return "怪盗{0}は{1}を確認。結果は「{1}の開始時役職は{2}」。".format(
        actor, _upper(action["target"]), role_label(action["revealed_initial_role"])
    )


def _thief_swap_text(action: Dict[str, Any]) -> str:
    actor = _upper(action["actor"])
    if not action.get("ability_used"):
        return "{0}は交換を行わなかった。最終役職は怪盗。".format(actor)
    if not action["swapped"]:
        return "{0}は「交換しない」を選択。".format(actor)
    target = _upper(action["target"])
    return "{0}は「交換する」を選択。最終役職は{0}が{1}、{2}が{3}（{2}には非通知）。".format(
        actor,
        role_label(action["actor_final_role"]),
        target,
        role_label(action["target_final_role"]),
    )


def _discussion(case_log: Dict[str, Any]) -> List[str]:
    discussion = case_log["discussion"]
    lines = ["## 公開議論", ""]

    events = discussion["events"]
    if not events:
        lines.extend(["発言はありませんでした。", ""])
        return lines

    rounds: Dict[int, List[Dict[str, Any]]] = {}
    for event in events:
        rounds.setdefault(event["round"], []).append(event)

    for round_no in sorted(rounds):
        lines.append("### 第{0}ラウンド".format(round_no))
        lines.append("")
        lines.append("| ID | 公開発言 | private memo |")
        lines.append("| --- | --- | --- |")
        for event in rounds[round_no]:
            lines.append(
                "| {0} | {1} | {2} |".format(
                    _upper(event["player_id"]),
                    _speech_cell(event),
                    _memo_cell(event),
                )
            )
        lines.append("")

    lines.append(
        "終了理由: {0}（{1}ラウンド、発言{2}件、見送り{3}件、スキップ{4}件）".format(
            _stop_reason_label(discussion["stop_reason"]),
            discussion["rounds"],
            sum(1 for e in events if e["spoke"]),
            sum(1 for e in events if not e["spoke"] and not e["skipped"]),
            sum(1 for e in events if e["skipped"]),
        )
    )
    lines.append("")
    return lines


def _speech_cell(event: Dict[str, Any]) -> str:
    if event["spoke"]:
        return _cell(event.get("speech_text", ""))
    # 本人が選んだ見送りと、応答が得られなかったスキップを別の文言にする（設計書6.10）。
    return SKIP_TEXT if event["skipped"] else PASS_TEXT


def _memo_cell(entry: Dict[str, Any]) -> str:
    memo = _cell(entry.get("memo", ""))
    return memo if memo else EMPTY_MEMO


def _stop_reason_label(stop_reason: Optional[str]) -> str:
    return {
        "all_pass": "そのラウンドの対象者全員が見送った",
        "max_rounds": "ラウンド数が上限に達した",
        "max_speeches": "発言数が上限に達した",
        "max_total_chars": "発言量が上限に達した",
    }.get(stop_reason or "", stop_reason or "不明")


def _votes(case_log: Dict[str, Any]) -> List[str]:
    lines = ["## 投票", "", "| ID | 投票先 | private memo |", "| --- | --- | --- |"]
    for vote in case_log["votes"]:
        target = "（棄権）" if vote["abstained"] else _upper(vote["target"])
        lines.append(
            "| {0} | {1} | {2} |".format(
                _upper(vote["voter"]), target, _memo_cell(vote)
            )
        )
    lines.append("")
    return lines


def _result(case_log: Dict[str, Any]) -> List[str]:
    result = case_log["result"]
    lines = ["## 結果", ""]

    if not result["valid"]:
        lines.extend(
            [
                "- 有効票数: 0",
                "- 結果: 無効試合",
                "- 理由: 有効投票なし",
                "- 異常処理: {0}".format(_anomaly_text(case_log)),
                "",
            ]
        )
        return lines

    tally = result["vote_tally"]
    tally_text = "、".join(
        "{0} {1}票".format(_upper(pid), count)
        for pid, count in sorted(tally.items(), key=lambda kv: (-kv[1], kv[0]))
    )
    lines.append("- 得票: {0}".format(tally_text or "なし"))

    if result["abstain_count"]:
        lines.append(
            "- 有効票数: {0}（棄権{1}件）".format(
                result["valid_vote_count"], result["abstain_count"]
            )
        )

    if result["executed"]:
        lines.append(
            "- 追放者: {0}".format("、".join(_upper(pid) for pid in result["executed"]))
        )
    else:
        lines.append("- 追放者: なし（最多得票が1票のため）")

    final_roles = "、".join(
        "{0} {1}".format(_upper(p["player_id"]), role_label(p["final_role"]))
        for p in case_log["players"]
    )
    lines.append("- 最終役職: {0}".format(final_roles))
    lines.append(
        "- 勝敗: {0}の勝利".format(
            "村人陣営" if result["winner"] == "village" else "人狼陣営"
        )
    )
    lines.append("- 判定理由: {0}".format(_verdict_reason(result)))
    lines.append("- 異常処理: {0}".format(_anomaly_text(case_log)))
    lines.append("")
    return lines


def _verdict_reason(result: Dict[str, Any]) -> str:
    wolves = [
        _upper(entry["player_id"])
        for entry in result["executed_roles"]
        if entry["final_role"] == "werewolf"
    ]
    if wolves:
        return "最終役職が人狼の{0}が追放されたため。".format("、".join(wolves))
    if not result["executed"]:
        return "最多得票が1票のみで誰も追放されず、人狼が1体も追放されなかったため。"
    return "最終役職が人狼の参加者は追放されなかったため。"


def write_transcript(path: Path, case_log: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_transcript(case_log), encoding="utf-8")
