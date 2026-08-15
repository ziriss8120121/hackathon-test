"""series_summary.md の生成（設計書6.7、要件F-38）。

複数試合の傾向を1ファイルで読めるようにする。1試合の実行も1試合のseriesとして
扱うため、単発実行でもこのファイルが出る。
"""

from __future__ import annotations

from typing import Any, Dict, List

from ..agents.functions import function_label

WINNER_LABELS = {"village": "村人陣営", "werewolf": "人狼陣営"}


def render_series_summary(series: Dict[str, Any], run_logs: List[Dict[str, Any]]) -> str:
    config = series.get("config") or {}
    done = [log for log in run_logs if log.get("status") == "done"]
    failed = [log for log in run_logs if log.get("status") != "done"]

    lines: List[str] = [
        "# 連続実行の集計",
        "",
        "| 項目 | 内容 |",
        "| --- | --- |",
        "| series_id | `{}` |".format(series.get("series_id", "")),
        "| 試合数（指定） | {} |".format(config.get("game_count", "")),
        "| 成功 | {} |".format(len(done)),
        "| 失敗 | {} |".format(len(failed)),
        "| base_seed | {} |".format(config.get("base_seed", config.get("seed", ""))),
        "| 参加人数 | {}人 |".format(config.get("player_count", "")),
        "| 議論ターン数 | {} |".format(config.get("turn_count", "")),
        "| 心理機能 | {} |".format("、".join(config.get("functions") or [])),
        "| 使用した脳 | {} |".format(_brain_text(config.get("brain") or {})),
        "| 実行環境 | {} |".format(config.get("machine_name", "")),
        "| 開始 | {} |".format(series.get("started_at", "")),
        "| 終了 | {} |".format(series.get("ended_at", "")),
        "| 合計所要時間 | {}秒 |".format(series.get("elapsed_seconds", "")),
        "| 合計AI待機時間 | {}秒 |".format(series.get("ai_wait_seconds", "")),
        "",
    ]

    if done:
        lines += ["## 陣営別の勝率", "", "| 陣営 | 勝ち数 | 勝率 |", "| --- | --- | --- |"]
        for team in ("village", "werewolf"):
            wins = sum(1 for log in done if (log.get("result") or {}).get("winner") == team)
            lines.append(
                "| {} | {} | {} |".format(
                    WINNER_LABELS[team], wins, _rate(wins, len(done))
                )
            )
        lines += ["", "## 心理機能別の集計", ""]
        lines += _function_table(done)

    lines += ["", "## 試合ごとの結果", "", "| # | run_id | 状態 | 勝敗 | 処刑 | 所要秒 |", "| --- | --- | --- | --- | --- | --- |"]
    for log in run_logs:
        result = log.get("result") or {}
        lines.append(
            "| {} | `{}` | {} | {} | {} | {} |".format(
                log.get("run_index", ""),
                log.get("run_id", ""),
                log.get("status", ""),
                WINNER_LABELS.get(result.get("winner"), "—"),
                result.get("executed", "—") or "—",
                (log.get("timing") or {}).get("elapsed_seconds", ""),
            )
        )

    if failed:
        lines += ["", "## 失敗した試合", "", "| run_id | 種別 | 内容 |", "| --- | --- | --- |"]
        for log in failed:
            failure = log.get("failure") or {}
            lines.append(
                "| `{}` | {} | {} |".format(
                    log.get("run_id", ""),
                    failure.get("kind", "不明"),
                    (failure.get("message", "") or "").replace("|", "/"),
                )
            )

    lines.append("")
    return "\n".join(lines)


def _brain_text(brain: Dict[str, Any]) -> str:
    parts = [brain.get("provider"), brain.get("model")]
    return " / ".join(part for part in parts if part) or "—"


def _function_table(logs: List[Dict[str, Any]]) -> List[str]:
    stats: Dict[str, Dict[str, float]] = {}
    for log in logs:
        for entry in (log.get("metrics") or {}).get("per_player") or []:
            bucket = stats.setdefault(
                entry["function"],
                {
                    "games": 0,
                    "wins": 0,
                    "werewolf_games": 0,
                    "speeches": 0,
                    "chars": 0.0,
                    "suspected": 0,
                },
            )
            bucket["games"] += 1
            bucket["wins"] += 1 if entry.get("win") else 0
            bucket["werewolf_games"] += 1 if entry.get("role") == "werewolf" else 0
            bucket["speeches"] += entry.get("speech_count", 0)
            bucket["chars"] += entry.get("avg_chars", 0.0)
            bucket["suspected"] += entry.get("suspected_by_count", 0)

    rows = [
        "| 心理機能 | 登場 | 勝ち | 勝率 | 人狼だった回数 | 平均発言数 | 平均文字数 | 平均疑われ数 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for code in sorted(stats):
        bucket = stats[code]
        games = int(bucket["games"]) or 1
        rows.append(
            "| {}（{}） | {} | {} | {} | {} | {} | {} | {} |".format(
                code,
                function_label(code),
                int(bucket["games"]),
                int(bucket["wins"]),
                _rate(int(bucket["wins"]), int(bucket["games"])),
                int(bucket["werewolf_games"]),
                round(bucket["speeches"] / games, 1),
                round(bucket["chars"] / games, 1),
                round(bucket["suspected"] / games, 1),
            )
        )
    return rows


def _rate(part: int, whole: int) -> str:
    if not whole:
        return "—"
    return "{}%".format(round(part * 100 / whole, 1))
