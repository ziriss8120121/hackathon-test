"""中断と再開（設計書10章 test_resume／3.5、6.5、F-51〜F-53、AC-12）。

`test_condition_fixation` と並んでv2.0で最も重要なテストである。ここが壊れると
数時間から数日かけた実行データを失う、または気付かないまま条件が変わった状態で
実行を続けることになる。
"""

from __future__ import annotations

import json
import re

import pytest

from mbti_werewolf import experiment as experiment_module
from mbti_werewolf.runner import (
    STATUS_SKIPPED,
    ExperimentRunner,
    ResumeError,
    error_kind_of,
)
from mbti_werewolf.record.case_log import STATUS_DONE, STATUS_FAILED


@pytest.fixture
def runner_for(v2_config, v2_data_dir, tmp_path):
    """スタブで実験を実行するRunner。出力先を tmp_path にする。"""

    def build(**overrides):
        case_filter = overrides.pop("case_filter", None)
        case_attempts = overrides.pop("case_attempts", 2)
        overrides.setdefault("machine_name", "test")
        config = v2_config(**overrides)
        return ExperimentRunner(
            config,
            data_dir=v2_data_dir,
            runs_dir=tmp_path,
            case_attempts=case_attempts,
            case_filter=case_filter,
        )

    return build


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize(root):
    """実験IDと時刻を落として全ケースの記録を比べられる形にする。"""

    exp_dir = next(root.iterdir())
    payload = {
        case_dir.name: _read(case_dir / "case_log.json")
        for trial_dir in sorted(exp_dir.iterdir())
        if trial_dir.is_dir()
        for case_dir in sorted(trial_dir.iterdir())
        if case_dir.is_dir()
    }
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    text = re.sub(r"e-\d{8}-\d{6}", "EXP", text)
    text = re.sub(r"\d{4}-\d{2}-\d{2}T[\d:+]+", "TIME", text)
    text = re.sub(
        r'"(wait_seconds|elapsed_seconds|ai_wait_seconds)": [\d.]+', r'"\1": 0', text
    )
    return text


# --- ケースを絞って実行する ------------------------------------------------


def test_case_filter_runs_only_the_named_cases(runner_for):
    """1ケースだけの実測に使う（M5前の所要時間の見積もり）。"""

    runner = runner_for(case_filter=["c00"])
    summary = runner.run(experiment_id="e-20260101-000000")

    assert summary["done_count"] == 1
    assert summary["skipped_count"] == 16
    ran = [c for c in summary["cases"] if c["status"] != STATUS_SKIPPED]
    assert [c["case_id"] for c in ran] == ["e-20260101-000000-t001-c00"]


def test_case_filter_accepts_directory_names(runner_for):
    runner = runner_for(case_filter=["c00-mixed", "c05-ISTP"])
    summary = runner.run(experiment_id="e-20260101-000000")

    assert summary["done_count"] == 2


# --- 再開 -----------------------------------------------------------------


def test_resume_skips_done_cases(runner_for):
    first = runner_for(case_filter=["c00", "c01"])
    first.run(experiment_id="e-20260101-000000")

    second = runner_for()
    summary = second.resume("e-20260101-000000")

    assert summary["resumed"] is True
    assert summary["skipped_count"] == 2
    assert summary["done_count"] == 15
    ran = {c["case_id"] for c in summary["cases"] if c["status"] != STATUS_SKIPPED}
    assert "e-20260101-000000-t001-c00" not in ran


def test_resume_reproduces_the_same_records(runner_for, tmp_path, v2_config, v2_data_dir):
    """途中で止めて再開した結果が、一気に実行した結果と一致すること（AC-12）。

    実験IDと時刻、所要時間は実行ごとに変わるため比較から外す。`speech_id` は
    ケースIDを含むので、実験IDを置き換えた後で比べる。
    """

    runner_for(case_filter=["c00", "c01"]).run(experiment_id="e-20260101-000000")
    runner_for().resume("e-20260101-000000")

    whole_dir = tmp_path / "whole"
    ExperimentRunner(
        v2_config(machine_name="test"), data_dir=v2_data_dir, runs_dir=whole_dir
    ).run(experiment_id="e-20260202-000000")

    resumed_dir = tmp_path / "resumed"
    resumed_dir.mkdir()
    (tmp_path / "e-20260101-000000").rename(resumed_dir / "e-20260101-000000")

    assert _normalize(resumed_dir) == _normalize(whole_dir)


def test_resume_restores_fixed_conditions_from_trial_json(runner_for, tmp_path):
    """座席と役職を作り直さない。作り直すとTrial内で条件が変わる（F-53）。"""

    first = runner_for(case_filter=["c00"])
    first.run(experiment_id="e-20260101-000000")

    trial_path = tmp_path / "e-20260101-000000" / "t001" / "trial.json"
    before = _read(trial_path)["fixed_conditions"]

    runner_for().resume("e-20260101-000000")

    assert _read(trial_path)["fixed_conditions"] == before


def test_resume_ignores_conflicting_settings(runner_for, tmp_path):
    """再開時はTrialの記録が正本である（設計書3.5、5.7）。

    違う議論条件で再開しても、Trialの17ケースは同じ条件で実行される。混ざると
    その差がMBTIの差と区別できなくなる。
    """

    first = runner_for(case_filter=["c00"], discussion={"max_rounds": 2})
    first.run(experiment_id="e-20260101-000000")

    notes = []
    second = runner_for(discussion={"max_rounds": 6})
    second._on_progress = notes.append
    second.resume("e-20260101-000000")

    case_dir = tmp_path / "e-20260101-000000" / "t001" / "c05-ISTP"
    log = _read(case_dir / "case_log.json")
    assert log["discussion"]["limits"]["max_rounds"] == 2
    assert any("Trialの記録で条件を上書き" in note for note in notes)


def test_resume_counts_attempts(runner_for, tmp_path):
    """再実行したケースに attempt を加算する（設計書3.5）。"""

    runner_for(case_filter=["c00"]).run(experiment_id="e-20260101-000000")
    status_path = tmp_path / "e-20260101-000000" / "t001" / "c00-mixed" / "status.json"
    assert _read(status_path)["attempt"] == 1

    # 完了済みを強制的に未実行へ戻すと、再開で2回目として実行される。
    trial_path = tmp_path / "e-20260101-000000" / "t001" / "trial.json"
    raw = _read(trial_path)
    raw["cases"][0]["status"] = "pending"
    trial_path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

    runner_for(case_filter=["c00"]).resume("e-20260101-000000")

    assert _read(status_path)["attempt"] == 2


def test_resume_retries_failed_cases(runner_for, tmp_path):
    """失敗したケースは再開の対象にする。done だけを飛ばす。"""

    runner_for(case_filter=["c00"]).run(experiment_id="e-20260101-000000")
    trial_path = tmp_path / "e-20260101-000000" / "t001" / "trial.json"
    raw = _read(trial_path)
    raw["cases"][0]["status"] = STATUS_FAILED
    trial_path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

    summary = runner_for(case_filter=["c00"]).resume("e-20260101-000000")

    assert summary["done_count"] == 1
    assert summary["skipped_count"] == 16


def test_resume_without_the_experiment_file_stops(runner_for):
    with pytest.raises(ResumeError) as exc:
        runner_for().resume("e-20990101-000000")

    assert "実験のファイルがない" in str(exc.value)


def test_resume_stops_when_the_rule_version_changed(runner_for, tmp_path):
    """ルール文書の改訂後に古い実験を再開しない。混ぜると比較できなくなる。"""

    runner_for(case_filter=["c00"]).run(experiment_id="e-20260101-000000")
    path = tmp_path / "e-20260101-000000" / "experiment.json"
    raw = _read(path)
    raw["rule_set_version"] = "0.6"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ResumeError) as exc:
        runner_for().resume("e-20260101-000000")

    assert "ルールセットの版" in str(exc.value)


def _v2_masters(v2_inputs):
    pool, pattern_set, _rule_set = v2_inputs
    return pool, pattern_set


def _saved_trial(v2_inputs, config, rule_set):
    trial = experiment_module.build_trial(
        "e-20260101-000000", 1, config, rule_set, *_v2_masters(v2_inputs)
    )
    return trial.to_dict()


def test_restore_trial_reproduces_the_seats(v2_inputs, v2_config):
    _pool, _patterns, rule_set = v2_inputs
    config = v2_config(machine_name="test")
    raw = _saved_trial(v2_inputs, config, rule_set)

    restored = experiment_module.restore_trial(raw, config, rule_set)

    assert restored.to_dict()["fixed_conditions"]["seats"] == raw["fixed_conditions"]["seats"]
    assert restored.initial_roles == tuple(
        s["initial_role"] for s in raw["fixed_conditions"]["seats"]
    )
    assert len(restored.cases) == 17
    assert restored.condition_check["varying_keys"] == ["mbti"]


def test_restore_trial_rejects_a_hand_edited_role_deck(v2_inputs, v2_config):
    """役職の枚数がルールと合わない `trial.json` で停止する。

    17ケースを見比べる条件固定の検査では見つからない。全ケースへ同じ座席を配るため、
    どのケースも同じように誤るためである。
    """

    _pool, _patterns, rule_set = v2_inputs
    config = v2_config(machine_name="test")
    raw = _saved_trial(v2_inputs, config, rule_set)
    for seat in raw["fixed_conditions"]["seats"][:3]:
        seat["initial_role"] = "werewolf"

    with pytest.raises(experiment_module.ExperimentError) as exc:
        experiment_module.restore_trial(raw, config, rule_set)

    assert "役職構成" in str(exc.value)


def test_restore_trial_rejects_a_wrong_seat_count(v2_inputs, v2_config):
    _pool, _patterns, rule_set = v2_inputs
    config = v2_config(machine_name="test")
    raw = _saved_trial(v2_inputs, config, rule_set)
    raw["fixed_conditions"]["seats"] = raw["fixed_conditions"]["seats"][:7]

    with pytest.raises(experiment_module.ExperimentError) as exc:
        experiment_module.restore_trial(raw, config, rule_set)

    assert "座席数" in str(exc.value)


# --- 失敗したケースの扱い ---------------------------------------------------


def test_failed_case_is_retried_then_recorded(runner_for, tmp_path, monkeypatch):
    """1回目が失敗したら1回だけ作り直して試す。それでも失敗したら次へ進む（F-51）。"""

    from mbti_werewolf.engine import case as case_module

    calls = {"count": 0}
    original = case_module.CaseEngine.run

    def flaky(self):
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("最初の1回だけ失敗する")
        return original(self)

    monkeypatch.setattr(case_module.CaseEngine, "run", flaky)

    summary = runner_for(case_filter=["c00"]).run(experiment_id="e-20260101-000000")

    assert calls["count"] == 2
    assert summary["done_count"] == 1
    assert summary["failed_count"] == 0
    status = _read(tmp_path / "e-20260101-000000" / "t001" / "c00-mixed" / "status.json")
    assert status["status"] == STATUS_DONE
    assert status["attempt"] == 2


def test_case_failure_does_not_stop_the_trial(runner_for, tmp_path, monkeypatch):
    from mbti_werewolf.engine import case as case_module

    def always_fail(self):
        raise RuntimeError("必ず失敗する")

    monkeypatch.setattr(case_module.CaseEngine, "run", always_fail)

    summary = runner_for(case_filter=["c00", "c01"]).run(
        experiment_id="e-20260101-000000"
    )

    assert summary["failed_count"] == 2
    assert summary["done_count"] == 0
    status = _read(tmp_path / "e-20260101-000000" / "t001" / "c00-mixed" / "status.json")
    assert status["status"] == STATUS_FAILED
    assert status["error"]["kind"] == "internal"


def test_incomplete_trial_is_marked_in_status(runner_for, tmp_path):
    """17ケースが1つでも欠けたTrialを分析側で除外できるようにする（F-51、9.4）。"""

    runner_for(case_filter=["c00"]).run(experiment_id="e-20260101-000000")

    trial_status = _read(tmp_path / "e-20260101-000000" / "t001" / "status.json")
    assert trial_status["complete"] is False
    assert trial_status["case_done"] == 1
    assert trial_status["case_pending"] == 16

    runner_for().resume("e-20260101-000000")

    trial_status = _read(tmp_path / "e-20260101-000000" / "t001" / "status.json")
    assert trial_status["complete"] is True
    assert trial_status["case_done"] == 17


def test_experiment_status_tracks_progress(runner_for, tmp_path):
    summary = runner_for().run(experiment_id="e-20260101-000000")

    status = _read(tmp_path / "e-20260101-000000" / "status.json")
    assert status["status"] == STATUS_DONE
    assert status["trial_total"] == 1
    assert status["trial_complete"] == 1
    assert status["case_total"] == 17
    assert status["case_done"] == 17
    assert status["case_pending"] == 0
    assert summary["trial_complete_count"] == 1


def test_experiment_status_counts_the_whole_experiment(runner_for, tmp_path):
    """実験の `status.json` は前回までの完了分も含めて数える（設計書6.5）。

    再開のたびに0から数え直すと、100 Trialの実行で全体の進み具合が読めなくなる。
    実行担当が画面で見る要約は今回の実行分なので、そちらとは数え方が違う。
    """

    runner_for(case_filter=["c00", "c01", "c02"]).run(experiment_id="e-20260101-000000")
    summary = runner_for().resume("e-20260101-000000")

    status = _read(tmp_path / "e-20260101-000000" / "status.json")
    assert status["case_done"] == 17
    assert status["case_pending"] == 0
    assert status["case_skipped"] == 0

    # 要約は今回の実行で何をしたかを出す。
    assert summary["done_count"] == 14
    assert summary["skipped_count"] == 3


def test_filtered_cases_are_counted_as_skipped_not_done(runner_for, tmp_path):
    runner_for(case_filter=["c00"]).run(experiment_id="e-20260101-000000")

    status = _read(tmp_path / "e-20260101-000000" / "status.json")
    assert status["case_done"] == 1
    assert status["case_skipped"] == 16
    assert status["case_pending"] == 0


def test_error_kind_falls_back_to_internal():
    from mbti_werewolf.brains.base import BrainError

    assert error_kind_of(BrainError("rate_limited", "429")) == "rate_limited"
    assert error_kind_of(BrainError("timeout", "遅い")) == "timeout"
    assert error_kind_of(RuntimeError("想定外")) == "internal"


def test_case_status_holds_progress_fields(runner_for, tmp_path):
    """画面が短い間隔で読むファイル。発言そのものは載せない（設計書6.5）。"""

    runner_for(case_filter=["c00"]).run(experiment_id="e-20260101-000000")

    status = _read(tmp_path / "e-20260101-000000" / "t001" / "c00-mixed" / "status.json")

    assert set(status) == {
        "case_id",
        "trial_id",
        "experiment_id",
        "composition",
        "homogeneous_type",
        "status",
        "phase",
        "round",
        "max_rounds",
        "speech_count",
        "inference_calls",
        "attempt",
        "started_at",
        "updated_at",
        "error",
    }
    assert status["speech_count"] > 0
    assert "speech_text" not in json.dumps(status)


def test_master_data_snapshot_is_saved(runner_for, tmp_path):
    """`data/` を後から書き換えても、過去の実験が指す人物定義は変わらない（F-03）。"""

    runner_for(case_filter=["c00"]).run(experiment_id="e-20260101-000000")

    exp_dir = tmp_path / "e-20260101-000000"
    assert _read(exp_dir / "pool_snapshot.json")["count"] == 100
    assert len(_read(exp_dir / "pattern_snapshot.json")["patterns"]) == 100


def test_resume_does_not_reread_the_pool_and_patterns(runner_for, tmp_path, v2_data_dir):
    """座席は trial.json が持っているので、プールとパターンを読み直さない。

    読み直す実装だと、`data/` の人物プールを差し替えた後に再開したとき、同じTrialの
    座席が入れ替わる。
    """

    import shutil

    runner_for(case_filter=["c00"]).run(experiment_id="e-20260101-000000")

    rules_only = tmp_path / "data-rules-only"
    (rules_only / "rules").mkdir(parents=True)
    shutil.copytree(v2_data_dir / "rules", rules_only / "rules", dirs_exist_ok=True)

    runner = runner_for()
    runner.data_dir = rules_only
    summary = runner.resume("e-20260101-000000")

    assert summary["done_count"] == 16
    assert summary["failed_count"] == 0
