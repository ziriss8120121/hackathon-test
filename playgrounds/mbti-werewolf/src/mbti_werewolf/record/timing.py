"""実行時間の実測記録（設計書1.3、NF-07）。

1ケースの所要時間はAI応答待ちで決まる。設計書1.3の試算（1呼び出しあたり約10.6秒）
と並べて残し、段階2で `max_rounds` を見直す材料にする。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

#: v1.1の実測（4人3ターン、16回で約170秒）から置いた試算。段階1の実測で更新する。
ESTIMATED_SECONDS_PER_CALL = 10.6
ESTIMATED_CALLS_PER_CASE = 81


def seconds_per_call(wait_seconds: float, calls: int) -> Optional[float]:
    if calls <= 0:
        return None
    return round(float(wait_seconds) / calls, 3)


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
    brain = brain or {}
    provider = brain.get("provider") or "stub"
    model = brain.get("model") or "（なし）"

    lines = [
        "# 実行時間の実測",
        "",
        "実験 `{0}` の、今回実行したケースの所要時間です。".format(
            summary.get("experiment_id", "")
        ),
        "設計書1.3の試算（1呼び出しあたり約{0}秒、1ケース約{1}回・約14分）と見比べるための記録です。".format(
            ESTIMATED_SECONDS_PER_CALL, ESTIMATED_CALLS_PER_CASE
        ),
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
        "| 設計書1.3の試算 | 1回あたり約{0}秒 |".format(ESTIMATED_SECONDS_PER_CALL),
        "",
    ]
    if provider == "stub":
        lines.append(
            "Stubでは待機がほぼ0になります。実モデルの実測は `--brain ollama` で取ります。"
        )
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
