"""自由議論（設計書10章 test_discussion／要件F-20〜F-23、4.5、AC-04）。"""

from __future__ import annotations

import json
import re

from mbti_werewolf.engine.discussion import poll_order

from v2_support import default_responder


def _events(outcome):
    return outcome.discussion.events


def _spoken_rounds(outcome, player_id):
    return sorted(
        e["round"] for e in _events(outcome) if e["player_id"] == player_id and e["spoke"]
    )


def _max_consecutive(rounds):
    best = current = 0
    previous = None
    for value in rounds:
        current = current + 1 if previous is not None and value == previous + 1 else 1
        previous = value
        best = max(best, current)
    return best


def test_all_pass_ends_the_discussion(run_case):
    outcome, _brain, _case, _trial, _config, _rules = run_case(
        default_responder(speak=False)
    )

    assert outcome.discussion.stop_reason == "all_pass"
    assert outcome.discussion.rounds == 1
    assert outcome.discussion.total_speeches == 0
    assert outcome.discussion.total_passes == 8


def test_max_rounds_stops_the_discussion(run_case):
    outcome, _brain, _case, _trial, _config, _rules = run_case(
        discussion={"max_rounds": 3}
    )

    assert outcome.discussion.stop_reason == "max_rounds"
    assert outcome.discussion.rounds == 3


def test_round_with_no_eligible_player_still_counts(run_case):
    """全員が連続発言の上限に達したラウンドもラウンド数に数える（設計書4.5）。

    数えないと、上限を設けたことで議論ラウンド数が静かに減り、`max_rounds` と
    実際のラウンド数が食い違う。
    """

    outcome, _brain, _case, _trial, _config, _rules = run_case(
        discussion={"max_rounds": 3, "max_consecutive_speeches": 2}
    )

    rounds_with_events = {e["round"] for e in _events(outcome)}
    assert outcome.discussion.rounds == 3
    assert rounds_with_events == {1, 2}


def test_max_speeches_stops_the_discussion(run_case):
    outcome, _brain, _case, _trial, _config, _rules = run_case(
        discussion={"max_speeches": 5, "max_rounds": 6}
    )

    assert outcome.discussion.stop_reason == "max_speeches"
    assert outcome.discussion.total_speeches == 5


def test_max_total_chars_stops_the_discussion(run_case):
    outcome, _brain, _case, _trial, _config, _rules = run_case(
        discussion={"max_total_chars": 60, "max_rounds": 6}
    )

    assert outcome.discussion.stop_reason == "max_total_chars"
    assert outcome.discussion.total_chars >= 60


def test_consecutive_speech_limit_is_enforced(run_case):
    outcome, _brain, _case, _trial, _config, _rules = run_case(
        discussion={"max_consecutive_speeches": 2, "max_rounds": 6}
    )

    for player in outcome.players:
        rounds = _spoken_rounds(outcome, player.player_id)
        assert _max_consecutive(rounds) <= 2, player.player_id


def test_excluded_player_returns_in_a_later_round(run_case):
    """上限に達した人が二度と対象へ戻らないと、議論が数人に収束してしまう。"""

    outcome, _brain, _case, _trial, _config, _rules = run_case(
        discussion={"max_consecutive_speeches": 2, "max_rounds": 6}
    )

    for player in outcome.players:
        assert len(_spoken_rounds(outcome, player.player_id)) >= 3, player.player_id


def test_consecutive_limit_can_be_disabled_with_null(run_case):
    """`max_consecutive_speeches: null` で上限なしにできる（設計書6.4）。"""

    outcome, _brain, _case, _trial, _config, _rules = run_case(
        discussion={"max_consecutive_speeches": None, "max_rounds": 3}
    )

    for player in outcome.players:
        assert _spoken_rounds(outcome, player.player_id) == [1, 2, 3]


def test_pass_and_skip_are_recorded_differently(run_case):
    """本人が選んだ見送りと、応答が得られなかったスキップを区別する（設計書4.5）。"""

    def responder(tag, player_id, request, index):
        if tag == "speak" and player_id == "p1":
            return "うーん"
        if tag == "speak" and player_id == "p2":
            return json.dumps({"speak": False, "memo": "今は待つ。"}, ensure_ascii=False)
        return default_responder()(tag, player_id, request, index)

    outcome, _brain, _case, _trial, _config, _rules = run_case(responder)

    p1 = [e for e in _events(outcome) if e["player_id"] == "p1"]
    p2 = [e for e in _events(outcome) if e["player_id"] == "p2"]

    assert p1 and p2
    assert all(e["spoke"] is False and e["skipped"] is True for e in p1)
    assert all(e["parse_failed"] is True and e["attempts"] == 3 for e in p1)
    assert all(e["spoke"] is False and e["skipped"] is False for e in p2)
    assert all(e["parse_failed"] is False and e["memo"] for e in p2)


def test_pass_does_not_block_other_players(run_case):
    """1人が黙り続けても、他の参加者の議論は進む。"""

    def responder(tag, player_id, request, index):
        if tag == "speak" and player_id == "p1":
            return json.dumps({"speak": False, "memo": "様子を見る。"}, ensure_ascii=False)
        return default_responder()(tag, player_id, request, index)

    outcome, _brain, _case, _trial, _config, _rules = run_case(responder)

    assert _spoken_rounds(outcome, "p1") == []
    assert outcome.discussion.total_speeches > 0


def test_empty_speech_is_not_counted_as_a_speech(run_case):
    """空回答は正常な発言として数えない（ルール文書v0.7 §2-5）。"""

    def responder(tag, player_id, request, index):
        if tag == "speak" and player_id == "p3":
            return json.dumps({"speak": True, "speech": "", "memo": "空。"})
        return default_responder()(tag, player_id, request, index)

    outcome, _brain, _case, _trial, _config, _rules = run_case(responder)

    p3 = [e for e in _events(outcome) if e["player_id"] == "p3"]
    assert p3
    assert all(e["spoke"] is False and e["skipped"] is True for e in p3)


def test_long_speech_is_truncated(run_case):
    long_text = "あ" * 500

    def responder(tag, player_id, request, index):
        if tag == "speak":
            return json.dumps({"speak": True, "speech": long_text, "memo": "長い。"})
        return default_responder()(tag, player_id, request, index)

    outcome, _brain, _case, _trial, _config, _rules = run_case(
        responder, discussion={"max_speech_chars": 200, "max_rounds": 1}
    )

    spoken = [e for e in _events(outcome) if e["spoke"]]
    assert spoken
    for event in spoken:
        assert event["chars"] == 200
        assert event["truncated"] is True


def test_events_hold_order_and_speech_id(run_case):
    """`order` は発言と見送りの通し番号、`speech_id` は発言だけの通し番号（設計書6.7）。"""

    outcome, _brain, case, _trial, _config, _rules = run_case()

    events = _events(outcome)
    assert [e["order"] for e in events] == list(range(1, len(events) + 1))

    speech_ids = [e["speech_id"] for e in events if e["spoke"]]
    assert len(speech_ids) == outcome.discussion.total_speeches
    assert speech_ids[0] == "{0}-s001".format(case.case_id)
    assert all("speech_id" not in e for e in events if not e["spoke"])


def test_poll_order_is_reproducible_and_varies_by_round():
    ids = ["p{0}".format(i) for i in range(1, 9)]

    assert poll_order(ids, 42, 1) == poll_order(ids, 42, 1)
    assert poll_order(ids, 42, 1) != poll_order(ids, 42, 2)
    assert sorted(poll_order(ids, 42, 1)) == sorted(ids)
    assert poll_order(ids, 42, 1) != poll_order(ids, 43, 1)


def test_poll_order_is_identical_across_cases_in_a_trial(run_case):
    """問い合わせ順が17ケースで揃っていないと、MBTI以外の変数が動く（設計書3.1）。"""

    mixed, _b1, _c1, _t1, _cf1, _r1 = run_case(case_index=0)
    istj, _b2, _c2, _t2, _cf2, _r2 = run_case(case_index=1)

    def order_of(outcome, round_no):
        return [e["player_id"] for e in outcome.discussion.events if e["round"] == round_no]

    assert order_of(mixed, 1) == order_of(istj, 1)


def test_speech_log_shows_only_public_speeches(run_case):
    """見送った人の行を公開発言ログへ出さない（設計書4.7）。

    誰が黙っているかが場に見える情報になると、ルールに定めのない手掛かりを
    議論へ持ち込むことになる。
    """

    def responder(tag, player_id, request, index):
        if tag == "speak" and player_id == "p1":
            return json.dumps({"speak": False, "memo": "黙る。"}, ensure_ascii=False)
        return default_responder()(tag, player_id, request, index)

    _outcome, brain, _case, _trial, _config, _rules = run_case(responder)

    for call in brain.calls:
        assert re.search(r"^\d+\. P1:", call["user"], re.M) is None
