"""コマンド起動を確認する。

対応要件: IF-07、F-23、AC-16、AC-10
"""

from __future__ import annotations

import json

from mbti_werewolf.__main__ import main


def _series_dir(tmp_path):
    return next(path for path in tmp_path.iterdir() if path.name.startswith("s-"))


def test_run_single_game(tmp_path, capsys):
    code = main(["run", "--brain", "stub", "--runs-dir", str(tmp_path)])
    captured = capsys.readouterr()

    assert code == 0
    assert "series_id:" in captured.out
    assert "成功 1 / 失敗 0" in captured.out

    log_path = _series_dir(tmp_path) / "r001" / "run_log.json"
    assert log_path.is_file()


def test_run_multiple_games_with_options(tmp_path, capsys):
    code = main(
        [
            "run",
            "--brain",
            "stub",
            "--games",
            "3",
            "--seed",
            "7",
            "--turns",
            "2",
            "--runs-dir",
            str(tmp_path),
        ]
    )
    captured = capsys.readouterr()

    assert code == 0
    assert "成功 3 / 失敗 0" in captured.out

    series = json.loads((_series_dir(tmp_path) / "series.json").read_text(encoding="utf-8"))
    assert series["game_count"] == 3
    assert series["config"]["turn_count"] == 2
    assert series["config"]["base_seed"] == 7
    assert (_series_dir(tmp_path) / "series_summary.md").is_file()


def test_settings_can_be_changed_without_code_edit(tmp_path):
    """8人版へ設定だけで広げられること（要件F-08、AC-10）。"""
    code = main(
        [
            "run",
            "--brain",
            "stub",
            "--players",
            "8",
            "--werewolves",
            "2",
            "--functions",
            "Ne,Ti,Fe,Si,Ni,Se,Te,Fi",
            "--turns",
            "1",
            "--runs-dir",
            str(tmp_path),
        ]
    )

    assert code == 0
    log = json.loads(
        (_series_dir(tmp_path) / "r001" / "run_log.json").read_text(encoding="utf-8")
    )
    assert len(log["players"]) == 8
    assert sum(1 for player in log["players"] if player["role"] == "werewolf") == 2
    assert len(log["turns"]) == 8
    assert len(log["votes"]) == 8


def test_invalid_config_returns_error_code(tmp_path, capsys):
    code = main(["run", "--brain", "stub", "--players", "2", "--runs-dir", str(tmp_path)])
    captured = capsys.readouterr()

    assert code == 2
    assert "設定エラー" in captured.err
