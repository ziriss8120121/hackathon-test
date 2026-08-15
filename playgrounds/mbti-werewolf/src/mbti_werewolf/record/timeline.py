"""timeline.md の生成（設計書6.7、要件F-32）。

このファイルには役職を書く。エージェントへ渡す公開ビュー（engine/view.py）とは
別物で、人が結果を読むためのファイルなので役職が見えている方が読みやすい。
混同を避けるため、エージェント入力を組み立てるのは engine/view.py だけに限定している。
"""

from __future__ import annotations

from typing import Any, Dict, List

from ..agents.functions import function_label

ROLE_LABELS = {"werewolf": "人狼", "villager": "村人"}
WINNER_LABELS = {"village": "村人陣営の勝ち", "werewolf": "人狼陣営の勝ち"}


def render_timeline(run_log: Dict[str, Any]) -> str:
    players = {p["player_id"]: p for p in run_log.get("players") or []}
    turns = run_log.get("turns") or []
    votes = run_log.get("votes") or []
    result = run_log.get("result") or {}

    lines: List[str] = [
        "# 会話タイムライン",
        "",
        "実行ID: `{}`".format(run_log.get("run_id", "")),
        "",
        "## 参加者",
        "",
        "| ID | 心理機能 | 役職 |",
        "| --- | --- | --- |",
    ]
    for player in run_log.get("players") or []:
        lines.append(
            "| {} | {}（{}） | {} |".format(
                player["player_id"],
                player["function"],
                function_label(player["function"]),
                ROLE_LABELS.get(player["role"], player["role"]),
            )
        )

    lines += ["", "発言順: {}".format(" → ".join(run_log.get("speaking_order") or [])), ""]

    current_turn = None
    for turn in turns:
        if turn["turn"] != current_turn:
            current_turn = turn["turn"]
            lines += ["", "## ターン{}".format(current_turn), ""]
        lines.append("- {}: {}{}".format(
            _who(players, turn["player_id"]),
            turn.get("speech_text", ""),
            "  ※形式が崩れた応答" if turn.get("parse_failed") else "",
        ))

    if votes:
        lines += ["", "## 投票", ""]
        for vote in votes:
            note = []
            if vote.get("fallback"):
                note.append("乱数で決定")
            if vote.get("invalid_retry_count"):
                note.append("再要求{}回".format(vote["invalid_retry_count"]))
            suffix = "  ※{}".format("、".join(note)) if note else ""
            lines.append(
                "- {} → {}: {}{}".format(
                    _who(players, vote["voter"]),
                    vote["target"],
                    vote.get("reason", ""),
                    suffix,
                )
            )

    if result:
        counts = result.get("vote_counts") or {}
        lines += [
            "",
            "## 結果",
            "",
            "- 得票: {}".format(
                "、".join("{} {}票".format(pid, count) for pid, count in counts.items())
                or "（記録なし）"
            ),
            "- 処刑: {}".format(_who(players, result.get("executed", ""))),
            "- 勝敗: {}".format(WINNER_LABELS.get(result.get("winner"), "（決着なし）")),
        ]
        if result.get("tie_break"):
            lines.append(
                "- 同数得票のため {} で決着（候補: {}）".format(
                    result["tie_break"].get("method"),
                    "、".join(result["tie_break"].get("candidates") or []),
                )
            )

    lines.append("")
    return "\n".join(lines)


def _who(players: Dict[str, Dict[str, Any]], player_id: str) -> str:
    player = players.get(player_id)
    if not player:
        return player_id or "（不明）"
    return "{}（{} / {}）".format(
        player_id,
        player["function"],
        ROLE_LABELS.get(player["role"], player["role"]),
    )
