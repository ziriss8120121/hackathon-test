"""17ケースの条件固定（設計書10章 test_condition_fixation／要件F-11、F-12、NF-06、AC-02）。

v2.0で最も重要なテストである。ここが壊れると、MBTI構成以外の条件が動いた状態で
比較することになり、何時間実行しても結果が無効になる。
"""

from __future__ import annotations

import copy

import pytest

from mbti_werewolf import experiment as experiment_module
from mbti_werewolf import masterdata as md
from mbti_werewolf.agents.mbti_types import TYPE_STACKS


def test_trial_has_one_mixed_and_sixteen_homogeneous_cases(build_trial):
    trial, _config, _rules = build_trial()

    assert len(trial.cases) == 17
    assert trial.cases[0].composition == "mixed"
    assert trial.cases[0].homogeneous_type is None
    assert [c.homogeneous_type for c in trial.cases[1:]] == list(TYPE_STACKS)


def test_case_index_order_follows_type_stacks(build_trial):
    """ケース番号とタイプの対応を固定する（設計書6.2）。

    ここがずれると、過去の実験の `c05` が指すタイプが変わり、比較できなくなる。
    """

    trial, _config, _rules = build_trial()

    assert trial.cases[1].dir_name == "c01-ISTJ"
    assert trial.cases[16].dir_name == "c16-ENTJ"


def test_only_mbti_varies_across_cases(build_trial):
    trial, _config, _rules = build_trial()

    assert trial.condition_check["passed"] is True
    assert trial.condition_check["varying_keys"] == ["mbti"]


def test_person_age_gender_and_role_are_identical_in_every_case(build_trial):
    trial, _config, _rules = build_trial()

    baseline = trial.cases[0].players
    for case in trial.cases[1:]:
        for seat, (base, player) in enumerate(zip(baseline, case.players)):
            assert player.player_id == base.player_id, seat
            assert player.person_id == base.person_id, seat
            assert player.age == base.age, seat
            assert player.gender == base.gender, seat
            assert player.initial_role == base.initial_role, seat


def test_homogeneous_case_replaces_every_seat_mbti(build_trial):
    trial, _config, _rules = build_trial()

    istj_case = trial.cases[1]
    assert {p.mbti for p in istj_case.players} == {"ISTJ"}


def test_seat_to_person_mapping_is_fixed_within_trial(build_trial):
    """17ケースを通じて `p3` は同じ人物を指す（設計書6.2）。"""

    trial, _config, _rules = build_trial()

    p3_persons = {case.players[2].person_id for case in trial.cases}
    assert len(p3_persons) == 1


def test_role_assignment_is_reproducible_from_trial_seed(build_trial):
    first, _c1, _r1 = build_trial(trial_index=1)
    again, _c2, _r2 = build_trial(trial_index=1)

    assert first.initial_roles == again.initial_roles
    assert first.pattern_id == again.pattern_id


def test_different_trial_changes_pattern_and_roles(build_trial):
    trial1, _c1, _r1 = build_trial(trial_index=1, trial_count=2)
    trial2, _c2, _r2 = build_trial(trial_index=2, trial_count=2)

    assert trial1.trial_seed != trial2.trial_seed
    assert trial1.pattern_id != trial2.pattern_id


def test_condition_check_fails_when_a_seat_role_differs(build_trial):
    """意図的に条件をずらすと停止する（AC-02）。"""

    trial, _config, _rules = build_trial()
    cases = copy.deepcopy(trial.cases)
    cases[3].players[0].initial_role = "werewolf"

    with pytest.raises(experiment_module.ConditionFixationError) as exc:
        experiment_module.check_condition_fixation(cases)

    assert "initial_role" in str(exc.value)


def test_condition_check_fails_when_age_differs(build_trial):
    trial, _config, _rules = build_trial()
    cases = copy.deepcopy(trial.cases)
    cases[5].players[2].age = cases[5].players[2].age + 1

    with pytest.raises(experiment_module.ConditionFixationError) as exc:
        experiment_module.check_condition_fixation(cases)

    assert "age" in str(exc.value)


def test_condition_check_fails_when_mbti_does_not_vary(build_trial):
    """MBTIに差がないのも失敗にする。生成が壊れている兆候である。"""

    trial, _config, _rules = build_trial()
    cases = copy.deepcopy(trial.cases[:2])
    for case in cases:
        for player in case.players:
            player.mbti = "ISTJ"

    with pytest.raises(experiment_module.ConditionFixationError) as exc:
        experiment_module.check_condition_fixation(cases)

    assert "なし" in str(exc.value)


def test_pool_composition_matches_requirements(v2_inputs):
    """人物プールの配分が要求定義書8.2のとおりであること。"""

    pool, _patterns, _rules = v2_inputs

    assert pool.count == 100
    assert sum(pool.composition["mbti"].values()) == 100
    assert (
        sum(sum(g.values()) for g in pool.composition["age_gender"].values()) == 100
    )
    assert pool.assignment_mode == "seeded_random_independent"


def test_pool_rejects_inconsistent_composition(tmp_path, v2_inputs):
    pool, _patterns, _rules = v2_inputs
    payload = pool.to_dict()
    payload["persons"][0]["mbti"] = "ENTJ" if payload["persons"][0]["mbti"] != "ENTJ" else "ISTJ"
    path = tmp_path / "pool-bad.json"
    md.write_json(path, payload)

    with pytest.raises(md.PoolError):
        md.load_person_pool(path)


def test_pattern_rejects_duplicate_person(tmp_path, v2_inputs):
    pool, pattern_set, _rules = v2_inputs
    payload = pattern_set.to_dict()
    ids = payload["patterns"][0]["person_ids"]
    ids[1] = ids[0]
    path = tmp_path / "pattern-bad.json"
    md.write_json(path, payload)

    with pytest.raises(md.PatternError) as exc:
        md.load_pattern_set(path, pool)

    assert "重複" in str(exc.value)


def test_master_data_is_reproducible_from_seed():
    first = md.build_person_pool(generated_at="2026-01-01T00:00:00+09:00")
    again = md.build_person_pool(generated_at="2026-01-01T00:00:00+09:00")
    other = md.build_person_pool(seed=999, generated_at="2026-01-01T00:00:00+09:00")

    assert first.to_dict() == again.to_dict()
    assert first.to_dict() != other.to_dict()
