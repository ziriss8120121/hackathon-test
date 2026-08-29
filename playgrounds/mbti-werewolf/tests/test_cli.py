"""コマンド起動を確認する（設計書8.1、IF-07、F-23、AC-16）。

長時間の実行は画面を経由しないこの経路で行うため、サブコマンドが繋がっていること、
`--dry-run` が推論を呼ばずに条件固定の検査まで通ること、`--cases` で1ケースだけを
実測できることを確かめる。
"""

from __future__ import annotations

import json

from mbti_werewolf.__main__ import main


def _experiment_dir(runs_dir):
    return next(path for path in runs_dir.iterdir() if path.name.startswith("e-"))


def test_dry_run_generates_trials_without_calling_the_brain(tmp_path, capsys):
    """生成と条件固定の検査だけを行う。出力ディレクトリは作らない。"""

    code = main(["experiment", "--dry-run", "--runs-dir", str(tmp_path)])
    captured = capsys.readouterr()

    assert code == 0
    assert "ケース数: 17件" in captured.out
    assert "条件検査=通過" in captured.out
    assert "ケースは実行していない" in captured.out
    assert list(tmp_path.iterdir()) == []


def test_single_case_run_writes_every_output_file(tmp_path, capsys):
    """`--cases` で1ケースだけ実測する経路（設計書8.1）。"""

    code = main(
        [
            "experiment",
            "--brain",
            "stub",
            "--cases",
            "c00",
            "--runs-dir",
            str(tmp_path),
        ]
    )
    captured = capsys.readouterr()

    assert code == 0
    assert "完了 1" in captured.out
    assert "experiment_metrics.csv" in captured.out
    assert "latest.html" in captured.out

    case_dir = _experiment_dir(tmp_path) / "t001" / "c00-mixed"
    log = json.loads((case_dir / "case_log.json").read_text(encoding="utf-8"))
    assert log["composition"] == "mixed"
    assert len(log["players"]) == 8
    for name in ("config.json", "status.json", "transcript.md", "summary.md", "result.html"):
        assert (case_dir / name).is_file(), name
    assert (tmp_path / "latest.html").is_file()


def test_trial_range_and_seed_are_accepted(tmp_path, capsys):
    """分割実行の指定。`--trial-range` だけでも `trial_count` を補って通す。"""

    code = main(
        [
            "experiment",
            "--dry-run",
            "--trial-range",
            "2-3",
            "--seed",
            "77",
            "--runs-dir",
            str(tmp_path),
        ]
    )
    captured = capsys.readouterr()

    assert code == 0
    assert "Trial 2件（2-3）" in captured.out
    assert "seed=77" in captured.out
    assert "t002" in captured.out and "t003" in captured.out
    assert "t001" not in captured.out


def test_invalid_trial_range_returns_error_code(tmp_path, capsys):
    code = main(
        ["experiment", "--dry-run", "--trial-range", "3..7", "--runs-dir", str(tmp_path)]
    )
    captured = capsys.readouterr()

    assert code == 2
    assert "設定エラー" in captured.err


def test_judge_evaluates_a_finished_experiment_without_rerunning_the_game(
    tmp_path, capsys
):
    """ゲーム実行とJudgeが別コマンドであることの確認（設計書8.1、IF-09）。"""

    assert main(
        ["experiment", "--brain", "stub", "--cases", "c00", "--runs-dir", str(tmp_path)]
    ) == 0
    capsys.readouterr()

    experiment_id = _experiment_dir(tmp_path).name
    code = main(["judge", "--experiment", experiment_id, "--runs-dir", str(tmp_path)])
    captured = capsys.readouterr()

    assert code == 0
    assert "評価 1" in captured.out

    case_dir = _experiment_dir(tmp_path) / "t001" / "c00-mixed"
    payload = json.loads((case_dir / "judge.v1.json").read_text(encoding="utf-8"))
    assert payload["judge_criteria_version"] == "v1"
    assert len(payload["speeches"]) == len(payload["stance_series"])
    # 元の case_log.json は評価で書き換えない。
    log = json.loads((case_dir / "case_log.json").read_text(encoding="utf-8"))
    assert "judge" not in log


def test_judging_twice_skips_the_cases_that_already_have_this_version(tmp_path, capsys):
    assert main(
        ["experiment", "--brain", "stub", "--cases", "c00", "--runs-dir", str(tmp_path)]
    ) == 0
    experiment_id = _experiment_dir(tmp_path).name
    assert main(["judge", "--experiment", experiment_id, "--runs-dir", str(tmp_path)]) == 0
    capsys.readouterr()

    code = main(["judge", "--experiment", experiment_id, "--runs-dir", str(tmp_path)])
    captured = capsys.readouterr()

    assert code == 0
    assert "評価 0" in captured.out
    assert "評価済み 1" in captured.out


def test_judging_an_unknown_experiment_returns_error_code(tmp_path, capsys):
    code = main(
        ["judge", "--experiment", "e-99999999-999999", "--runs-dir", str(tmp_path)]
    )
    captured = capsys.readouterr()

    assert code == 2
    assert "評価エラー" in captured.err


def test_masterdata_writes_pool_and_patterns(tmp_path, capsys):
    code = main(
        [
            "masterdata",
            "--data-dir",
            str(tmp_path),
            "--patterns",
            "3",
        ]
    )
    captured = capsys.readouterr()

    assert code == 0
    pool = json.loads((tmp_path / "persons" / "pool-001.json").read_text(encoding="utf-8"))
    patterns = json.loads(
        (tmp_path / "patterns" / "pattern-set-001.json").read_text(encoding="utf-8")
    )
    assert len(pool["persons"]) == pool["count"]
    assert len(patterns["patterns"]) == 3
    assert "人物プール" in captured.out


def test_pages_builds_index_from_runs(tmp_path, capsys):
    runs_dir = tmp_path / "runs"
    code = main(
        [
            "experiment",
            "--brain",
            "stub",
            "--cases",
            "c00",
            "--runs-dir",
            str(runs_dir),
        ]
    )
    assert code == 0

    out = tmp_path / "site"
    code = main(["pages", "--runs-dir", str(runs_dir), "--out", str(out)])
    captured = capsys.readouterr()

    assert code == 0
    assert (out / "index.html").is_file()
    assert (out / ".nojekyll").is_file()
    assert (out / "404.html").is_file()

    html = (out / "index.html").read_text(encoding="utf-8")
    assert "ケース1件" in html
    assert "混合構成" in html
    assert "runs/latest.html" in html

    copied = list(out.glob("runs/*/t001/c00-mixed/result.html"))
    assert copied, "result.html がサイトへコピーされていない"
    assert (out / "runs" / "latest.html").is_file()
    assert "GitHub Pages用サイト" in captured.out


def test_analyze_missing_experiment_exits_2(tmp_path, capsys):
    code = main(
        ["analyze", "--experiment", "e-missing", "--runs-dir", str(tmp_path)]
    )
    captured = capsys.readouterr()

    assert code == 2
    assert "分析エラー" in captured.err


def test_no_subcommand_prints_help(capsys):
    code = main([])
    captured = capsys.readouterr()

    assert code == 1
    assert "experiment" in captured.out
    assert "judge" in captured.out
    assert "analyze" in captured.out
