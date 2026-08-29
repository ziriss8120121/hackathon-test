"""実験条件とID、Trialの生成（設計書10章 test_experiment／6.4、6.6、F-55、NF-05）。"""

from __future__ import annotations

import json

import pytest

from mbti_werewolf import experiment as experiment_module
from mbti_werewolf import experiment_config as ec


# --- ID -------------------------------------------------------------------


def test_ids_follow_the_documented_format():
    """IDの形を固定する。ディレクトリ名とログの突き合わせがIDに依存する（設計書6.1）。"""

    from datetime import datetime

    experiment_id = experiment_module.make_experiment_id(datetime(2026, 1, 2, 3, 4, 5))
    trial_id = experiment_module.make_trial_id(experiment_id, 7)
    case_id = experiment_module.make_case_id(trial_id, 16)

    assert experiment_id == "e-20260102-030405"
    assert trial_id == "e-20260102-030405-t007"
    assert case_id == "e-20260102-030405-t007-c16"


def test_directory_names_are_derived_from_the_plan(build_trial):
    trial, _config, _rules = build_trial()

    assert trial.dir_name == "t001"
    assert trial.cases[0].dir_name == "c00-mixed"


# --- 設定の重ね方 ----------------------------------------------------------


def test_defaults_match_the_design_document(v2_config):
    config = v2_config()

    assert config.pool_id == "pool-001"
    assert config.pattern_set_id == "pattern-set-001"
    assert config.rule_set_id == "onenight-8p-v0.7"
    assert config.base_seed == 42
    assert config.discussion.max_rounds == 6
    assert config.discussion.max_speeches == 40
    assert config.discussion.max_speech_chars == 200
    assert config.brain.provider == "stub"


def test_file_then_override_wins(tmp_path, v2_config):
    """既定値 → ファイル → 上書きの順に重ねる（設計書6.4）。"""

    path = tmp_path / "config.json"
    path.write_text(
        json.dumps({"base_seed": 100, "discussion": {"max_rounds": 4}}),
        encoding="utf-8",
    )

    from_file = ec.load_config(path=path, overrides={"machine_name": "test"})
    assert from_file.base_seed == 100
    assert from_file.discussion.max_rounds == 4
    # ファイルで触れていない項目は既定値のまま残る。
    assert from_file.discussion.max_speeches == 40

    overridden = ec.load_config(
        path=path, overrides={"base_seed": 7, "machine_name": "test"}
    )
    assert overridden.base_seed == 7
    assert overridden.discussion.max_rounds == 4


def test_none_override_does_not_erase_a_value(v2_config):
    """CLI由来の未指定引数（None）で既定値を消さない（設計書6.4）。"""

    config = ec.load_config(overrides={"base_seed": None, "machine_name": "test"})

    assert config.base_seed == 42


def test_explicit_null_is_kept_for_nullable_keys():
    """null自体が意味を持つ項目では null を通す。"""

    config = ec.load_config(
        overrides={
            "trial_range": None,
            "discussion": {"max_consecutive_speeches": None},
            "machine_name": "test",
        }
    )

    assert config.trial_range is None
    assert config.discussion.max_consecutive_speeches is None


def test_unknown_config_key_is_rejected():
    with pytest.raises(ec.ConfigError) as exc:
        ec.load_config(overrides={"max_rounds": 3})

    assert "未知の設定項目" in str(exc.value)


@pytest.mark.parametrize(
    "overrides,expected",
    [
        ({"trial_count": 0}, "trial_count"),
        ({"trial_count": 2, "trial_range": [2, 1]}, "trial_range"),
        ({"trial_count": 2, "trial_range": [1, 3]}, "trial_count を超えている"),
        ({"discussion": {"max_rounds": 0}}, "discussion.max_rounds"),
        ({"discussion": {"max_consecutive_speeches": 0}}, "max_consecutive_speeches"),
        ({"brain": {"provider": "openai"}}, "未知の値"),
        ({"brain": {"provider": "ollama"}}, "model は provider"),
        ({"brain": {"temperature": 3.0}}, "temperature"),
    ],
)
def test_invalid_config_stops_before_running(overrides, expected):
    overrides.setdefault("machine_name", "test")

    with pytest.raises(ec.ConfigError) as exc:
        ec.load_config(overrides=overrides)

    assert expected in str(exc.value)


def test_machine_name_falls_back_to_environment(monkeypatch):
    """どのPCで実行したかを記録に残す（F-49）。"""

    monkeypatch.setenv(ec.ENV_MACHINE, "mac-a")
    config = ec.load_config()

    assert config.machine_name == "mac-a"


# --- seedとTrialの範囲 ----------------------------------------------------


def test_trial_seed_is_derived_from_base_seed(v2_config):
    """`trial_seed = base_seed + trial_index - 1`（設計書6.3）。"""

    config = v2_config(base_seed=42, trial_count=3)

    assert config.trial_seed(1) == 42
    assert config.trial_seed(2) == 43
    assert config.trial_seed(3) == 44


def test_trial_range_limits_which_trials_run(v2_config):
    """途中から再開・分担できるようにする（F-55）。"""

    config = v2_config(trial_count=10, trial_range=[4, 6])

    assert config.trial_indices() == (4, 5, 6)


def test_trial_range_keeps_the_seed_of_the_original_trial_number(v2_config):
    """範囲を絞っても Trial 4 のseedは変わらない。変わると再現できない。"""

    full = v2_config(trial_count=10)
    partial = v2_config(trial_count=10, trial_range=[4, 6])

    assert partial.trial_seed(4) == full.trial_seed(4)


# --- 実験計画 --------------------------------------------------------------


def test_experiment_builds_one_trial_per_index(v2_inputs, v2_config):
    pool, pattern_set, rule_set = v2_inputs
    config = v2_config(trial_count=3)

    plan = experiment_module.build_experiment(
        config, rule_set, pool, pattern_set, experiment_id="e-20260101-000000"
    )

    assert [t.trial_index for t in plan.trials] == [1, 2, 3]
    assert plan.to_dict()["case_count"] == 3 * 17


def test_experiment_stops_when_ids_do_not_match(v2_inputs, v2_config):
    """設定とマスタデータの取り違えを実行前に止める。"""

    pool, pattern_set, rule_set = v2_inputs
    config = v2_config(pool_id="pool-999")

    with pytest.raises(experiment_module.ExperimentError) as exc:
        experiment_module.build_experiment(config, rule_set, pool, pattern_set)

    assert "プールのID" in str(exc.value)


def test_experiment_stops_when_patterns_run_out(v2_inputs, v2_config):
    pool, pattern_set, rule_set = v2_inputs
    config = v2_config(trial_count=len(pattern_set.patterns) + 1)

    with pytest.raises(experiment_module.ExperimentError) as exc:
        experiment_module.build_experiment(config, rule_set, pool, pattern_set)

    assert "対応するパターンがない" in str(exc.value)


def test_trial_record_holds_every_fixed_condition(build_trial):
    """再現に必要な条件をTrialの記録に残す（F-49、NF-05）。"""

    trial, _config, _rules = build_trial()
    data = trial.to_dict()

    assert data["trial_seed"] == 42
    assert data["rule_set_version"] == "0.7"
    assert data["pattern_id"] == "pt001"
    fixed = data["fixed_conditions"]
    assert len(fixed["seats"]) == 8
    assert fixed["role_assignment_mode"] == "seeded_random"
    assert fixed["persona_prompt_version"] == "v2"
    assert set(fixed["discussion"]) == {
        "max_rounds",
        "max_speeches",
        "max_total_chars",
        "max_speech_chars",
        "max_consecutive_speeches",
        "stop_on_all_pass",
    }
    assert data["condition_check"]["passed"] is True


def test_trial_seats_record_the_pool_mbti(build_trial):
    """座席の記録は混合構成のMBTIを持つ。同質構成で上書きした値と混ぜない。"""

    trial, _config, _rules = build_trial()
    seats = trial.to_dict()["fixed_conditions"]["seats"]

    mixed = trial.cases[0].players
    assert [s["pool_mbti"] for s in seats] == [p.mbti for p in mixed]


def test_role_deck_is_dealt_in_seat_order(build_trial):
    trial, _config, _rules = build_trial()

    assert len(trial.initial_roles) == 8
    assert sorted(trial.initial_roles) == sorted(
        ["werewolf", "werewolf", "seer", "thief"] + ["villager"] * 4
    )
    assert [p.initial_role for p in trial.cases[0].players] == list(trial.initial_roles)
