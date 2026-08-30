"""ケースログ（設計書6.7）。

出力の正本である。Judgeと分析以外の出力はすべてこのファイルから導出する。
`schema_version: "2"` を持ち、v1の `run_log.json` とはファイル名でも区別できる。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

SCHEMA_VERSION = "2"

STATUS_DONE = "done"
STATUS_FAILED = "failed"


def build_case_log(
    case_plan,
    outcome,
    config,
    rule_set,
    brain_describe: Dict[str, str],
    trial,
    status: str = STATUS_DONE,
    attempt: int = 1,
    failure: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    discussion = outcome.discussion
    return {
        "schema_version": SCHEMA_VERSION,
        "case_id": case_plan.case_id,
        "trial_id": case_plan.trial_id,
        "experiment_id": case_plan.experiment_id,
        "case_index": case_plan.case_index,
        "composition": case_plan.composition,
        "homogeneous_type": case_plan.homogeneous_type,
        "status": status,
        "attempt": attempt,
        "versions": {
            "rule_set_id": rule_set.rule_set_id,
            "rule_set_version": rule_set.rule_set_version,
            "persona_prompt_version": config.persona_prompt_version,
            "judge_criteria_version": config.judge_criteria_version,
            "pool_id": config.pool_id,
            "pattern_id": trial.pattern_id,
        },
        "brain": dict(brain_describe),
        "config": _case_config(config, trial),
        "players": [p.to_dict() for p in outcome.players],
        "night_actions": outcome.night_actions,
        "pre_discussion_answers": outcome.pre_discussion_answers,
        "discussion": {
            "rounds": discussion.rounds if discussion else 0,
            "stop_reason": discussion.stop_reason if discussion else None,
            "limits": config.discussion.to_dict(),
            "events": discussion.events if discussion else [],
        },
        "pre_vote_answers": outcome.pre_vote_answers,
        "votes": outcome.votes,
        "result": outcome.result,
        "timing": {
            "started_at": outcome.started_at,
            "ended_at": outcome.ended_at,
            "elapsed_seconds": outcome.elapsed_seconds,
            "ai_wait_seconds": outcome.ai_wait_seconds,
            "inference_calls": outcome.inference_calls,
            "machine_name": config.machine_name,
        },
        "failure": failure,
    }


def _case_config(config, trial) -> Dict[str, Any]:
    """そのケースに関係する値だけを確定した形で持つ（設計書6.4）。

    どの経路で実行しても同じ形で保存される（F-56、IF-08）。実験全体の
    `trial_count` や `trial_range` はケースの再実行に関係しないので含めない。
    """

    return {
        "pool_id": config.pool_id,
        "pattern_set_id": config.pattern_set_id,
        "pattern_id": trial.pattern_id,
        "rule_set_id": config.rule_set_id,
        "trial_index": trial.trial_index,
        "trial_seed": trial.trial_seed,
        "discussion": config.discussion.to_dict(),
        "persona_prompt_version": config.persona_prompt_version,
        "judge_criteria_version": config.judge_criteria_version,
        "indicator_version": config.indicator_version,
        "indicator_frozen_at": config.indicator_frozen_at,
        "brain": config.brain.to_dict(),
        "judge_brain": config.judge_brain.to_dict(),
        "machine_name": config.machine_name,
    }


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
