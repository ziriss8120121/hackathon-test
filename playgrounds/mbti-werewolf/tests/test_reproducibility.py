"""同一設定・同一seedで割当と進行順序が再現されることを確認する。

対応要件: F-21、F-22、NF-05、AC-09

Stubで実行する。実際のLLMは同じseedでも出力が揺れるため、再現性の対象は
割当と進行順序に限る（要件NF-05の「脳の出力揺れは許容する」に対応）。
"""

from __future__ import annotations

from mbti_werewolf.runner import Runner

from conftest import read_json


def _run(tmp_path, config, name):
    runner = Runner(tmp_path / name)
    series_id, _ = runner.run_series(config)
    return read_json(tmp_path / name / series_id / "r001" / "run_log.json")


def test_same_seed_reproduces_assignment_and_order(tmp_path, make_config):
    config = make_config(seed=1234)

    first = _run(tmp_path, config, "a")
    second = _run(tmp_path, config, "b")

    # 心理機能の割当、役職の割当（F-22）
    assert first["players"] == second["players"]
    # 発言順（設計書4.4）
    assert first["speaking_order"] == second["speaking_order"]
    # 進行順序と投票先
    assert [(t["turn"], t["player_id"]) for t in first["turns"]] == [
        (t["turn"], t["player_id"]) for t in second["turns"]
    ]
    assert [v["target"] for v in first["votes"]] == [v["target"] for v in second["votes"]]
    assert first["result"]["executed"] == second["result"]["executed"]
    assert first["result"]["winner"] == second["result"]["winner"]


def test_seed_is_recorded(tmp_path, make_config):
    config = make_config(seed=777)
    log = _run(tmp_path, config, "c")

    assert log["config"]["seed"] == 777
    assert log["config"]["base_seed"] == 777
    assert log["config"]["role_assignment_mode"] == "seeded_random"


def test_different_seed_changes_assignment(tmp_path, make_config):
    """seedを変えれば心理機能と役職の組み合わせが動くこと（設計書4.4の狙い）。"""
    roles_by_seed = set()
    for seed in range(1, 12):
        log = _run(tmp_path, make_config(seed=seed), "seed-{}".format(seed))
        werewolf = next(p["function"] for p in log["players"] if p["role"] == "werewolf")
        roles_by_seed.add(werewolf)

    assert len(roles_by_seed) > 1, "seedを変えても人狼の心理機能が固定されている"
