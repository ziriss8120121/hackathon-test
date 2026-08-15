"""run_log.json の組み立て（設計書6.5）。

出力の正本である。summary.md、timeline.md、metrics.csv、result.html はすべて
このファイルから導出する。導出元を1つに絞ることで、画面とファイルで内容が
食い違う事態が起きない。

schema_version を持たせるのは、実装途中でschemaを変えたときに古い実行結果を
読み分けられるようにするためである（要件NF-10）。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ..config import SCHEMA_VERSION
from .metrics import compute_metrics


def build_run_log(
    run_id: str,
    series_id: str,
    run_index: int,
    status: str,
    config,
    brain_info: Dict[str, str],
    record,
    timing: Dict[str, Any],
    failure: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    result = record.result
    metrics = compute_metrics(
        players=record.players,
        turns=record.turns,
        votes=record.votes,
        result=result,
        elapsed_seconds=timing.get("elapsed_seconds", 0.0),
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "series_id": series_id,
        "run_index": run_index,
        "status": status,
        "phase": record.phase,
        "config": config.to_dict(),
        "brain": brain_info,
        "players": [player.to_dict() for player in record.players],
        "speaking_order": list(record.speaking_order),
        "turns": list(record.turns),
        "votes": list(record.votes),
        "result": result,
        "metrics": metrics,
        "timing": timing,
        "failure": failure,
    }
