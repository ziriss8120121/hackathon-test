"""ケース指標の算出（設計書9.1〜9.3）。

「判断していない」を0として数えていないかを重点的に見る。0にすると、棄権や
`"unknown"` が正確性の低さとして集計され、指標が実行品質に汚染される（9.1）。
"""

from __future__ import annotations

from mbti_werewolf.record.case_metrics import (
    case_metrics,
    gini,
    normalized_entropy,
    player_metrics,
)


def _row(rows, player_id):
    return next(row for row in rows if row["player_id"] == player_id)


def _wolf_and_villager(log):
    """最終役職が人狼の1人と、村人側の1人を返す。"""

    wolf = next(p["player_id"] for p in log["players"] if p["final_role"] == "werewolf")
    villager = next(
        p["player_id"] for p in log["players"] if p["final_role"] != "werewolf"
    )
    return wolf, villager


def _set_answers(log, player_id, pre=None, final=None, pre_conf=None, final_conf=None):
    for entry in log["pre_discussion_answers"]:
        if entry["player_id"] == player_id:
            if pre is not None:
                entry["suspect"] = pre
            entry["confidence"] = pre_conf
    for entry in log["pre_vote_answers"]:
        if entry["player_id"] == player_id:
            if final is not None:
                entry["suspect"] = final
            entry["confidence"] = final_conf


# --- 正確性（9.1） -----------------------------------------------------------


def test_vote_correct_is_one_when_the_target_is_a_final_werewolf(case_log):
    log, _outcome, _brain = case_log()
    wolf, _villager = _wolf_and_villager(log)
    for vote in log["votes"]:
        vote["target"] = wolf
        vote["abstained"] = False

    for row in player_metrics(log):
        assert row["vote_correct"] == 1


def test_vote_correct_is_zero_when_the_target_is_a_villager(case_log):
    log, _outcome, _brain = case_log()
    _wolf, villager = _wolf_and_villager(log)
    for vote in log["votes"]:
        vote["target"] = villager
        vote["abstained"] = False

    for row in player_metrics(log):
        assert row["vote_correct"] == 0


def test_abstain_makes_vote_correct_none_not_zero(case_log):
    """棄権は誤った投票ではない。0にすると正確性が実行品質に汚染される（9.1）。"""

    log, _outcome, _brain = case_log()
    log["votes"][0]["abstained"] = True
    log["votes"][0]["target"] = None

    row = _row(player_metrics(log), log["votes"][0]["voter"])
    assert row["vote_correct"] is None
    assert row["abstained"] is True


def test_unknown_makes_pre_correct_none_not_zero(case_log):
    log, _outcome, _brain = case_log()
    target = log["players"][0]["player_id"]
    _set_answers(log, target, pre="unknown")

    assert _row(player_metrics(log), target)["pre_correct"] is None


def test_village_correct_needs_only_one_werewolf_among_the_executed(case_log):
    """同率最多の全員追放を認めるため、1人でも人狼なら1にする（4.6、9.1）。"""

    log, _outcome, _brain = case_log()
    wolf, villager = _wolf_and_villager(log)
    log["result"]["executed"] = [wolf, villager]
    log["result"]["executed_roles"] = [
        {"player_id": wolf, "initial_role": "werewolf", "final_role": "werewolf"},
        {"player_id": villager, "initial_role": "villager", "final_role": "villager"},
    ]

    assert case_metrics(log)["village_correct"] == 1


def test_village_correct_is_zero_when_nobody_is_executed(case_log):
    log, _outcome, _brain = case_log()
    log["result"]["executed"] = []
    log["result"]["executed_roles"] = []

    assert case_metrics(log)["village_correct"] == 0


def test_invalid_game_has_no_village_correct(case_log):
    log, _outcome, _brain = case_log()
    log["result"]["valid"] = False

    assert case_metrics(log)["village_correct"] is None


def test_village_vote_accuracy_excludes_werewolves(case_log):
    """人狼本人の投票は正解を知った上の行動なので、正確性から外す（9.1）。"""

    log, _outcome, _brain = case_log()
    wolf, villager = _wolf_and_villager(log)
    wolves = {p["player_id"] for p in log["players"] if p["final_role"] == "werewolf"}
    for vote in log["votes"]:
        vote["abstained"] = False
        # 村人側は全員正解、人狼側は全員外す。
        vote["target"] = villager if vote["voter"] in wolves else wolf

    assert case_metrics(log)["village_vote_accuracy"] == 1.0


# --- 収束（9.2） -------------------------------------------------------------


def test_vote_concentration_uses_valid_votes_as_the_denominator(case_log):
    log, _outcome, _brain = case_log()
    log["result"]["top_vote_count"] = 3
    log["result"]["valid_vote_count"] = 6

    assert case_metrics(log)["vote_concentration"] == 0.5


def test_judge_dependent_metrics_stay_empty_until_m4(case_log):
    log, _outcome, _brain = case_log()
    metrics = case_metrics(log)

    assert metrics["final_entropy"] is None
    assert metrics["convergence_round"] is None


def test_gini_is_zero_when_everyone_speaks_the_same_amount():
    assert gini([3, 3, 3, 3]) == 0.0


def test_gini_rises_when_one_player_dominates():
    assert gini([0, 0, 0, 12]) > gini([2, 3, 3, 4])


def test_gini_is_none_when_nobody_spoke():
    """偏りが0なのではなく、偏りを測る対象がない。"""

    assert gini([0, 0, 0, 0]) is None


def test_entropy_is_zero_when_all_suspicion_points_at_one_player():
    assert normalized_entropy({"p1": 8}, 8) == 0.0


def test_entropy_is_one_when_suspicion_is_spread_over_every_player():
    spread = {"p{0}".format(i): 1 for i in range(1, 9)}
    assert normalized_entropy(spread, 8) == 1.0


def test_entropy_normalizes_by_player_count_not_by_targets_present():
    """対象の数で正規化すると、2人へ向いた分布と8人へ分散した分布が同じ値になる。"""

    two_targets = normalized_entropy({"p1": 4, "p2": 4}, 8)
    eight_targets = normalized_entropy({"p{0}".format(i): 1 for i in range(1, 9)}, 8)
    assert two_targets < eight_targets


def test_pass_rate_excludes_skips(case_log):
    """スキップは実行上の失敗であり、本人が選んだ沈黙ではない（4.5）。"""

    log, _outcome, _brain = case_log()
    log["discussion"]["events"] = [
        {"player_id": "p1", "round": 1, "spoke": True, "skipped": False, "speech_text": "あ"},
        {"player_id": "p2", "round": 1, "spoke": False, "skipped": False, "memo": "様子見"},
        {"player_id": "p3", "round": 1, "spoke": False, "skipped": True},
    ]

    assert case_metrics(log)["pass_rate"] == 0.5


# --- 判断変化（9.3） ---------------------------------------------------------


def test_confidence_delta_is_the_difference_between_the_two_time_points(case_log):
    log, _outcome, _brain = case_log()
    target = log["players"][0]["player_id"]
    _set_answers(log, target, pre_conf=2, final_conf=5)

    assert _row(player_metrics(log), target)["confidence_delta"] == 3


def test_confidence_delta_is_none_when_a_time_point_is_missing(case_log):
    log, _outcome, _brain = case_log()
    target = log["players"][0]["player_id"]
    _set_answers(log, target, pre_conf=None, final_conf=4)

    assert _row(player_metrics(log), target)["confidence_delta"] is None


def test_corrected_needs_a_wrong_start_and_a_right_end(case_log):
    log, _outcome, _brain = case_log()
    wolf, villager = _wolf_and_villager(log)
    target = log["players"][0]["player_id"]
    _set_answers(log, target, pre=villager, final=wolf)

    row = _row(player_metrics(log), target)
    assert row["pre_correct"] == 0
    assert row["final_correct"] == 1
    assert row["corrected"] == 1
    assert row["deteriorated"] == 0


def test_deteriorated_is_the_opposite_direction(case_log):
    log, _outcome, _brain = case_log()
    wolf, villager = _wolf_and_villager(log)
    target = log["players"][0]["player_id"]
    _set_answers(log, target, pre=wolf, final=villager)

    row = _row(player_metrics(log), target)
    assert row["deteriorated"] == 1
    assert row["corrected"] == 0


def test_unknown_start_counts_as_decided_not_corrected(case_log):
    """判断していない状態から判断へ至ることは、誤りを正すことと別に数える（9.3）。"""

    log, _outcome, _brain = case_log()
    wolf, _villager = _wolf_and_villager(log)
    target = log["players"][0]["player_id"]
    _set_answers(log, target, pre="unknown", final=wolf)

    row = _row(player_metrics(log), target)
    assert row["decided_from_unknown"] == 1
    assert row["corrected"] is None
    assert row["suspect_changed"] is None


def test_correction_rate_denominator_is_those_who_started_wrong(case_log):
    log, _outcome, _brain = case_log()
    wolf, villager = _wolf_and_villager(log)
    ids = [p["player_id"] for p in log["players"]]
    # 4人が誤りから開始し、そのうち1人だけ正す。
    for index, pid in enumerate(ids[:4]):
        _set_answers(log, pid, pre=villager, final=wolf if index == 0 else villager)
    for pid in ids[4:]:
        _set_answers(log, pid, pre="unknown", final=villager)

    assert case_metrics(log)["correction_rate"] == 0.25


def test_correction_rate_is_none_when_nobody_started_wrong(case_log):
    """0件中0件を「0割」として集計しない。"""

    log, _outcome, _brain = case_log()
    for player in log["players"]:
        _set_answers(log, player["player_id"], pre="unknown")

    assert case_metrics(log)["correction_rate"] is None


def test_plan_vote_mismatch_rate_counts_the_gap_between_plan_and_action(case_log):
    log, _outcome, _brain = case_log()
    wolf, villager = _wolf_and_villager(log)
    for entry in log["pre_vote_answers"]:
        entry["planned_vote"] = wolf
    for index, vote in enumerate(log["votes"]):
        vote["abstained"] = False
        vote["target"] = wolf if index < 6 else villager

    assert case_metrics(log)["plan_vote_mismatch_rate"] == 0.25


# --- 素の集計 ---------------------------------------------------------------


def test_speech_counts_split_pass_and_skip(case_log):
    log, _outcome, _brain = case_log()
    log["discussion"]["events"] = [
        {"player_id": "p1", "round": 1, "spoke": True, "skipped": False, "speech_text": "ああ"},
        {"player_id": "p1", "round": 2, "spoke": False, "skipped": False, "memo": "様子見"},
        {"player_id": "p1", "round": 3, "spoke": False, "skipped": True},
    ]

    row = _row(player_metrics(log), "p1")
    assert row["speech_count"] == 1
    assert row["pass_count"] == 1
    assert row["skip_count"] == 1
    assert row["total_chars"] == 2


def test_win_follows_the_final_role_not_the_initial_role(case_log):
    """怪盗が人狼と交換すれば人狼陣営として勝敗が付く（4.2）。"""

    log, _outcome, _brain = case_log()
    log["result"]["winner"] = "werewolf"
    log["players"][0]["initial_role"] = "thief"
    log["players"][0]["final_role"] = "werewolf"

    assert _row(player_metrics(log), log["players"][0]["player_id"])["win"] == 1


def test_every_player_has_one_row(case_log):
    log, _outcome, _brain = case_log()
    rows = player_metrics(log)

    assert len(rows) == 8
    assert len({row["player_id"] for row in rows}) == 8


def test_case_metrics_carry_the_identifiers_and_versions(case_log):
    log, _outcome, _brain = case_log()
    metrics = case_metrics(log)

    assert metrics["case_id"] == log["case_id"]
    assert metrics["trial_id"] == log["trial_id"]
    assert metrics["experiment_id"] == log["experiment_id"]
    assert metrics["rule_set_version"] == log["versions"]["rule_set_version"]
    assert metrics["indicator_version"] == log["config"]["indicator_version"]
    assert metrics["machine_name"] == log["timing"]["machine_name"]
