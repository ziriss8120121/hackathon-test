"""投票の収集（設計書10章 test_vote／要件F-25、F-26、4.6）。"""

from __future__ import annotations

import json

from conftest import default_responder


def test_every_player_votes_once(run_case):
    outcome, _brain, _case, _trial, _config, _rules = run_case()

    ids = [p.player_id for p in outcome.players]
    assert [v["voter"] for v in outcome.votes] == ids


def test_self_vote_is_rejected_and_retried(run_case):
    """自分への投票は認めない（ルール文書v0.7 §1）。"""

    seen = {"first": True}

    def responder(tag, player_id, request, index):
        if tag == "vote" and seen["first"]:
            seen["first"] = False
            return json.dumps({"target": player_id.upper(), "memo": "自分。"})
        return default_responder()(tag, player_id, request, index)

    outcome, _brain, _case, _trial, _config, _rules = run_case(responder)

    first = outcome.votes[0]
    assert first["attempts"] == 2
    assert first["target"] != first["voter"]
    assert all(v["target"] != v["voter"] for v in outcome.votes if not v["abstained"])


def test_out_of_range_target_is_rejected(run_case):
    def responder(tag, player_id, request, index):
        if tag == "vote":
            return json.dumps({"target": "P9", "memo": "存在しない。"})
        return default_responder()(tag, player_id, request, index)

    outcome, _brain, _case, _trial, _config, _rules = run_case(responder)

    assert all(v["abstained"] is True and v["attempts"] == 3 for v in outcome.votes)


def test_three_invalid_answers_mean_abstain_not_random(run_case):
    """乱数で投票先を埋めない（設計書5.4）。埋めると投票正解率に偽の値が混ざる。"""

    def responder(tag, player_id, request, index):
        if tag == "vote":
            return "誰にしよう"
        return default_responder()(tag, player_id, request, index)

    outcome, _brain, _case, _trial, _config, _rules = run_case(responder)

    for vote in outcome.votes:
        assert vote["abstained"] is True
        assert vote["target"] is None
        assert vote["parse_failed"] is True
        assert vote["attempts"] == 3


def test_vote_prompt_shows_seven_candidates(run_case):
    _outcome, brain, _case, _trial, _config, _rules = run_case()

    vote_calls = [c for c in brain.calls if c["tag"] == "vote"]
    assert vote_calls
    for call in vote_calls:
        assert len(call["choices"]) == 7
        assert call["player_id"].upper() not in call["choices"]


def test_lowercase_vote_is_accepted(run_case):
    def responder(tag, player_id, request, index):
        if tag == "vote":
            return json.dumps({"target": request.choices[0].lower(), "memo": "選ぶ。"})
        return default_responder()(tag, player_id, request, index)

    outcome, _brain, _case, _trial, _config, _rules = run_case(responder)

    assert all(v["attempts"] == 1 for v in outcome.votes)
    assert all(v["target"] == v["target"].lower() for v in outcome.votes)
