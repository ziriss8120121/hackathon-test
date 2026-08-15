"""得票が同数でも試合が終了し、決着方法が記録されることを確認する。

対応要件: F-06（常に1試合が終了する状態）
"""

from __future__ import annotations

from mbti_werewolf.engine.tiebreak import break_tie
from mbti_werewolf.runner import Runner

from conftest import is_vote_prompt, read_json, speech, vote, voter_of

# 2票対2票になるように投票先を固定する。
TIE_MAP = {"p1": "p2", "p4": "p2", "p2": "p1", "p3": "p1"}


def test_break_tie_is_deterministic():
    first, info = break_tie(["p3", "p1"], seed=42, turn_count=3)
    second, _ = break_tie(["p1", "p3"], seed=42, turn_count=3)

    assert first == second, "候補の順序が違っても同じseedなら同じ結果になること"
    assert first in ("p1", "p3")
    assert info["method"] == "seeded_random"
    assert info["candidates"] == ["p1", "p3"]
    assert info["seed"] == 45


def test_tied_vote_still_finishes_and_records_tie_break(
    tmp_path, make_config, use_brain
):
    def responder(system, user, index):
        if is_vote_prompt(user):
            return vote(TIE_MAP[voter_of(user)])
        return speech()

    use_brain(responder)
    runner = Runner(tmp_path)
    series_id, series = runner.run_series(make_config())
    log = read_json(tmp_path / series_id / "r001" / "run_log.json")

    assert series["status"] == "done"
    assert log["result"]["vote_counts"] == {"p1": 2, "p2": 2}

    tie_break = log["result"]["tie_break"]
    assert tie_break is not None, "同数得票の決着方法が記録されていない"
    assert tie_break["method"] == "seeded_random"
    assert tie_break["candidates"] == ["p1", "p2"]
    assert log["result"]["executed"] == tie_break["player_id"]
    assert log["result"]["winner"] in ("village", "werewolf")

    # 乱数で決めた処刑であることが人の読む出力からも分かること。
    summary = (tmp_path / series_id / "r001" / "summary.md").read_text(encoding="utf-8")
    assert "同数得票" in summary
