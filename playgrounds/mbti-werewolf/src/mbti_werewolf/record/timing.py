"""実行時間と出力容量の実測記録（設計書1.3、NF-07、NF-12）。

1ケースの所要時間はAI応答待ちで決まる。設計書1.3の試算（1呼び出しあたり約10.6秒）
と並べて残し、段階2で `max_rounds` と本実行の規模を見直す材料にする。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Sequence

#: v1.1の実測（4人3ターン、16回で約170秒）から置いた試算。段階1の実測で更新する。
ESTIMATED_SECONDS_PER_CALL = 10.6
ESTIMATED_CALLS_PER_CASE = 81
CASES_PER_TRIAL = 17

#: 設計書1.3の規模ごとの試算。実測の見込みと並べる。
ESTIMATED_SCALE = (
    ("1ケース", 1, "約14分"),
    ("1 Trial（17ケース）", 17, "約4時間"),
    ("5 Trial", 85, "約20時間"),
    ("100 Trial（1,700ケース）", 1700, "約400時間（約17日）"),
)


def seconds_per_call(wait_seconds: float, calls: int) -> Optional[float]:
    if calls <= 0:
        return None
    return round(float(wait_seconds) / calls, 3)


def directory_bytes(path: Path) -> int:
    """ディレクトリ以下のファイルサイズ合計。読めないファイルは飛ばす。"""

    total = 0
    if not path.exists():
        return 0
    for child in path.rglob("*"):
        if not child.is_file():
            continue
        try:
            total += child.stat().st_size
        except OSError:
            continue
    return total


def case_output_bytes(exp_dir: Path) -> int:
    """ケースディレクトリだけの合計。規模の換算には実験全体よりこちらを使う。"""

    total = 0
    if not exp_dir.is_dir():
        return 0
    for trial_dir in exp_dir.iterdir():
        if not trial_dir.is_dir() or not trial_dir.name.startswith("t"):
            continue
        for case_dir in trial_dir.iterdir():
            if case_dir.is_dir():
                total += directory_bytes(case_dir)
    return total


def bytes_per_done_case(case_bytes: int, done_count: int) -> Optional[int]:
    if done_count <= 0:
        return None
    return int(case_bytes / done_count)


def count_stop_reasons(logs: Sequence[Dict[str, Any]]) -> Dict[str, int]:
    """完了ケースの議論終了理由。`max_rounds` 見直しの材料（4.5）。"""

    counts: Dict[str, int] = {}
    for log in logs:
        if log.get("status") != "done":
            continue
        reason = (log.get("discussion") or {}).get("stop_reason")
        if not reason:
            continue
        counts[str(reason)] = counts.get(str(reason), 0) + 1
    return dict(sorted(counts.items()))


def format_bytes(n: Optional[int]) -> str:
    if n is None:
        return "—"
    value = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            if unit == "B":
                return "{0} B".format(int(value))
            return "{0:.1f} {1}".format(value, unit)
        value /= 1024
    return "{0} B".format(n)


def format_duration(seconds: Optional[float]) -> str:
    if seconds is None:
        return "—"
    value = float(seconds)
    if value < 90:
        return "{0:.1f}秒".format(value)
    minutes = value / 60.0
    if minutes < 90:
        return "約{0:.0f}分".format(minutes)
    hours = value / 3600.0
    if hours < 48:
        return "約{0:.1f}時間".format(hours)
    return "約{0:.1f}日".format(hours / 24.0)


def format_stop_reasons(reasons: Optional[Dict[str, int]]) -> str:
    if not reasons:
        return "—"
    return " / ".join("{0} {1}".format(name, count) for name, count in reasons.items())


def write_timing_note(
    path: Path,
    summary: Dict[str, Any],
    brain: Optional[Dict[str, Any]] = None,
) -> None:
    """実験ディレクトリへ、人が読む実測メモを書く。"""

    calls = int(summary.get("inference_calls") or 0)
    wait = float(summary.get("ai_wait_seconds") or 0.0)
    elapsed = float(summary.get("elapsed_seconds") or 0.0)
    per_call = seconds_per_call(wait, calls)
    per_case = summary.get("seconds_per_done_case")
    if per_case is None:
        per_case = seconds_per_call(elapsed, int(summary.get("done_count") or 0))
    brain = brain or {}
    provider = brain.get("provider") or "stub"
    model = brain.get("model") or "（なし）"
    output_bytes = summary.get("output_bytes")
    case_bytes = summary.get("case_output_bytes")
    per_case_bytes = summary.get("bytes_per_done_case")
    reasons = summary.get("discussion_stop_reasons") or {}

    lines = [
        "# 実行時間と出力容量の実測",
        "",
        "実験 `{0}` の、今回実行したケースの所要時間と出力容量です。".format(
            summary.get("experiment_id", "")
        ),
        "設計書1.3の試算（1呼び出しあたり約{0}秒、1ケース約{1}回・約14分）と見比べるための記録です。".format(
            ESTIMATED_SECONDS_PER_CALL, ESTIMATED_CALLS_PER_CASE
        ),
        "既定値の見直しは、実モデルの1 Trialが揃ってから行う（14章）。",
        "",
        "| 項目 | 値 |",
        "| --- | --- |",
        "| 脳 | {0} / {1} |".format(provider, model),
        "| 今回完了したケース | {0} |".format(summary.get("done_count", 0)),
        "| 失敗したケース | {0} |".format(summary.get("failed_count", 0)),
        "| 推論呼び出し | {0}回 |".format(calls),
        "| AI待機時間 | {0}秒 |".format(wait),
        "| 経過時間 | {0}秒 |".format(elapsed),
        "| 1呼び出しあたり（待機） | {0} |".format(
            "{0}秒".format(per_call) if per_call is not None else "—"
        ),
        "| 1完了ケースあたり（経過） | {0} |".format(format_duration(per_case)),
        "| 設計書1.3の試算 | 1回あたり約{0}秒 |".format(ESTIMATED_SECONDS_PER_CALL),
        "| 実験ディレクトリの容量 | {0} |".format(format_bytes(output_bytes)),
        "| ケース出力の容量 | {0} |".format(format_bytes(case_bytes)),
        "| 1完了ケースあたりの容量 | {0} |".format(format_bytes(per_case_bytes)),
        "| 議論の終わり方 | {0} |".format(format_stop_reasons(reasons)),
        "",
        "## 規模の見込み",
        "",
        "今回の1完了ケースあたりの経過時間と容量から、1 Trial・5 Trial・100 Trialを機械的に掛けた値です。",
        "失敗や再開、Judge評価の時間は含みません。",
        "",
        "| 規模 | この実測からの見込み（時間） | この実測からの見込み（容量） | 設計書1.3の試算 |",
        "| --- | --- | --- | --- |",
    ]
    for label, cases, estimate in ESTIMATED_SCALE:
        time_cell = (
            format_duration(per_case * cases) if per_case is not None else "—"
        )
        size_cell = (
            format_bytes(int(per_case_bytes) * cases)
            if per_case_bytes is not None
            else "—"
        )
        lines.append(
            "| {0} | {1} | {2} | {3} |".format(label, time_cell, size_cell, estimate)
        )
    lines.append("")
    if provider == "stub":
        lines.append(
            "Stubでは待機がほぼ0になり、出力も短い定型文です。"
            "時間と容量の見込みは `--brain ollama` の実測で置き換えます。"
        )
        lines.append("")
    elif int(summary.get("done_count") or 0) < CASES_PER_TRIAL:
        lines.append(
            "1 Trial（17ケース）未満の実行です。段階2の判断には、同じ条件で1 Trialを完走した記録を使います。"
        )
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
