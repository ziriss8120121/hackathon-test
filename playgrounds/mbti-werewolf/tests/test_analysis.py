"""分析出力（設計書3.6、9.4、6.9、6.10 / 要件F-63〜F-65）。

推論は呼ばない。Stubで1 Trialを実行し、Judgeを通してから `analyze` する。
"""

from __future__ import annotations

import csv

import pytest

from mbti_werewolf.analysis.analyzer import AnalyzeError, Analyzer
from mbti_werewolf.analysis.indicators import convergence_round, frozen_note
from mbti_werewolf.analysis.stats import friedman, median, wilcoxon_signed_rank
from mbti_werewolf.brains.factory import create_case_brain
from mbti_werewolf.judge.judge import Criteria, ExperimentJudge
from mbti_werewolf.record.metrics_csv import EXPERIMENT_COLUMNS, SPEECH_COLUMNS
from mbti_werewolf.runner import ExperimentRunner


@pytest.fixture
def runner_for(v2_config, v2_data_dir, tmp_path):
    def build(**overrides):
        case_filter = overrides.pop("case_filter", None)
        overrides.setdefault("machine_name", "test")
        return ExperimentRunner(
            v2_config(**overrides),
            data_dir=v2_data_dir,
            runs_dir=tmp_path,
            case_filter=case_filter,
        )

    return build


def _judge_then_analyze(tmp_path, v2_config, experiment_id="e-20260101-000000"):
    config = v2_config(machine_name="test")
    ExperimentJudge(
        runs_dir=tmp_path,
        brain_factory=lambda: create_case_brain(config, seed=config.base_seed, judge=True),
        criteria=Criteria(),
    ).run(experiment_id)
    return Analyzer(tmp_path).run(experiment_id)


# --- 統計 --------------------------------------------------------------------


def test_median_skips_none():
    assert median([1, None, 3, 2]) == 2


def test_wilcoxon_finds_a_consistent_difference():
    left = [3, 4, 5, 6, 7, 8]
    right = [0, 1, 0, 1, 0, 1]
    result = wilcoxon_signed_rank(left, right)
    assert result["n"] == 6
    assert result["p_two_sided"] < 0.05
    assert result["r"] > 0


def test_wilcoxon_drops_zero_differences_and_missing_pairs():
    result = wilcoxon_signed_rank([1, 1, None], [1, 0, 3])
    assert result["n"] == 1


def test_friedman_is_zero_when_every_condition_is_tied():
    result = friedman([[5, 5, 5], [5, 5, 5], [5, 5, 5]])
    assert result["n"] == 3
    assert result["q"] == 0
    assert result["p"] == pytest.approx(1.0, abs=0.05)


def test_friedman_drops_rows_with_a_missing_value():
    result = friedman([[1, 2, 3], [1, None, 3], [3, 2, 1]])
    assert result["n"] == 2


# --- 収束ラウンド -------------------------------------------------------------


def test_convergence_round_is_null_when_nobody_is_executed():
    case_log = {"result": {"executed": []}, "discussion": {"events": []}}
    series = [{"at_speech_id": "s1", "suspicion_distribution": {"p4": 3}}]
    assert convergence_round(case_log, series) is None


def test_convergence_round_is_the_first_round_that_stays_on_the_top_voted():
    case_log = {
        "result": {"executed": ["p4"]},
        "discussion": {
            "events": [
                {"speech_id": "s1", "round": 1},
                {"speech_id": "s2", "round": 2},
                {"speech_id": "s3", "round": 3},
            ]
        },
    }
    series = [
        {"at_speech_id": "s1", "suspicion_distribution": {"p2": 2}},
        {"at_speech_id": "s2", "suspicion_distribution": {"p4": 3}},
        {"at_speech_id": "s3", "suspicion_distribution": {"p4": 4}},
    ]
    assert convergence_round(case_log, series) == 2


def test_convergence_round_is_null_when_the_mode_moves_again():
    case_log = {
        "result": {"executed": ["p4"]},
        "discussion": {
            "events": [
                {"speech_id": "s1", "round": 1},
                {"speech_id": "s2", "round": 2},
            ]
        },
    }
    series = [
        {"at_speech_id": "s1", "suspicion_distribution": {"p4": 3}},
        {"at_speech_id": "s2", "suspicion_distribution": {"p2": 3}},
    ]
    assert convergence_round(case_log, series) is None


def test_frozen_note_requires_the_indicator_to_predate_the_run():
    assert "確認的" in frozen_note("2026-01-01T00:00:00", "2026-02-01T00:00:00")
    assert "探索的" in frozen_note(None, "2026-02-01T00:00:00")
    assert "探索的" in frozen_note("2026-03-01T00:00:00", "2026-02-01T00:00:00")


# --- 実行を通す ---------------------------------------------------------------


def test_incomplete_trial_is_excluded_with_a_reason(runner_for, tmp_path):
    runner_for(case_filter=["c00"]).run(experiment_id="e-20260101-000000")
    summary = Analyzer(tmp_path).run("e-20260101-000000")

    assert summary["eligible_count"] == 0
    assert summary["excluded_count"] == 1
    report = (tmp_path / "e-20260101-000000" / "experiment_report.md").read_text(
        encoding="utf-8"
    )
    assert "17ケース揃っていない" in report
    assert "除外したTrial" in report


def test_missing_judge_excludes_the_trial_from_rq(runner_for, tmp_path):
    runner_for().run(experiment_id="e-20260101-000000")
    summary = Analyzer(tmp_path).run("e-20260101-000000")

    assert summary["eligible_count"] == 0
    rq1 = (tmp_path / "e-20260101-000000" / "rq1.md").read_text(encoding="utf-8")
    assert "Judge評価がない" in rq1
    assert "確認的分析" in rq1 or "探索的分析" in rq1


def test_analyze_fills_judge_columns_and_writes_speech_labels(
    runner_for, tmp_path, v2_config
):
    runner_for().run(experiment_id="e-20260101-000000")
    summary = _judge_then_analyze(tmp_path, v2_config)

    assert summary["eligible_count"] == 1
    assert summary["speech_label_rows"] > 0

    exp_dir = tmp_path / "e-20260101-000000"
    with (exp_dir / "experiment_metrics.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert list(rows[0].keys()) == list(EXPERIMENT_COLUMNS)
    filled = [row["final_entropy"] for row in rows if row["final_entropy"]]
    assert filled, "Judge後も final_entropy が空欄のまま"
    # 空欄と0を区別する。埋まった行は数値として読める。
    float(filled[0])

    with (exp_dir / "speech_labels.csv").open(encoding="utf-8", newline="") as handle:
        speeches = list(csv.DictReader(handle))
    assert list(speeches[0].keys()) == list(SPEECH_COLUMNS)
    assert speeches[0]["mbti"]
    assert speeches[0]["player_id"]
    # 複数ラベルは | 区切り。カンマだと表計算ソフトで列がずれる。
    multi = [row for row in speeches if "|" in row["labels"]]
    assert multi, "複数ラベルの行がない"


def test_rq_files_state_their_analysis_kind(runner_for, tmp_path, v2_config):
    runner_for().run(experiment_id="e-20260101-000000")
    _judge_then_analyze(tmp_path, v2_config)

    exp_dir = tmp_path / "e-20260101-000000"
    rq1 = (exp_dir / "rq1.md").read_text(encoding="utf-8")
    rq2 = (exp_dir / "rq2.md").read_text(encoding="utf-8")
    check = (exp_dir / "manipulation_check.md").read_text(encoding="utf-8")

    assert "探索的分析として読む必要がある" in rq1
    assert "Wilcoxon" in rq1
    assert "探索的分析である" in rq2
    assert "Friedman" in rq2
    assert "個別比較は行わない" in rq2 or "順位の提示" in rq2
    assert "recorded" in check
    assert "drafted" in check


def test_analysis_html_embeds_json_and_renders_tables(
    runner_for, tmp_path, v2_config
):
    runner_for().run(experiment_id="e-20260101-000000")
    _judge_then_analyze(tmp_path, v2_config)

    html_text = (tmp_path / "e-20260101-000000" / "experiment.html").read_text(
        encoding="utf-8"
    )
    assert 'type="application/json"' in html_text
    assert "有効Trial数" in html_text
    assert "<table" in html_text
    assert "analysis-data" in html_text

    trial_html = (tmp_path / "e-20260101-000000" / "t001" / "trial.html").read_text(
        encoding="utf-8"
    )
    assert "補助分析" in trial_html
    assert "c00-mixed/result.html" in trial_html


def test_latest_html_points_to_the_experiment_after_analyze(
    runner_for, tmp_path, v2_config
):
    runner_for().run(experiment_id="e-20260101-000000")
    before = (tmp_path / "latest.html").read_text(encoding="utf-8")
    assert "result.html" in before

    _judge_then_analyze(tmp_path, v2_config)

    after = (tmp_path / "latest.html").read_text(encoding="utf-8")
    assert "e-20260101-000000/experiment.html" in after
    assert (tmp_path / "e-20260101-000000" / "experiment.html").is_file()


def test_analyze_without_the_experiment_directory_stops(tmp_path):
    with pytest.raises(AnalyzeError):
        Analyzer(tmp_path).run("e-does-not-exist")


def test_trial_report_is_marked_as_auxiliary(runner_for, tmp_path, v2_config):
    runner_for().run(experiment_id="e-20260101-000000")
    _judge_then_analyze(tmp_path, v2_config)

    text = (tmp_path / "e-20260101-000000" / "t001" / "trial_report.md").read_text(
        encoding="utf-8"
    )
    assert "補助分析" in text
    assert "混合" in text
    assert "同質" in text
