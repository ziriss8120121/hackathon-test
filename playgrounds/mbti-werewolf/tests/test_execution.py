"""追放判定と勝敗判定（設計書10章 test_execution／要件F-26、F-27、4.6）。

投票の収集を通さず `VoteResolver.resolve` を直接呼ぶ。得票分布を狙って作る必要が
あり、エージェントの応答経由では同率や1票最多を安定して再現できないためである。
"""

from __future__ import annotations

import pytest

from mbti_werewolf.engine.roles import CasePlayer
from mbti_werewolf.engine.vote import (
    INVALID_NO_VALID_VOTES,
    NO_EXECUTION_TOP_IS_ONE,
    VoteResolver,
)


def _players(final_roles):
    return [
        CasePlayer(
            player_id="p{0}".format(index + 1),
            person_id="pe{0:03d}".format(index + 1),
            mbti="ISTJ",
            age=30,
            gender="male",
            initial_role=role,
            final_role=role,
        )
        for index, role in enumerate(final_roles)
    ]


#: 最終役職の並び。p1とp2が人狼、p3が占い師、p4が怪盗、p5〜p8が村人。
ROLES = ("werewolf", "werewolf", "seer", "thief", "villager", "villager", "villager", "villager")


def _resolver(final_roles=ROLES, min_votes: int = 2):
    return VoteResolver(_players(final_roles), {}, None, min_votes_to_execute=min_votes)


def _votes(targets):
    return [
        {
            "voter": "p{0}".format(index + 1),
            "target": target,
            "memo": "",
            "abstained": target is None,
            "attempts": 1,
            "parse_failed": target is None,
            "wait_seconds": 0.0,
        }
        for index, target in enumerate(targets)
    ]


def test_single_top_voted_player_is_executed():
    result = _resolver().resolve(
        _votes(["p1", "p1", "p1", "p1", "p1", "p2", "p3", "p3"])
    )

    assert result["vote_tally"] == {"p1": 5, "p2": 1, "p3": 2}
    assert result["top_vote_count"] == 5
    assert result["executed"] == ["p1"]
    assert result["executed_count"] == 1


def test_all_tied_top_voted_players_are_executed():
    """同率最多は全員追放する（ルール文書v0.7 §1）。"""

    result = _resolver().resolve(
        _votes(["p1", "p1", "p1", "p2", "p2", "p2", "p3", "p4"])
    )

    assert result["top_vote_count"] == 3
    assert result["executed"] == ["p1", "p2"]
    assert result["executed_count"] == 2


def test_no_execution_when_top_vote_count_is_one():
    """最多得票が1票のみなら誰も追放しない（ルール文書v0.7 §1）。"""

    result = _resolver().resolve(
        _votes(["p2", "p3", "p4", "p5", "p6", "p7", "p8", "p1"])
    )

    assert result["top_vote_count"] == 1
    assert result["executed"] == []
    assert result["no_execution_reason"] == NO_EXECUTION_TOP_IS_ONE
    assert result["valid"] is True


def test_no_execution_means_werewolf_side_wins():
    """人狼が1人も追放されていないので人狼陣営の勝ちになる（設計書4.6）。"""

    result = _resolver().resolve(
        _votes(["p2", "p3", "p4", "p5", "p6", "p7", "p8", "p1"])
    )

    assert result["winner"] == "werewolf"


def test_village_wins_when_a_final_werewolf_is_executed():
    result = _resolver().resolve(
        _votes(["p1", "p1", "p1", "p1", "p1", "p2", "p3", "p3"])
    )

    assert result["winner"] == "village"


def test_werewolf_wins_when_only_villagers_are_executed():
    result = _resolver().resolve(
        _votes(["p5", "p5", "p5", "p5", "p5", "p1", "p1", "p2"])
    )

    assert result["executed"] == ["p5"]
    assert result["winner"] == "werewolf"


def test_village_wins_when_a_tie_includes_one_werewolf():
    """同率追放の中に人狼が1人でもいれば村人陣営の勝ち（設計書4.6）。"""

    result = _resolver().resolve(
        _votes(["p1", "p1", "p1", "p5", "p5", "p5", "p2", "p3"])
    )

    assert result["executed"] == ["p1", "p5"]
    assert result["winner"] == "village"


def test_final_role_decides_the_winner_not_initial_role():
    """怪盗が人狼と交換した場合、追放すべき相手は交換後の怪盗である（F-27）。"""

    # p1（開始時人狼）とp4（開始時怪盗）が交換した後の最終役職。
    swapped = ("thief", "werewolf", "seer", "werewolf", "villager", "villager", "villager", "villager")
    resolver = VoteResolver(_players(swapped), {}, None, min_votes_to_execute=2)

    # 開始時に人狼だったp1を追放しても、最終役職は怪盗なので村人陣営は勝てない。
    executed_p1 = resolver.resolve(_votes(["p2", "p1", "p1", "p1", "p1", "p1", "p3", "p3"]))
    assert executed_p1["executed"] == ["p1"]
    assert executed_p1["winner"] == "werewolf"

    # 最終役職が人狼のp4を追放すれば村人陣営の勝ち。
    executed_p4 = resolver.resolve(_votes(["p4", "p4", "p4", "p1", "p1", "p1", "p4", "p3"]))
    assert executed_p4["executed"] == ["p4"]
    assert executed_p4["winner"] == "village"


def test_abstained_votes_are_excluded_from_the_tally():
    result = _resolver().resolve(
        _votes(["p1", "p1", None, None, None, "p2", None, None])
    )

    assert result["vote_tally"] == {"p1": 2, "p2": 1}
    assert result["valid_vote_count"] == 3
    assert result["abstain_count"] == 5
    assert result["executed"] == ["p1"]


def test_no_valid_votes_means_invalid_game():
    """有効票が0票なら勝敗を付けない（ルール文書v0.7 §1）。"""

    result = _resolver().resolve(_votes([None] * 8))

    assert result["valid"] is False
    assert result["invalid_reason"] == INVALID_NO_VALID_VOTES
    assert result["winner"] is None
    assert result["executed"] == []
    assert result["vote_tally"] == {}
    assert result["abstain_count"] == 8


def test_single_valid_vote_results_in_no_execution():
    """1票しか有効票がないなら最多は1票なので誰も追放されない。"""

    result = _resolver().resolve(_votes(["p1"] + [None] * 7))

    assert result["valid"] is True
    assert result["valid_vote_count"] == 1
    assert result["executed"] == []
    assert result["no_execution_reason"] == NO_EXECUTION_TOP_IS_ONE


def test_executed_roles_record_both_initial_and_final():
    swapped = ("thief", "werewolf", "seer", "werewolf", "villager", "villager", "villager", "villager")
    players = _players(swapped)
    players[0].initial_role = "werewolf"
    resolver = VoteResolver(players, {}, None, min_votes_to_execute=2)

    result = resolver.resolve(_votes(["p2", "p1", "p1", "p1", "p1", "p1", "p3", "p3"]))

    assert result["executed_roles"] == [
        {"player_id": "p1", "initial_role": "werewolf", "final_role": "thief"}
    ]


def test_tally_is_sorted_for_stable_output():
    """出力の差分を読めるようにするため並びを固定する（設計書6.7）。"""

    result = _resolver().resolve(
        _votes(["p8", "p8", "p3", "p1", "p1", "p5", "p5", "p5"])
    )

    assert list(result["vote_tally"]) == sorted(result["vote_tally"])


@pytest.mark.parametrize("min_votes,expected", [(2, ["p1"]), (3, [])])
def test_min_votes_to_execute_comes_from_the_rule_set(min_votes, expected):
    """追放に必要な最少得票数をコードへ埋め込まない（NF-11）。"""

    result = _resolver(min_votes=min_votes).resolve(
        _votes(["p1", "p1", "p2", "p3", "p4", "p5", "p6", "p7"])
    )

    assert result["executed"] == expected


def test_rule_set_requires_two_votes_to_execute(v2_inputs):
    """`transcript.md` の「最多得票が1票のため」の文言が成り立つ前提を固定する。"""

    _pool, _patterns, rule_set = v2_inputs

    assert rule_set.vote.min_votes_to_execute == 2
