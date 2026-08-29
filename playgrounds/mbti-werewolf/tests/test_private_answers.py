"""2時点の個別判断とprivate memo（設計書10章 test_private_answers／5.3、F-19、F-24、F-28）。"""

from __future__ import annotations

import json

from mbti_werewolf.agents.case_agent import MEMO_MAX_CHARS, REASON_MAX_CHARS
from mbti_werewolf.agents.persona import SUSPECT_UNKNOWN

from v2_support import default_responder


def test_both_time_points_are_collected_for_all_players(run_case):
    outcome, _brain, _case, _trial, _config, _rules = run_case()

    ids = [p.player_id for p in outcome.players]
    assert [a["player_id"] for a in outcome.pre_discussion_answers] == ids
    assert [a["player_id"] for a in outcome.pre_vote_answers] == ids


def test_pre_discussion_allows_unknown_but_pre_vote_does_not(run_case):
    """議論前は判断材料がないので unknown を認め、投票直前は認めない（設計書5.3）。"""

    outcome, _brain, _case, _trial, _config, _rules = run_case()

    assert all(a["suspect"] == SUSPECT_UNKNOWN for a in outcome.pre_discussion_answers)
    for answer in outcome.pre_vote_answers:
        assert answer["suspect"] != SUSPECT_UNKNOWN
        assert answer["suspect"] != answer["player_id"]


def test_pre_vote_unknown_is_retried_then_becomes_skip(run_case):
    def responder(tag, player_id, request, index):
        if tag == "pre_vote":
            return json.dumps(
                {
                    "suspect": "unknown",
                    "confidence": 3,
                    "reason": "分からない。",
                    "planned_vote": "unknown",
                }
            )
        return default_responder()(tag, player_id, request, index)

    outcome, _brain, _case, _trial, _config, _rules = run_case(responder)

    for answer in outcome.pre_vote_answers:
        assert answer["parse_failed"] is True
        assert answer["attempts"] == 3
        assert answer["suspect"] is None
        assert answer["planned_vote"] is None


def test_confidence_outside_one_to_five_is_invalid(run_case):
    def responder(tag, player_id, request, index):
        if tag == "pre_discussion":
            return json.dumps(
                {
                    "role_awareness": "自分の情報だけ。",
                    "suspect": "unknown",
                    "confidence": 9,
                    "reason": "根拠なし。",
                }
            )
        return default_responder()(tag, player_id, request, index)

    outcome, _brain, _case, _trial, _config, _rules = run_case(responder)

    for answer in outcome.pre_discussion_answers:
        assert answer["parse_failed"] is True
        assert answer["confidence"] is None
        assert answer["suspect"] == SUSPECT_UNKNOWN


def test_confidence_is_kept_as_one_to_five_integer(run_case):
    outcome, _brain, _case, _trial, _config, _rules = run_case()

    for answer in outcome.pre_discussion_answers + outcome.pre_vote_answers:
        assert answer["confidence"] in (1, 2, 3, 4, 5)


def test_reason_is_clipped(run_case):
    def responder(tag, player_id, request, index):
        base = json.loads(default_responder()(tag, player_id, request, index))
        if "reason" in base:
            base["reason"] = "あ" * 300
        return json.dumps(base, ensure_ascii=False)

    outcome, _brain, _case, _trial, _config, _rules = run_case(responder)

    for answer in outcome.pre_discussion_answers + outcome.pre_vote_answers:
        assert len(answer["reason"]) == REASON_MAX_CHARS


def test_memo_is_collected_for_every_speech_and_vote(run_case):
    """発言ごと・投票ごとに1文の判断理由を取る（要件F-28、要求定義書課題A5）。"""

    outcome, _brain, _case, _trial, _config, _rules = run_case()

    spoke = [e for e in outcome.discussion.events if e["spoke"]]
    assert spoke
    assert all(e["memo"] for e in spoke)
    assert all(v["memo"] for v in outcome.votes if not v["abstained"])


def test_memo_is_clipped(run_case):
    def responder(tag, player_id, request, index):
        base = json.loads(default_responder()(tag, player_id, request, index))
        if "memo" in base:
            base["memo"] = "い" * 300
        return json.dumps(base, ensure_ascii=False)

    outcome, _brain, _case, _trial, _config, _rules = run_case(responder)

    for event in outcome.discussion.events:
        if event["spoke"]:
            assert len(event["memo"]) == MEMO_MAX_CHARS


def test_memo_missing_is_not_an_invalid_answer(run_case):
    """memoが欠けても発言自体は有効にする。memoは指標の入力ではない（設計書5.3）。"""

    def responder(tag, player_id, request, index):
        if tag == "speak":
            return json.dumps({"speak": True, "speech": "様子を見ます。"})
        return default_responder()(tag, player_id, request, index)

    outcome, _brain, _case, _trial, _config, _rules = run_case(responder)

    spoke = [e for e in outcome.discussion.events if e["spoke"]]
    assert spoke
    assert all(e["attempts"] == 1 and e["memo"] == "" for e in spoke)


def test_pre_discussion_is_asked_before_any_speech(run_case):
    """議論前の判断は、公開発言を見る前に取らないと2時点の比較にならない。"""

    _outcome, brain, _case, _trial, _config, _rules = run_case()

    tags = [c["tag"] for c in brain.calls]
    assert tags.index("pre_discussion") < tags.index("speak")
    assert tags.index("speak") < tags.index("pre_vote")
    assert tags.index("pre_vote") < tags.index("vote")


def test_pre_discussion_prompt_has_no_speech_log(run_case):
    _outcome, brain, _case, _trial, _config, _rules = run_case()

    for call in brain.calls:
        if call["tag"] == "pre_discussion":
            assert "ここまでの公開発言" not in call["user"]
