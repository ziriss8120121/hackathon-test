"""公開スタンス系列の導出（設計書5.5、9.2 / 要件F-44）。

疑念分布が発言量に引きずられないことを、この系列の性質として検査する。
"""

from __future__ import annotations

import math

import pytest

from mbti_werewolf.judge import stance as stance_module

PLAYERS = ["p{0}".format(i) for i in range(1, 9)]


def speech(index: int, player_id: str):
    return {"speech_id": "c-s{0:03d}".format(index), "player_id": player_id}


def suspect(target: str, strength: int = 2):
    return {"target": target, "direction": "suspect", "strength": strength}


def defend(target: str, strength: int = 2):
    return {"target": target, "direction": "defend", "strength": strength}


# --- 1発言から1件を選ぶ -------------------------------------------------------


def test_the_strongest_stance_in_one_speech_is_the_one_that_counts():
    chosen = stance_module.pick_stance(
        [suspect("p2", strength=1), suspect("p3", strength=3), defend("p4", strength=2)]
    )
    assert chosen["target"] == "p3"


def test_a_tie_on_strength_is_broken_by_taking_the_last_one():
    chosen = stance_module.pick_stance([suspect("p2", strength=3), defend("p5", strength=3)])
    assert chosen == {"target": "p5", "direction": "defend", "strength": 3}


def test_a_speech_without_a_stance_yields_nothing():
    assert stance_module.pick_stance([]) is None


# --- 正規化エントロピー -------------------------------------------------------


def test_no_suspicion_at_all_gives_zero():
    assert stance_module.normalized_entropy({}, 8) == 0.0


def test_everyone_suspecting_one_person_gives_zero():
    assert stance_module.normalized_entropy({"p4": 7}, 8) == 0.0


def test_suspicion_spread_over_all_eight_gives_one():
    distribution = {pid: 1 for pid in PLAYERS}
    assert stance_module.normalized_entropy(distribution, 8) == pytest.approx(1.0)


def test_the_denominator_is_the_participant_count_not_the_number_of_targets():
    """2人に分かれた分布と8人に分かれた分布が同じ値にならない（設計書9.2）。"""

    two = stance_module.normalized_entropy({"p1": 1, "p2": 1}, 8)
    eight = stance_module.normalized_entropy({pid: 1 for pid in PLAYERS}, 8)
    assert two == pytest.approx(math.log(2) / math.log(8), abs=1e-6)
    assert two < eight


# --- 系列 ---------------------------------------------------------------------


def test_the_series_has_one_entry_per_speech():
    speeches = [speech(1, "p1"), speech(2, "p2"), speech(3, "p1")]
    series = stance_module.derive_stance_series(speeches, {}, PLAYERS)
    assert [e["at_speech_id"] for e in series] == [s["speech_id"] for s in speeches]


def test_every_entry_lists_all_participants_even_without_a_stance():
    series = stance_module.derive_stance_series([speech(1, "p1")], {}, PLAYERS)
    assert sorted(series[0]["current_stances"]) == sorted(PLAYERS)
    assert all(value is None for value in series[0]["current_stances"].values())


def test_repeating_the_same_suspicion_never_pushes_the_total_over_the_player_count():
    """F-44。同じ人が何度疑っても分布へは1件しか入らない。"""

    speeches = [speech(i, "p1") for i in range(1, 11)]
    stances = {s["speech_id"]: [suspect("p4")] for s in speeches}

    series = stance_module.derive_stance_series(speeches, stances, PLAYERS)

    for entry in series:
        assert sum(entry["suspicion_distribution"].values()) <= len(PLAYERS)
    assert series[-1]["suspicion_distribution"] == {"p4": 1}


def test_a_talkative_player_does_not_outweigh_a_quiet_one():
    speeches = [speech(1, "p1"), speech(2, "p1"), speech(3, "p1"), speech(4, "p2")]
    stances = {
        "c-s001": [suspect("p5")],
        "c-s002": [suspect("p5")],
        "c-s003": [suspect("p5")],
        "c-s004": [suspect("p6")],
    }

    series = stance_module.derive_stance_series(speeches, stances, PLAYERS)

    assert series[-1]["suspicion_distribution"] == {"p5": 1, "p6": 1}


def test_changing_target_moves_the_count_instead_of_adding_one():
    speeches = [speech(1, "p1"), speech(2, "p1")]
    stances = {"c-s001": [suspect("p5")], "c-s002": [suspect("p6")]}

    series = stance_module.derive_stance_series(speeches, stances, PLAYERS)

    assert series[0]["suspicion_distribution"] == {"p5": 1}
    assert series[1]["suspicion_distribution"] == {"p6": 1}


def test_a_speech_without_a_stance_keeps_the_previous_one():
    """質問や役職主張は、直前に示した立場の取り下げにはあたらない（設計書5.5）。"""

    speeches = [speech(1, "p1"), speech(2, "p1")]
    stances = {"c-s001": [suspect("p5")]}

    series = stance_module.derive_stance_series(speeches, stances, PLAYERS)

    assert series[1]["current_stances"]["p1"] == suspect("p5")
    assert series[1]["suspicion_distribution"] == {"p5": 1}


def test_defending_someone_is_not_counted_as_suspicion():
    speeches = [speech(1, "p1"), speech(2, "p2")]
    stances = {"c-s001": [defend("p5")], "c-s002": [suspect("p5")]}

    series = stance_module.derive_stance_series(speeches, stances, PLAYERS)

    assert series[0]["suspicion_distribution"] == {}
    assert series[1]["suspicion_distribution"] == {"p5": 1}


def test_switching_from_suspicion_to_defence_removes_the_count():
    speeches = [speech(1, "p1"), speech(2, "p1")]
    stances = {"c-s001": [suspect("p5")], "c-s002": [defend("p5")]}

    series = stance_module.derive_stance_series(speeches, stances, PLAYERS)

    assert series[0]["suspicion_distribution"] == {"p5": 1}
    assert series[1]["suspicion_distribution"] == {}


def test_the_entropy_falls_as_suspicion_gathers_on_one_person():
    speeches = [speech(1, "p1"), speech(2, "p2"), speech(3, "p3"), speech(4, "p2")]
    stances = {
        "c-s001": [suspect("p7")],
        "c-s002": [suspect("p8")],
        "c-s003": [suspect("p6")],
        "c-s004": [suspect("p7")],
    }

    series = stance_module.derive_stance_series(speeches, stances, PLAYERS)

    assert series[2]["entropy"] > series[3]["entropy"]
