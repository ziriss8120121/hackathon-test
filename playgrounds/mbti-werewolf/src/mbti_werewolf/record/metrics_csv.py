"""集計CSVの書き出し（設計書6.9）。

列は定数で持ち、追加するときは末尾に足す。既存列の意味と位置を変えない。表計算
ソフトで開いたまま版が変わると、列を差し込んだ時点で参照がずれる。

複数値のセルは `|` 区切りにする。カンマを使うとCSVをそのまま表計算ソフトで開いた
ときに列がずれる。

値が算出できない項目は空欄にする。`0` は「値が0」を意味し、空欄は「まだ算出して
いない」または「算出対象がない」を意味する（6.9）。
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

from .case_metrics import case_metrics, player_metrics

MULTI_VALUE_SEPARATOR = "|"

#: `trial_metrics.csv`（1行 = 1プレイヤー × 1ケース）
TRIAL_COLUMNS: Sequence[str] = (
    "experiment_id",
    "trial_id",
    "case_id",
    "composition",
    "homogeneous_type",
    "player_id",
    "person_id",
    "age",
    "gender",
    "mbti",
    "initial_role",
    "final_role",
    "speech_count",
    "pass_count",
    "skip_count",
    "total_chars",
    "avg_chars",
    "pre_suspect",
    "pre_confidence",
    "final_suspect",
    "final_confidence",
    "planned_vote",
    "actual_vote",
    "abstained",
    "suspect_changed",
    "confidence_delta",
    "pre_correct",
    "final_correct",
    "vote_correct",
    "plan_vote_match",
    "executed",
    "win",
    # ここから下は設計書6.9の一覧より後に足した列。末尾へ足す決まりに従う。
    "decided_from_unknown",
    "suspect_vote_match",
    "corrected",
    "deteriorated",
)

#: `experiment_metrics.csv`（1行 = 1ケース）
EXPERIMENT_COLUMNS: Sequence[str] = (
    "experiment_id",
    "trial_id",
    "case_id",
    "case_index",
    "composition",
    "homogeneous_type",
    "status",
    "valid",
    "invalid_reason",
    "rule_set_version",
    "persona_prompt_version",
    "judge_criteria_version",
    "indicator_version",
    "brain_provider",
    "brain_model",
    "rounds",
    "stop_reason",
    "total_speeches",
    "total_passes",
    "total_skips",
    "total_chars",
    "valid_vote_count",
    "abstain_count",
    "top_vote_count",
    "executed",
    "executed_count",
    "executed_final_roles",
    "no_execution_reason",
    "winner",
    "village_correct",
    "vote_concentration",
    "final_entropy",
    "convergence_round",
    "correction_rate",
    "deterioration_rate",
    "mean_confidence_delta",
    "plan_vote_mismatch_rate",
    "elapsed_seconds",
    "ai_wait_seconds",
    "inference_calls",
    "machine_name",
    # ここから下は設計書6.9の一覧より後に足した列。末尾へ足す決まりに従う。
    "village_vote_accuracy",
    "pass_rate",
    "speech_count_gini",
    "decided_from_unknown_count",
)


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple)):
        return MULTI_VALUE_SEPARATOR.join(str(v) for v in value)
    return str(value)


def trial_rows(case_logs: Iterable[Dict[str, Any]]) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for case_log in case_logs:
        head = {
            "experiment_id": case_log["experiment_id"],
            "trial_id": case_log["trial_id"],
            "case_id": case_log["case_id"],
            "composition": case_log["composition"],
            "homogeneous_type": case_log["homogeneous_type"],
        }
        for player in player_metrics(case_log):
            merged = dict(head)
            merged.update(player)
            rows.append({key: _cell(merged.get(key)) for key in TRIAL_COLUMNS})
    return rows


def experiment_rows(case_logs: Iterable[Dict[str, Any]]) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for case_log in case_logs:
        metrics = case_metrics(case_log)
        rows.append({key: _cell(metrics.get(key)) for key in EXPERIMENT_COLUMNS})
    return rows


def write_csv(path: Path, columns: Sequence[str], rows: Sequence[Dict[str, str]]) -> None:
    """ヘッダだけの行数0のファイルも書く。列の形を確認できるようにするため。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    # newline="" はcsvモジュールの要求。指定しないとWindowsで空行が挟まる。
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(columns))
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_trial_metrics(path: Path, case_logs: Iterable[Dict[str, Any]]) -> None:
    write_csv(path, TRIAL_COLUMNS, trial_rows(case_logs))


def write_experiment_metrics(path: Path, case_logs: Iterable[Dict[str, Any]]) -> None:
    write_csv(path, EXPERIMENT_COLUMNS, experiment_rows(case_logs))
