"""ケース単位の指標算出（設計書9.1〜9.3）。

`case_log.json` だけを入力にする。`case_log.json` が出力の正本であり、指標は
そこから導出できる形にしておくと、指標の定義を変えたときにゲームを再実行せず
`analyze` を回すだけで作り直せる（設計書0.2の4番目の方針）。

「判断していない」と「誤って判断した」を区別するため、算出できない値は0ではなく
`None` にする。0にすると、棄権や `"unknown"` が正確性の低さとして集計され、指標が
実行品質に汚染される（9.1）。

疑念分布を使う `final_entropy` と `convergence_round` はここで算出しない。公開
スタンス系列（5.5）が必要であり、それはJudge（M4）の出力である。M3では
`None` を返し、CSVでは空欄になる（6.9）。
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence

from ..engine.roles import TEAM_WEREWOLF, team_of

SUSPECT_UNKNOWN = "unknown"

#: Judgeが揃うまで算出できない指標（設計書6.9）。空欄と0を区別する。
JUDGE_DEPENDENT = ("final_entropy", "convergence_round")


def _final_roles(case_log: Dict[str, Any]) -> Dict[str, str]:
    return {p["player_id"]: p["final_role"] for p in case_log["players"]}


def _is_werewolf(final_roles: Dict[str, str], player_id: Optional[str]) -> Optional[int]:
    """`player_id` の最終役職が人狼なら1、村人側なら0、判断がなければ None。"""

    if not player_id or player_id == SUSPECT_UNKNOWN:
        return None
    role = final_roles.get(player_id)
    if role is None:
        return None
    return 1 if team_of(role) == TEAM_WEREWOLF else 0


def _by_player(entries: Sequence[Dict[str, Any]], key: str) -> Dict[str, Dict[str, Any]]:
    return {entry[key]: entry for entry in entries}


def _mean(values: Sequence[float]) -> Optional[float]:
    usable = [v for v in values if v is not None]
    if not usable:
        return None
    return round(sum(usable) / len(usable), 4)


def _rate(numerator: int, denominator: int) -> Optional[float]:
    """分母が0なら None。0件中0件を「0割」として集計しないため。"""

    if denominator == 0:
        return None
    return round(numerator / denominator, 4)


def player_metrics(case_log: Dict[str, Any]) -> List[Dict[str, Any]]:
    """1行 = 1プレイヤー（設計書9.1〜9.3、6.9の `trial_metrics.csv`）。"""

    final_roles = _final_roles(case_log)
    pre = _by_player(case_log["pre_discussion_answers"], "player_id")
    post = _by_player(case_log["pre_vote_answers"], "player_id")
    votes = _by_player(case_log["votes"], "voter")
    result = case_log["result"]
    executed = set(result["executed"])
    events = case_log["discussion"]["events"]

    rows: List[Dict[str, Any]] = []
    for player in case_log["players"]:
        pid = player["player_id"]
        own = [e for e in events if e["player_id"] == pid]
        spoke = [e for e in own if e["spoke"]]

        pre_answer = pre.get(pid, {})
        post_answer = post.get(pid, {})
        vote = votes.get(pid, {})

        pre_suspect = pre_answer.get("suspect")
        final_suspect = post_answer.get("suspect")
        actual_vote = None if vote.get("abstained") else vote.get("target")

        pre_correct = _is_werewolf(final_roles, pre_suspect)
        final_correct = _is_werewolf(final_roles, final_suspect)

        pre_confidence = pre_answer.get("confidence")
        final_confidence = post_answer.get("confidence")
        confidence_delta = (
            final_confidence - pre_confidence
            if pre_confidence is not None and final_confidence is not None
            else None
        )

        rows.append(
            {
                "player_id": pid,
                "person_id": player["person_id"],
                "age": player["age"],
                "gender": player["gender"],
                "mbti": player["mbti"],
                "initial_role": player["initial_role"],
                "final_role": player["final_role"],
                "speech_count": len(spoke),
                "pass_count": sum(1 for e in own if not e["spoke"] and not e["skipped"]),
                "skip_count": sum(1 for e in own if e["skipped"]),
                "total_chars": sum(len(e.get("speech_text") or "") for e in spoke),
                "avg_chars": _mean([len(e.get("speech_text") or "") for e in spoke]),
                "pre_suspect": pre_suspect,
                "pre_confidence": pre_confidence,
                "final_suspect": final_suspect,
                "final_confidence": final_confidence,
                "planned_vote": post_answer.get("planned_vote"),
                "actual_vote": actual_vote,
                "abstained": bool(vote.get("abstained")),
                "suspect_changed": _suspect_changed(pre_suspect, final_suspect),
                "decided_from_unknown": _decided_from_unknown(pre_suspect, final_suspect),
                "confidence_delta": confidence_delta,
                "pre_correct": pre_correct,
                "final_correct": final_correct,
                "vote_correct": _is_werewolf(final_roles, actual_vote),
                "corrected": _flag(pre_correct == 0 and final_correct == 1, pre_correct, final_correct),
                "deteriorated": _flag(pre_correct == 1 and final_correct == 0, pre_correct, final_correct),
                "plan_vote_match": _match(post_answer.get("planned_vote"), actual_vote),
                "suspect_vote_match": _match(final_suspect, actual_vote),
                "executed": 1 if pid in executed else 0,
                "win": _win(player["final_role"], result["winner"]),
            }
        )
    return rows


def _suspect_changed(pre: Optional[str], final: Optional[str]) -> Optional[int]:
    """議論前が `"unknown"` の場合は判断の変化として数えない（設計書9.3）。

    判断していない状態から判断へ至ることは `decided_from_unknown` で別に数える。
    """

    if pre is None or final is None:
        return None
    if pre == SUSPECT_UNKNOWN:
        return None
    return 1 if pre != final else 0


def _decided_from_unknown(pre: Optional[str], final: Optional[str]) -> Optional[int]:
    if pre is None:
        return None
    if pre != SUSPECT_UNKNOWN:
        return 0
    return 1 if final and final != SUSPECT_UNKNOWN else 0


def _flag(condition: bool, *inputs: Optional[int]) -> Optional[int]:
    """入力のどれかが欠損なら None。欠損を0として数えないため。"""

    if any(value is None for value in inputs):
        return None
    return 1 if condition else 0


def _match(left: Optional[str], right: Optional[str]) -> Optional[int]:
    if left is None or right is None:
        return None
    return 1 if left == right else 0


def _win(final_role: str, winner: Optional[str]) -> Optional[int]:
    """陣営は最終役職で決まる。怪盗が人狼と交換すれば人狼陣営になる（4.2）。"""

    if winner is None:
        return None
    return 1 if team_of(final_role) == winner else 0


def case_metrics(case_log: Dict[str, Any]) -> Dict[str, Any]:
    """1行 = 1ケース（設計書9.1〜9.3、6.9の `experiment_metrics.csv`）。"""

    rows = player_metrics(case_log)
    result = case_log["result"]
    discussion = case_log["discussion"]
    events = discussion["events"]
    timing = case_log["timing"]
    versions = case_log["versions"]
    config = case_log["config"]
    brain = case_log["brain"]

    speeches = [e for e in events if e["spoke"]]
    passes = [e for e in events if not e["spoke"] and not e["skipped"]]
    skips = [e for e in events if e["skipped"]]

    # 人狼本人の投票は正解を知った上での行動なので、正確性の集計から外す（9.1）。
    non_wolf = [r for r in rows if team_of(r["final_role"]) != TEAM_WEREWOLF]

    return {
        "experiment_id": case_log["experiment_id"],
        "trial_id": case_log["trial_id"],
        "case_id": case_log["case_id"],
        "case_index": case_log["case_index"],
        "composition": case_log["composition"],
        "homogeneous_type": case_log["homogeneous_type"],
        "status": case_log["status"],
        "valid": result["valid"],
        "invalid_reason": result["invalid_reason"],
        "rule_set_version": versions["rule_set_version"],
        "persona_prompt_version": versions["persona_prompt_version"],
        "judge_criteria_version": versions["judge_criteria_version"],
        "indicator_version": config["indicator_version"],
        "brain_provider": brain.get("provider"),
        "brain_model": brain.get("model"),
        "rounds": discussion["rounds"],
        "stop_reason": discussion["stop_reason"],
        "total_speeches": len(speeches),
        "total_passes": len(passes),
        "total_skips": len(skips),
        "total_chars": sum(len(e.get("speech_text") or "") for e in speeches),
        "valid_vote_count": result["valid_vote_count"],
        "abstain_count": result["abstain_count"],
        "top_vote_count": result["top_vote_count"],
        "executed": list(result["executed"]),
        # 一覧から数え直す。記録された件数をそのまま出すと、CSVの中で一覧と件数が
        # 食い違う行を作れてしまう。
        "executed_count": len(result["executed"]),
        "executed_final_roles": [e["final_role"] for e in result["executed_roles"]],
        "no_execution_reason": result["no_execution_reason"],
        "winner": result["winner"],
        "village_correct": _village_correct(result),
        "village_vote_accuracy": _mean([r["vote_correct"] for r in non_wolf]),
        "vote_concentration": _rate(result["top_vote_count"], result["valid_vote_count"]),
        # Judgeの公開スタンス系列が必要なため、M3では算出しない（設計書6.9）。
        "final_entropy": None,
        "convergence_round": None,
        "pass_rate": _rate(len(passes), len(passes) + len(speeches)),
        "speech_count_gini": gini([r["speech_count"] for r in rows]),
        "correction_rate": _rate(
            sum(1 for r in rows if r["corrected"] == 1),
            sum(1 for r in rows if r["pre_correct"] == 0),
        ),
        "deterioration_rate": _rate(
            sum(1 for r in rows if r["deteriorated"] == 1),
            sum(1 for r in rows if r["pre_correct"] == 1),
        ),
        "decided_from_unknown_count": sum(
            1 for r in rows if r["decided_from_unknown"] == 1
        ),
        "mean_confidence_delta": _mean([r["confidence_delta"] for r in rows]),
        "plan_vote_mismatch_rate": _mismatch_rate(rows),
        "elapsed_seconds": timing["elapsed_seconds"],
        "ai_wait_seconds": timing["ai_wait_seconds"],
        "inference_calls": timing["inference_calls"],
        "machine_name": timing["machine_name"],
    }


def _village_correct(result: Dict[str, Any]) -> Optional[int]:
    """追放者に人狼が1人でもいれば1（設計書9.1）。

    同率最多の全員追放と追放者0人を認めるルールv0.7に合わせている（4.6）。
    無効試合は勝敗が付かないので None。
    """

    if not result["valid"]:
        return None
    wolves = any(
        team_of(entry["final_role"]) == TEAM_WEREWOLF for entry in result["executed_roles"]
    )
    return 1 if wolves else 0


def _mismatch_rate(rows: Sequence[Dict[str, Any]]) -> Optional[float]:
    matches = [r["plan_vote_match"] for r in rows if r["plan_vote_match"] is not None]
    if not matches:
        return None
    return round(sum(1 for m in matches if m == 0) / len(matches), 4)


def gini(counts: Sequence[int]) -> Optional[float]:
    """発言回数の偏り（設計書9.2）。0が完全に均等、1に近いほど1人へ偏った。

    全員が0回（誰も発言しなかった）の場合は None にする。偏りが0なのではなく、
    偏りを測る対象がない。
    """

    values = sorted(counts)
    total = sum(values)
    if not values or total == 0:
        return None
    n = len(values)
    weighted = sum((index + 1) * value for index, value in enumerate(values))
    return round((2 * weighted) / (n * total) - (n + 1) / n, 4)


def normalized_entropy(distribution: Dict[str, int], player_count: int) -> Optional[float]:
    """疑念分布の正規化エントロピー（設計書9.2）。

    `n` は分布に現れた対象の数ではなく参加人数で固定する。対象の数で正規化すると、
    2人にしか疑いが向いていない分布と8人へ分散した分布が同じ値になりうる。

    M4の公開スタンス系列から呼ぶ。M3ではまだ呼び出し元がない。
    """

    total = sum(distribution.values())
    if total == 0 or player_count < 2:
        return None
    entropy = 0.0
    for count in distribution.values():
        if count <= 0:
            continue
        p = count / total
        entropy -= p * math.log(p)
    return round(entropy / math.log(player_count), 4)
