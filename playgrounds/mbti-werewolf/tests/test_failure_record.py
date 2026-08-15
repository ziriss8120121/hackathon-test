"""実行が失敗したときに、原因と部分結果が残ることを確認する。

対応要件: F-37、NF-07、AC-11
"""

from __future__ import annotations

from mbti_werewolf.brains.base import BrainError
from mbti_werewolf.runner import Runner

from conftest import is_vote_prompt, read_json, speech, vote, voter_of


def test_rate_limited_leaves_partial_log_and_error_kind(
    tmp_path, make_config, use_brain
):
    """無料枠の上限に達した場合を模す。自動で別の脳へ切り替えず、失敗として残す。"""
    fail_after = 5

    def responder(system, user, index):
        if index >= fail_after:
            raise BrainError("rate_limited", "無料枠の上限に達しました。")
        return speech("上限に達する前の発言です。")

    use_brain(responder)
    runner = Runner(tmp_path)
    series_id, series = runner.run_series(make_config())

    assert series["status"] == "failed"
    assert series["failure_count"] == 1

    run_dir = tmp_path / series_id / "r001"
    log = read_json(run_dir / "run_log.json")

    assert log["status"] == "failed"
    assert log["failure"]["kind"] == "rate_limited"
    assert "上限" in log["failure"]["message"]

    # それまでの発言は保持されている（F-37）。
    assert 0 < len(log["turns"]) < 12
    assert log["result"] is None
    assert log["phase"] == "failed"

    # 状態ファイルからも原因が判別できる（NF-07）。
    status = read_json(run_dir / "status.json")
    assert status["status"] == "failed"
    assert status["error"]["kind"] == "rate_limited"

    # 失敗表示つきの結果ビューも生成される（F-55）。
    html = (run_dir / "result.html").read_text(encoding="utf-8")
    assert "rate_limited" in html
    assert (run_dir / "summary.md").is_file()
    assert (run_dir / "timeline.md").is_file()


def test_unreachable_is_classified(tmp_path, make_config, use_brain):
    """接続不可も種別を分けて記録する。切り替え判断の材料になる（NF-08）。"""

    def responder(system, user, index):
        raise BrainError("unreachable", "Ollamaに接続できません。")

    use_brain(responder)
    runner = Runner(tmp_path)
    series_id, _series = runner.run_series(make_config())
    log = read_json(tmp_path / series_id / "r001" / "run_log.json")

    assert log["failure"]["kind"] == "unreachable"
    assert log["turns"] == []


def test_series_continues_after_a_failed_game(tmp_path, make_config, use_brain):
    """多試合実行では1試合の失敗で全体を止めない（設計書3.5）。"""
    # 1試合は 発言12回 + 投票4回 = 16呼び出し。2試合目の最初の呼び出しだけを失敗させる。
    calls = {"count": 0}

    def responder(system, user, index):
        calls["count"] += 1
        if calls["count"] == 17:
            raise BrainError("timeout", "応答が返りませんでした。")
        if is_vote_prompt(user):
            return vote(_other_than(voter_of(user)))
        return speech()

    use_brain(responder)
    runner = Runner(tmp_path)
    config = make_config(game_count=3)

    series_id, series = runner.run_series(config)

    assert series["status"] == "partial"
    assert series["success_count"] == 2
    assert series["failure_count"] == 1
    assert [entry["status"] for entry in series["runs"]] == ["done", "failed", "done"]

    summary = (tmp_path / series_id / "series_summary.md").read_text(encoding="utf-8")
    assert "失敗した試合" in summary
    assert "timeout" in summary


def _other_than(voter: str) -> str:
    for candidate in ("p1", "p2", "p3", "p4"):
        if candidate != voter:
            return candidate
    return "p1"
