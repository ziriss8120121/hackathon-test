"""ケース単位の指標と、Judge出力から埋める列（設計書9.1〜9.3、6.9）。

ゲーム実行時点の指標は `record/case_metrics.py` が出し、ここは公開スタンス系列が
必要な2列だけを足す。M3では空欄、M4bの `analyze` で埋める。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..experiment import CASES_PER_TRIAL, COMPOSITION_HOMOGENEOUS, COMPOSITION_MIXED
from ..judge.stance import pick_stance
from ..record.case_metrics import case_metrics

#: RQ1でTrial単位の対応あり比較をする指標。確認的分析の対象（9.4）。
RQ1_METRICS: Tuple[str, ...] = (
    "village_correct",
    "village_vote_accuracy",
    "vote_concentration",
    "final_entropy",
    "convergence_round",
    "correction_rate",
    "deterioration_rate",
    "mean_confidence_delta",
    "pass_rate",
    "speech_count_gini",
)

METRIC_LABELS = {
    "village_correct": "村人側の正答（追放に人狼が含まれる）",
    "village_vote_accuracy": "村人側の投票正答率",
    "vote_concentration": "得票の集中（最多得票 ÷ 有効票）",
    "final_entropy": "最終発言時点の疑念の分散（0が集中、1が分散）",
    "convergence_round": "疑念が最多得票者へ固定された最初のラウンド",
    "correction_rate": "誤った初期判断を修正した割合",
    "deterioration_rate": "正しい初期判断を崩した割合",
    "mean_confidence_delta": "自信度の変化（投票前 − 議論前）",
    "pass_rate": "見送り率",
    "speech_count_gini": "発言回数の偏り（ジニ係数）",
}

VERSION_KEYS = (
    "rule_set_version",
    "persona_prompt_version",
    "judge_criteria_version",
    "indicator_version",
    "brain_provider",
    "brain_model",
)


def enriched_case_metrics(
    case_log: Dict[str, Any], judge: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """M3のケース指標に、Judge由来の2列を足す。"""

    row = case_metrics(case_log)
    row["final_entropy"] = None
    row["convergence_round"] = None
    if not judge:
        return row
    series = judge.get("stance_series") or []
    if series:
        row["final_entropy"] = series[-1].get("entropy")
        row["convergence_round"] = convergence_round(case_log, series)
    return row


def convergence_round(
    case_log: Dict[str, Any], series: Sequence[Dict[str, Any]]
) -> Optional[int]:
    """疑念の最頻対象が最多得票者と一致し、以後変わらなくなった最初のラウンド。

    追放者が0人なら `null`（9.2）。最頻が同率なら、その時点は収束していない。
    """

    executed = list(case_log.get("result", {}).get("executed") or [])
    if not executed or not series:
        return None

    rounds = {}
    for event in case_log.get("discussion", {}).get("events", []):
        speech_id = event.get("speech_id")
        if speech_id:
            rounds[speech_id] = event.get("round")

    modes: List[Optional[str]] = [_unique_mode(entry.get("suspicion_distribution") or {}) for entry in series]
    for index, mode in enumerate(modes):
        if mode is None or mode not in executed:
            continue
        if all(later == mode for later in modes[index:]):
            round_no = rounds.get(series[index]["at_speech_id"])
            return int(round_no) if round_no is not None else None
    return None


def _unique_mode(distribution: Dict[str, int]) -> Optional[str]:
    if not distribution:
        return None
    top = max(distribution.values())
    winners = [key for key, value in distribution.items() if value == top]
    if len(winners) != 1:
        return None
    return winners[0]


def speech_label_rows(
    case_log: Dict[str, Any], judge: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """`speech_labels.csv` の1ケース分。MBTIと役職はここで結合する（6.9）。"""

    players = {p["player_id"]: p for p in case_log["players"]}
    events = {
        e["speech_id"]: e
        for e in case_log.get("discussion", {}).get("events", [])
        if e.get("speech_id")
    }
    rows: List[Dict[str, Any]] = []
    for index, evaluation in enumerate(judge.get("speeches") or [], start=1):
        speech_id = evaluation["speech_id"]
        event = events.get(speech_id, {})
        player = players.get(event.get("player_id"), {})
        stance = pick_stance(evaluation.get("stances") or [])
        rows.append(
            {
                "experiment_id": case_log["experiment_id"],
                "trial_id": case_log["trial_id"],
                "case_id": case_log["case_id"],
                "speech_id": speech_id,
                "order": index,
                "round": event.get("round"),
                "player_id": event.get("player_id"),
                "mbti": player.get("mbti"),
                "initial_role": player.get("initial_role"),
                "final_role": player.get("final_role"),
                "chars": len(event.get("speech_text") or ""),
                "labels": evaluation.get("labels") or [],
                "mentions": evaluation.get("mentions") or [],
                "stance_target": None if stance is None else stance.get("target"),
                "stance_direction": None if stance is None else stance.get("direction"),
                "stance_strength": None if stance is None else stance.get("strength"),
                "judge_criteria_version": judge.get("judge_criteria_version"),
            }
        )
    return rows


def exclusion_reason(cases: Sequence[Dict[str, Any]]) -> Optional[str]:
    """RQ1・RQ2から外す理由。対象なら None（9.4）。"""

    if len(cases) != CASES_PER_TRIAL:
        return "17ケース揃っていない（{0}件）".format(len(cases))
    if any(row.get("status") != "done" for row in cases):
        return "未完了のケースがある"
    if any(not row.get("valid") for row in cases):
        return "無効試合または実行失敗のケースがある"
    mixed = [row for row in cases if row.get("composition") == COMPOSITION_MIXED]
    homo = [row for row in cases if row.get("composition") == COMPOSITION_HOMOGENEOUS]
    if len(mixed) != 1 or len(homo) != CASES_PER_TRIAL - 1:
        return "混合1ケースと同質16ケースの内訳になっていない"

    for key in VERSION_KEYS:
        values = {row.get(key) for row in cases}
        if len(values) != 1:
            return "Trial内で {0} が一致しない".format(key)
    return None


def frozen_note(frozen_at: Optional[str], started_at: Optional[str]) -> str:
    """RQ1の冒頭に出す注記（9.5）。"""

    if frozen_at and started_at and frozen_at < started_at:
        return "本実行前に確定した指標による確認的分析である"
    return "実行後に定義された指標を含むため、探索的分析として読む必要がある"
