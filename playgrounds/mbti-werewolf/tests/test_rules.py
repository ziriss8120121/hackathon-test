"""ルールセットの検証（設計書10章 test_rules／要件F-14、NF-11）。

ルールをコードから外へ出した目的は、ルール文書の改訂にコード変更なしで追従できる
ことである。その代わり、実装が対応していない値がJSONへ入る余地ができる。ここで
実行前に停止することを確かめる。
"""

from __future__ import annotations

import copy
import json

import pytest

from mbti_werewolf.engine import rules as rules_module


def _raw(v2_data_dir):
    path = rules_module.rule_set_path(v2_data_dir, "onenight-8p-v0.7")
    return json.loads(path.read_text(encoding="utf-8"))


def test_bundled_rule_set_loads(v2_inputs):
    _pool, _patterns, rule_set = v2_inputs

    assert rule_set.rule_set_id == "onenight-8p-v0.7"
    assert rule_set.rule_set_version == "0.7"
    assert rule_set.player_count == 8
    assert rule_set.max_response_attempts == 3
    assert rule_set.discussion_mode == "free"


def test_role_deck_matches_rule_document(v2_inputs):
    """ルール文書v0.7 §1 の「人狼2体、占い師1体、怪盗1体、村人4体」と一致する。"""

    _pool, _patterns, rule_set = v2_inputs

    assert rule_set.role_deck() == (
        "werewolf",
        "werewolf",
        "seer",
        "thief",
        "villager",
        "villager",
        "villager",
        "villager",
    )


def test_role_deck_order_is_stable(v2_inputs):
    """並びが固定されていないと、同じseedでも役職割当が一致しない。"""

    _pool, _patterns, rule_set = v2_inputs

    assert rule_set.role_deck() == rule_set.role_deck()


def test_night_phase_order_is_seer_wolf_thief(v2_inputs):
    _pool, _patterns, rule_set = v2_inputs

    assert [p.phase for p in rule_set.night_phases] == [
        "seer_inspection",
        "werewolf_recognition",
        "thief_inspection",
        "thief_swap",
    ]


@pytest.mark.parametrize(
    "label,mutate,expected",
    [
        (
            "役職構成の合計が人数と合わない",
            lambda raw: raw["role_composition"].update({"villager": 5}),
            "一致しない",
        ),
        (
            "未実装の役職",
            lambda raw: raw["role_composition"].update({"madman": 1}),
            "未実装の役職",
        ),
        (
            "未実装の夜フェーズ",
            lambda raw: raw["night_phases"].append(
                {"phase": "guard", "actor_role": "seer", "requires_inference": True}
            ),
            "未実装の夜フェーズ",
        ),
        (
            "未実装の昼フェーズ",
            lambda raw: raw["day_phases"].append("night_kill"),
            "未実装の昼フェーズ",
        ),
        (
            "固定ラウンドの議論（v0.6の方式）",
            lambda raw: raw["discussion"].update({"mode": "fixed_rounds"}),
            "未実装の議論方式",
        ),
        (
            "再投票あり",
            lambda raw: raw["vote"].update({"revote": True}),
            "再投票は未実装",
        ),
        (
            "自分への投票を認める",
            lambda raw: raw["vote"].update({"self_vote": True}),
            "自分への投票は認めない",
        ),
        (
            "未実装の追放判定",
            lambda raw: raw["vote"].update({"execute": "random_one"}),
            "未実装の追放判定",
        ),
        (
            "開始時役職での勝敗判定",
            lambda raw: raw["win_condition"].update({"basis": "initial_role"}),
            "未実装の勝敗判定基準",
        ),
        (
            "回答機会が0回",
            lambda raw: raw.update({"max_response_attempts": 0}),
            "1以上",
        ),
    ],
)
def test_invalid_rule_set_stops_before_running(v2_data_dir, label, mutate, expected):
    bad = copy.deepcopy(_raw(v2_data_dir))
    mutate(bad)

    with pytest.raises(rules_module.RuleSetError) as exc:
        rules_module.parse_rule_set(bad)

    assert expected in str(exc.value), label


def test_missing_key_is_reported(v2_data_dir):
    bad = copy.deepcopy(_raw(v2_data_dir))
    del bad["win_condition"]

    with pytest.raises(rules_module.RuleSetError) as exc:
        rules_module.parse_rule_set(bad)

    assert "win_condition" in str(exc.value)
