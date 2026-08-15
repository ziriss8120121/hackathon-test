"""Stubで1試合が完走し、出力ファイルが揃うことを確認する。

対応要件: F-07（人の介入なしの完走）、F-30〜F-34、AC-01〜AC-03、AC-05
"""

from __future__ import annotations

import csv

from mbti_werewolf.record.metrics import CSV_COLUMNS
from mbti_werewolf.runner import Runner

from conftest import read_json


def test_stub_game_completes_and_writes_outputs(tmp_path, make_config):
    config = make_config()
    runner = Runner(tmp_path)

    series_id, series = runner.run_series(config)

    assert series["status"] == "done"
    assert series["success_count"] == 1

    run_dir = tmp_path / series_id / "r001"
    for name in (
        "config.json",
        "status.json",
        "run_log.json",
        "summary.md",
        "timeline.md",
        "metrics.csv",
        "result.html",
    ):
        assert (run_dir / name).is_file(), "{} が出力されていない".format(name)

    assert (tmp_path / series_id / "series.json").is_file()
    assert (tmp_path / series_id / "series_summary.md").is_file()


def test_run_log_contents(tmp_path, make_config):
    config = make_config()
    runner = Runner(tmp_path)
    series_id, _ = runner.run_series(config)
    log = read_json(tmp_path / series_id / "r001" / "run_log.json")

    assert log["status"] == "done"
    assert log["run_id"] == "{}-r001".format(series_id)
    assert log["series_id"] == series_id

    # 4人、人狼1、村人3（AC-01）
    assert len(log["players"]) == 4
    assert sum(1 for p in log["players"] if p["role"] == "werewolf") == 1
    assert all(p["agent_prompt_version"] == "v1" for p in log["players"])
    assert {p["function"] for p in log["players"]} == {"Ne", "Ti", "Fe", "Si"}

    # 議論3ターン、投票1回、勝敗判定（AC-02）
    assert len(log["turns"]) == 12
    assert sorted({turn["turn"] for turn in log["turns"]}) == [1, 2, 3]
    assert len(log["votes"]) == 4
    assert log["result"]["winner"] in ("village", "werewolf")
    assert log["result"]["executed"] in {p["player_id"] for p in log["players"]}

    # 実行環境と時間（AC-05）
    timing = log["timing"]
    for key in ("started_at", "ended_at", "elapsed_seconds", "ai_wait_seconds", "machine_name"):
        assert timing.get(key) not in (None, "")

    # 使用した推論手段が特定できる（F-16、AC-08）
    assert log["brain"]["provider"] == "stub"
    assert log["brain"]["endpoint_kind"] == "stub"


def test_winner_matches_executed_role(tmp_path, make_config):
    config = make_config()
    runner = Runner(tmp_path)
    series_id, _ = runner.run_series(config)
    log = read_json(tmp_path / series_id / "r001" / "run_log.json")

    executed_role = log["result"]["executed_role"]
    expected = "village" if executed_role == "werewolf" else "werewolf"
    assert log["result"]["winner"] == expected


def test_metrics_csv_has_required_columns(tmp_path, make_config):
    config = make_config()
    runner = Runner(tmp_path)
    series_id, _ = runner.run_series(config)

    with (tmp_path / series_id / "r001" / "metrics.csv").open(encoding="utf-8") as fp:
        rows = list(csv.reader(fp))

    assert rows[0] == list(CSV_COLUMNS)
    assert len(rows) == 5  # ヘッダ + 4人


def test_result_html_is_self_contained(tmp_path, make_config):
    """外部を読まないこと。file:// でもGitHub Pagesでも同じに表示される（F-41、NF-15）。"""
    config = make_config()
    runner = Runner(tmp_path)
    series_id, _ = runner.run_series(config)

    html = (tmp_path / series_id / "r001" / "result.html").read_text(encoding="utf-8")

    assert '<script type="application/json" id="run-data">' in html
    assert "src=" not in html
    assert 'rel="stylesheet"' not in html
    assert "fetch(" not in html


def test_multiple_games_in_one_series(tmp_path, make_config):
    config = make_config(game_count=3)
    runner = Runner(tmp_path)
    series_id, series = runner.run_series(config)

    assert series["success_count"] == 3
    assert [entry["run_index"] for entry in series["runs"]] == [1, 2, 3]
    for index in (1, 2, 3):
        assert (tmp_path / series_id / "r{:03d}".format(index) / "run_log.json").is_file()

    # 試合ごとに seed をずらす。1試合目は指定した base_seed のまま（設計書3.5）。
    seeds = [
        read_json(tmp_path / series_id / "r{:03d}".format(i) / "config.json")["seed"]
        for i in (1, 2, 3)
    ]
    assert seeds == [config.seed, config.seed + 1, config.seed + 2]
