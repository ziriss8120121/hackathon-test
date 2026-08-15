"""想定外の応答でも試合が完走し、事象が記録されることを確認する。

対応要件: F-17（想定外応答での継続）、AC-11
"""

from __future__ import annotations

from mbti_werewolf.brains.base import extract_json
from mbti_werewolf.runner import Runner

from conftest import is_vote_prompt, read_json, speech, vote, voter_of


def test_extract_json_handles_preamble_and_fence():
    """小型モデルが付ける前置きとコードブロックを外せること（設計書5.4の段階2）。"""
    assert extract_json('{"speech": "ふつう"}') == {"speech": "ふつう"}
    assert extract_json('了解しました。{"speech": "前置きつき"} 以上です。') == {
        "speech": "前置きつき"
    }
    assert extract_json('```json\n{"speech": "囲みつき"}\n```') == {"speech": "囲みつき"}
    assert extract_json("JSONではありません") is None
    assert extract_json("") is None
    assert extract_json("[1, 2, 3]") is None


def test_preamble_response_is_not_treated_as_failure(tmp_path, make_config, use_brain):
    def responder(system, user, index):
        if is_vote_prompt(user):
            return "はい。" + vote(_first_candidate(user)) + " 以上です。"
        return "承知しました。" + speech("前置きつきの発言です。")

    use_brain(responder)
    runner = Runner(tmp_path)
    series_id, series = runner.run_series(make_config())
    log = read_json(tmp_path / series_id / "r001" / "run_log.json")

    assert series["status"] == "done"
    assert all(turn["parse_failed"] is False for turn in log["turns"])
    assert all(vote_entry["fallback"] is False for vote_entry in log["votes"])


def test_broken_json_completes_game_and_records_parse_failed(
    tmp_path, make_config, use_brain
):
    """JSONにならない応答でも試合は止まらない。崩れた事実は残る。"""

    def responder(system, user, index):
        return "これはJSONではない応答です。"

    use_brain(responder)
    runner = Runner(tmp_path)
    series_id, series = runner.run_series(make_config())
    log = read_json(tmp_path / series_id / "r001" / "run_log.json")

    assert series["status"] == "done", "形式が崩れても完走すること"
    assert len(log["turns"]) == 12
    assert all(turn["parse_failed"] is True for turn in log["turns"])
    assert all(turn["speech_text"] for turn in log["turns"]), "発言が空にならないこと"

    # 投票は最後にseed付き乱数で必ず1票にする（F-06）。
    assert all(vote_entry["fallback"] is True for vote_entry in log["votes"])
    assert all(vote_entry["invalid_retry_count"] > 0 for vote_entry in log["votes"])
    assert log["result"]["winner"] in ("village", "werewolf")


def test_vote_for_non_alive_player_is_retried_then_falls_back(
    tmp_path, make_config, use_brain
):
    """生存者以外への投票は不正として扱い、再要求してから乱数で決める（設計書3.3）。"""

    def responder(system, user, index):
        if is_vote_prompt(user):
            return vote("p99")
        return speech()

    use_brain(responder)
    runner = Runner(tmp_path)
    series_id, series = runner.run_series(make_config())
    log = read_json(tmp_path / series_id / "r001" / "run_log.json")

    assert series["status"] == "done"
    alive = {player["player_id"] for player in log["players"]}
    for vote_entry in log["votes"]:
        assert vote_entry["target"] in alive
        assert vote_entry["target"] != vote_entry["voter"]
        assert vote_entry["fallback"] is True
        assert vote_entry["invalid_retry_count"] > 0


def test_vote_target_with_extra_words_is_accepted(tmp_path, make_config, use_brain):
    """「p2さん」のような余分な語が付いた応答をIDとして解釈できること。"""

    def responder(system, user, index):
        if is_vote_prompt(user):
            return vote("プレイヤー{}さん".format(_first_candidate(user)))
        return speech()

    use_brain(responder)
    runner = Runner(tmp_path)
    series_id, series = runner.run_series(make_config())
    log = read_json(tmp_path / series_id / "r001" / "run_log.json")

    assert series["status"] == "done"
    assert all(vote_entry["fallback"] is False for vote_entry in log["votes"])
    assert all(vote_entry["invalid_retry_count"] == 0 for vote_entry in log["votes"])


def test_long_speech_is_truncated(tmp_path, make_config, use_brain):
    """字数上限を実装側でも抑える（設計書5.4）。"""
    limit = 40

    def responder(system, user, index):
        if is_vote_prompt(user):
            return vote(_first_candidate(user))
        return speech("あ" * 500)

    use_brain(responder)
    runner = Runner(tmp_path)
    series_id, _ = runner.run_series(make_config(brain={"max_output_chars": limit}))
    log = read_json(tmp_path / series_id / "r001" / "run_log.json")

    for turn in log["turns"]:
        assert len(turn["speech_text"]) <= limit


def _first_candidate(user: str) -> str:
    """投票プロンプトから自分以外の生存者を1人取り出す。"""
    voter = voter_of(user)
    for line in user.splitlines():
        if line.startswith("- あなたが投票できる相手:"):
            candidates = [
                part.strip() for part in line.split(":", 1)[1].split("、") if part.strip()
            ]
            for candidate in candidates:
                if candidate != voter:
                    return candidate
    return "p1"
