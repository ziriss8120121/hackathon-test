"""summary.md の生成（設計書6.7、要件F-31）。

実装者以外のメンバーが説明なしで結果を読める粒度にする（要件NF-13）。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..agents.functions import function_label
from ..agents.mbti_types import mbti_candidates_text, player_mbti_text, winning_mbti_text

WINNER_LABELS = {"village": "村人陣営の勝ち", "werewolf": "人狼陣営の勝ち"}
ROLE_LABELS = {"werewolf": "人狼", "villager": "村人"}


def render_summary(run_log: Dict[str, Any]) -> str:
    result = run_log.get("result") or {}
    timing = run_log.get("timing") or {}
    config = run_log.get("config") or {}
    brain = run_log.get("brain") or {}
    players = run_log.get("players") or []
    per_player = (run_log.get("metrics") or {}).get("per_player") or []

    lines: List[str] = ["# 結果カード", ""]

    if run_log.get("status") != "done":
        failure = run_log.get("failure") or {}
        lines += [
            "> この実行は完走していません。状態: **{}**".format(run_log.get("status")),
            ">",
            "> 失敗の種別: `{}`".format(failure.get("kind", "不明")),
            ">",
            "> 内容: {}".format(failure.get("message", "（記録なし）")),
            "",
        ]

    werewolf_mbti = [
        player_mbti_text(p["player_id"], p["function"])
        for p in players
        if p.get("role") == "werewolf"
    ]

    lines += [
        "| 項目 | 内容 |",
        "| --- | --- |",
        "| 実行ID | `{}` |".format(run_log.get("run_id", "")),
        "| 勝敗 | {} |".format(
            WINNER_LABELS.get(result.get("winner"), "（決着していません）")
        ),
        "| 勝ったMBTI | {} |".format(winning_mbti_text(players, result.get("winner"))),
        "| 人狼だったMBTI | {} |".format(
            "、".join(werewolf_mbti) or "（記録なし）"
        ),
        "| 処刑された人 | {} |".format(_executed_text(result, players)),
        "| 最も疑われた人 | {} |".format(_top_text(per_player, "suspected_by_count", "件")),
        "| 最も発言した人 | {} |".format(_top_text(per_player, "speech_count", "回")),
        "| 決着方法 | {} |".format(_tie_break_text(result)),
        "",
        "MBTIは主機能からの候補2タイプ（要求定義書6.5）。1人に心理機能を1つだけ持たせているため、タイプは一意に決まらない。",
        "",
        "## 実行条件",
        "",
        "| 項目 | 値 |",
        "| --- | --- |",
        "| 参加人数 | {}人 |".format(config.get("player_count", "")),
        "| 議論ターン数 | {} |".format(config.get("turn_count", "")),
        "| seed | {} |".format(config.get("seed", "")),
        "| 役職割当方式 | {} |".format(config.get("role_assignment_mode", "")),
        "| 心理機能 | {} |".format("、".join(config.get("functions") or [])),
        "| history_mode | {} |".format(config.get("history_mode", "")),
        "| 使用した脳 | {} |".format(_brain_text(brain)),
        "| 実行環境 | {} |".format(timing.get("machine_name", "")),
        "| 開始 | {} |".format(timing.get("started_at", "")),
        "| 終了 | {} |".format(timing.get("ended_at", "")),
        "| 所要時間 | {}秒 |".format(timing.get("elapsed_seconds", "")),
        "| AI待機時間 | {}秒 |".format(timing.get("ai_wait_seconds", "")),
        "",
        "## 心理機能ごとの集計",
        "",
        "| ID | 心理機能 | MBTI候補 | 役職 | 発言数 | 平均文字数 | 投票先 | 勝敗 | 疑い | 疑われ | 質問 | 反論 | 同調 | 仮説 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]

    for entry in per_player:
        lines.append(
            "| {} | {}（{}） | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
                entry["player_id"],
                entry["function"],
                function_label(entry["function"]),
                mbti_candidates_text(entry["function"]),
                ROLE_LABELS.get(entry["role"], entry["role"]),
                entry["speech_count"],
                entry["avg_chars"],
                entry["final_vote"] or "—",
                _win_text(entry.get("win")),
                entry["suspicion_count"],
                entry["suspected_by_count"],
                entry["question_count"],
                entry["rebuttal_count"],
                entry["agreement_count"],
                entry["hypothesis_count"],
            )
        )

    parse_failed = sum(1 for turn in run_log.get("turns") or [] if turn.get("parse_failed"))
    fallback_votes = sum(1 for vote in run_log.get("votes") or [] if vote.get("fallback"))
    lines += [
        "",
        "## 記録の品質",
        "",
        "| 項目 | 件数 |",
        "| --- | --- |",
        "| 形式が崩れた発言（parse_failed） | {} |".format(parse_failed),
        "| 乱数で決めた投票（fallback） | {} |".format(fallback_votes),
        "",
        "## 観察メモ",
        "",
        "（結果を見た人が追記する欄）",
        "",
        "---",
        "",
        "MBTIおよび心理機能は、実在人物の診断や評価ではない。"
        "エージェントの振る舞いを分けるためのフィクション設定として扱っている。",
        "",
    ]
    return "\n".join(lines)


def _brain_text(brain: Dict[str, Any]) -> str:
    """要件F-16の推論手段。同じ語の繰り返しは1つにまとめて読みやすくする。"""
    parts: List[str] = []
    for key in ("provider", "model", "endpoint_kind"):
        value = brain.get(key)
        if value and value not in parts:
            parts.append(value)
    return " / ".join(parts) or "—"


def _executed_text(result: Dict[str, Any], players: List[Dict[str, Any]]) -> str:
    executed = result.get("executed")
    if not executed:
        return "（処刑まで到達していません）"
    role = ROLE_LABELS.get(result.get("executed_role"), result.get("executed_role", ""))
    function = result.get("executed_function") or _function_of(players, executed)
    return "{}（{} / {}）→ {}".format(
        executed, function, role, mbti_candidates_text(function)
    )


def _function_of(players: List[Dict[str, Any]], player_id: str) -> str:
    for player in players:
        if player.get("player_id") == player_id:
            return player.get("function", "")
    return ""


def _top_text(per_player: List[Dict[str, Any]], key: str, unit: str) -> str:
    if not per_player:
        return "（記録なし）"
    top = max(entry.get(key, 0) for entry in per_player)
    if not top:
        return "（該当なし）"
    names = [
        player_mbti_text(entry["player_id"], entry["function"])
        for entry in per_player
        if entry.get(key, 0) == top
    ]
    return "{} — {}{}".format("、".join(names), top, unit)


def _tie_break_text(result: Dict[str, Any]) -> str:
    tie_break: Optional[Dict[str, Any]] = result.get("tie_break")
    if not tie_break:
        return "最多得票が1人だったため、そのまま処刑"
    return "同数得票のため {} で決着（候補: {}、seed: {}）".format(
        tie_break.get("method", ""),
        "、".join(tie_break.get("candidates") or []),
        tie_break.get("seed", ""),
    )


def _win_text(win: Optional[bool]) -> str:
    if win is None:
        return "—"
    return "勝ち" if win else "負け"
