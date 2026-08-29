"""Runnerが出力ファイルを揃えて書くか（設計書6.1、6.9、7.5、7.6、M3）。

`test_case_outputs` が1ファイルの中身を見るのに対し、こちらは実行を通してファイルが
どこへ何件できるかを見る。とくに再開したときに集計CSVが今回の実行分だけにならない
ことを確かめる。
"""

from __future__ import annotations

import csv
import json

import pytest

from mbti_werewolf.runner import ExperimentRunner
from mbti_werewolf.record.metrics_csv import EXPERIMENT_COLUMNS, TRIAL_COLUMNS

CASE_FILES = ("case_log.json", "config.json", "status.json", "transcript.md",
              "summary.md", "result.html")


@pytest.fixture
def runner_for(v2_config, v2_data_dir, tmp_path):
    def build(**overrides):
        case_filter = overrides.pop("case_filter", None)
        case_attempts = overrides.pop("case_attempts", 2)
        overrides.setdefault("machine_name", "test")
        return ExperimentRunner(
            v2_config(**overrides),
            data_dir=v2_data_dir,
            runs_dir=tmp_path,
            case_attempts=case_attempts,
            case_filter=case_filter,
        )

    return build


def _rows(path):
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _exp(tmp_path):
    return tmp_path / "e-20260101-000000"


# --- ケースごとの出力 -------------------------------------------------------


def test_every_completed_case_has_the_full_set_of_files(runner_for, tmp_path):
    runner_for().run(experiment_id="e-20260101-000000")

    trial_dir = _exp(tmp_path) / "t001"
    case_dirs = sorted(d for d in trial_dir.iterdir() if d.is_dir())
    assert len(case_dirs) == 17
    for case_dir in case_dirs:
        for name in CASE_FILES:
            assert (case_dir / name).is_file(), "{0}/{1} がない".format(case_dir.name, name)


def test_case_files_are_not_empty(runner_for, tmp_path):
    runner_for(case_filter=["c00"]).run(experiment_id="e-20260101-000000")

    case_dir = _exp(tmp_path) / "t001" / "c00-mixed"
    for name in CASE_FILES:
        assert (case_dir / name).stat().st_size > 0
    timing = (_exp(tmp_path) / "timing.md").read_text(encoding="utf-8")
    assert "実行時間の実測" in timing
    assert "stub" in timing


def test_skipped_cases_have_no_output_directory(runner_for, tmp_path):
    """`--cases` で外したケースは空のディレクトリも作らない。

    作ると、実行済みのケースと見分けが付かなくなる。
    """

    runner_for(case_filter=["c00"]).run(experiment_id="e-20260101-000000")

    trial_dir = _exp(tmp_path) / "t001"
    case_dirs = [d.name for d in trial_dir.iterdir() if d.is_dir()]
    assert case_dirs == ["c00-mixed"]


# --- 集計CSV ---------------------------------------------------------------


def test_trial_csv_has_one_row_per_player_per_case(runner_for, tmp_path):
    runner_for().run(experiment_id="e-20260101-000000")

    rows = _rows(_exp(tmp_path) / "t001" / "trial_metrics.csv")
    assert len(rows) == 17 * 8
    assert list(rows[0]) == list(TRIAL_COLUMNS)


def test_experiment_csv_has_one_row_per_case(runner_for, tmp_path):
    runner_for().run(experiment_id="e-20260101-000000")

    rows = _rows(_exp(tmp_path) / "experiment_metrics.csv")
    assert len(rows) == 17
    assert list(rows[0]) == list(EXPERIMENT_COLUMNS)


def test_csv_covers_all_seventeen_cases_in_index_order(runner_for, tmp_path):
    runner_for().run(experiment_id="e-20260101-000000")

    rows = _rows(_exp(tmp_path) / "experiment_metrics.csv")
    assert [row["case_index"] for row in rows] == [str(i) for i in range(17)]
    assert rows[0]["composition"] == "mixed"
    assert all(row["composition"] == "homogeneous" for row in rows[1:])


def test_resumed_run_writes_csv_for_every_case_not_only_this_session(
    runner_for, tmp_path
):
    """再開した実行のCSVに、前回までに完了したケースも入ること。

    実行中の結果だけを使うと、再開したときのCSVに今回のケースしか出ない。分析側は
    CSVをTrialの正本として読むため、ここが欠けるとTrialが不完全に見える。
    """

    runner_for(case_filter=["c00", "c01"]).run(experiment_id="e-20260101-000000")
    partial = _rows(_exp(tmp_path) / "experiment_metrics.csv")
    assert len(partial) == 2

    runner_for().resume("e-20260101-000000")

    assert len(_rows(_exp(tmp_path) / "experiment_metrics.csv")) == 17
    assert len(_rows(_exp(tmp_path) / "t001" / "trial_metrics.csv")) == 17 * 8


def test_csv_holds_a_header_even_when_no_case_ran(runner_for, tmp_path):
    """列の形だけでも確認できるようにする。"""

    runner_for(case_filter=["存在しないケース"]).run(experiment_id="e-20260101-000000")

    path = _exp(tmp_path) / "experiment_metrics.csv"
    assert path.is_file()
    assert _rows(path) == []
    assert path.read_text(encoding="utf-8").startswith("experiment_id,")


def test_csv_values_match_the_case_log(runner_for, tmp_path):
    runner_for(case_filter=["c00"]).run(experiment_id="e-20260101-000000")

    log = json.loads(
        (_exp(tmp_path) / "t001" / "c00-mixed" / "case_log.json").read_text(
            encoding="utf-8"
        )
    )
    row = _rows(_exp(tmp_path) / "experiment_metrics.csv")[0]

    assert row["case_id"] == log["case_id"]
    assert row["winner"] == (log["result"]["winner"] or "")
    assert row["rounds"] == str(log["discussion"]["rounds"])
    assert row["inference_calls"] == str(log["timing"]["inference_calls"])
    assert row["machine_name"] == "test"


# --- 最新結果リンク ---------------------------------------------------------


def test_latest_html_points_at_the_last_completed_case(runner_for, tmp_path):
    runner_for().run(experiment_id="e-20260101-000000")

    text = (tmp_path / "latest.html").read_text(encoding="utf-8")
    assert "e-20260101-000000/t001/c16-ENTJ/result.html" in text


def test_latest_html_is_updated_during_the_run(runner_for, tmp_path):
    """1ケース終えるごとに更新する。実行中でもいま何が出ているかを見られる（7.6）。"""

    runner_for(case_filter=["c00"]).run(experiment_id="e-20260101-000000")
    first = (tmp_path / "latest.html").read_text(encoding="utf-8")
    assert "c00-mixed" in first

    runner_for(case_filter=["c02"]).run(experiment_id="e-20260202-000000")
    second = (tmp_path / "latest.html").read_text(encoding="utf-8")
    assert "c02-ISFJ" in second
    assert "c00-mixed" not in second


def test_latest_html_target_exists(runner_for, tmp_path):
    """壊れたリンクを置かない。相対パスの組み立て間違いをここで捕まえる。"""

    runner_for(case_filter=["c05"]).run(experiment_id="e-20260101-000000")

    text = (tmp_path / "latest.html").read_text(encoding="utf-8")
    target = text.split("url=./", 1)[1].split('"', 1)[0]
    assert (tmp_path / target).is_file()


def test_latest_html_is_not_written_when_every_case_failed(runner_for, tmp_path):
    """失敗しか出ていない実行で、前回の正常な結果リンクを壊さない。"""

    runner_for(case_filter=["c00"]).run(experiment_id="e-20260101-000000")
    good = (tmp_path / "latest.html").read_text(encoding="utf-8")

    def explode(*_args, **_kwargs):
        raise RuntimeError("失敗させる")

    runner = runner_for(case_filter=["c01"])
    import mbti_werewolf.runner as runner_module

    original = runner_module.CaseEngine
    runner_module.CaseEngine = explode
    try:
        runner.run(experiment_id="e-20260202-000000")
    finally:
        runner_module.CaseEngine = original

    assert (tmp_path / "latest.html").read_text(encoding="utf-8") == good


# --- 失敗したケース ---------------------------------------------------------


def test_failed_case_still_gets_a_result_html(runner_for, tmp_path):
    """失敗したケースだけHTMLが無いと、一覧から開いたときに404になる（7.5）。"""

    def explode(*_args, **_kwargs):
        raise RuntimeError("失敗させる")

    runner = runner_for(case_filter=["c00"], case_attempts=1)
    import mbti_werewolf.runner as runner_module

    original = runner_module.CaseEngine
    runner_module.CaseEngine = explode
    try:
        runner.run(experiment_id="e-20260101-000000")
    finally:
        runner_module.CaseEngine = original

    case_dir = _exp(tmp_path) / "t001" / "c00-mixed"
    html_text = (case_dir / "result.html").read_text(encoding="utf-8")
    assert "失敗" in html_text
    assert "--resume" in html_text
    # case_log.json が無いので、通常の出力は書かれない。
    assert not (case_dir / "case_log.json").exists()
    assert not (case_dir / "summary.md").exists()
