"""夜の役職処理（設計書10章 test_night／要件F-15、4.2、4.7）。"""

from __future__ import annotations

import json

from v2_support import default_responder


def _night_by_phase(outcome, phase):
    return [a for a in outcome.night_actions if a["phase"] == phase]


def test_night_runs_in_seer_wolf_thief_order(run_case):
    outcome, _brain, _case, _trial, _config, _rules = run_case()

    phases = [a["phase"] for a in outcome.night_actions]
    assert phases.index("seer_inspection") < phases.index("werewolf_recognition")
    assert phases.index("werewolf_recognition") < phases.index("thief_inspection")
    assert phases.index("thief_inspection") < phases.index("thief_swap")


def test_seer_sees_initial_role_of_target(run_case):
    outcome, _brain, _case, _trial, _config, _rules = run_case()

    action = _night_by_phase(outcome, "seer_inspection")[0]
    target = next(p for p in outcome.players if p.player_id == action["target"])
    assert action["ability_used"] is True
    assert action["revealed_initial_role"] == target.initial_role


def test_werewolves_know_each_other_without_inference(run_case):
    outcome, _brain, _case, _trial, _config, _rules = run_case()

    records = _night_by_phase(outcome, "werewolf_recognition")
    assert len(records) == 2
    for record in records:
        assert record["requires_inference"] is False
        assert len(record["partners"]) == 1
        assert record["actor"] not in record["partners"]


def test_thief_inspects_then_decides_swap(run_case):
    """怪盗は確認結果を得た後に交換を判断する2段階になる（設計書4.2）。"""

    outcome, brain, _case, _trial, _config, _rules = run_case()

    inspect = _night_by_phase(outcome, "thief_inspection")[0]
    swap = _night_by_phase(outcome, "thief_swap")[0]
    assert swap["target"] == inspect["target"]

    tags = [c["tag"] for c in brain.calls]
    assert tags.index("night_thief_inspect") < tags.index("night_thief_swap")


def test_swap_prompt_shows_revealed_role(run_case):
    outcome, brain, _case, _trial, _config, _rules = run_case()

    inspect = _night_by_phase(outcome, "thief_inspection")[0]
    swap_call = next(c for c in brain.calls if c["tag"] == "night_thief_swap")
    assert swap_call["user"].count(inspect["target"].upper()) >= 1


def test_swap_exchanges_final_roles_and_notifies_only_thief(run_case):
    def responder(tag, player_id, request, index):
        if tag == "night_thief_swap":
            return json.dumps({"swap": True, "reason": "交換する。"}, ensure_ascii=False)
        return default_responder()(tag, player_id, request, index)

    outcome, brain, _case, _trial, _config, _rules = run_case(responder)

    swap = _night_by_phase(outcome, "thief_swap")[0]
    thief = next(p for p in outcome.players if p.player_id == swap["actor"])
    target = next(p for p in outcome.players if p.player_id == swap["target"])

    assert swap["swapped"] is True
    assert thief.initial_role == "thief"
    assert thief.final_role == swap["actor_final_role"]
    assert thief.final_role != "thief"
    assert target.final_role == "thief"
    assert swap["target_notified"] is False

    # 交換された側へは交換も最終役職も通知しない（ルール文書v0.7 §1、設計書4.7）。
    for prompt in brain.prompts_for(target.player_id):
        assert "交換を実行しました" not in prompt
    # 怪盗本人へは通知する。
    thief_prompts = brain.prompts_for(thief.player_id)
    assert any("交換を実行しました" in prompt for prompt in thief_prompts)


def test_no_swap_keeps_final_roles(run_case):
    outcome, _brain, _case, _trial, _config, _rules = run_case()

    swap = _night_by_phase(outcome, "thief_swap")[0]
    assert swap["swapped"] is False
    for player in outcome.players:
        assert player.final_role == player.initial_role


def test_three_invalid_answers_mean_ability_unused(run_case):
    """3回とも無効なら能力未使用。乱数で対象を埋めない（設計書5.4）。"""

    def responder(tag, player_id, request, index):
        if tag in ("night_seer", "night_thief_inspect"):
            return "分かりません"
        return default_responder()(tag, player_id, request, index)

    outcome, _brain, _case, _trial, _config, _rules = run_case(responder)

    seer = _night_by_phase(outcome, "seer_inspection")[0]
    assert seer["ability_used"] is False
    assert seer["target"] is None
    assert seer["attempts"] == 3
    assert seer["parse_failed"] is True
    assert seer["skip_reason"] == "exhausted_attempts"

    # 確認できなかった怪盗は交換もしない。最終役職は怪盗のまま。
    swap = _night_by_phase(outcome, "thief_swap")[0]
    assert swap["swapped"] is False
    thief = next(p for p in outcome.players if p.player_id == swap["actor"])
    assert thief.final_role == "thief"


def test_self_designation_is_retried(run_case):
    """自分自身の指定は無効な回答として再送の対象になる（ルール文書v0.7 §2-2）。"""

    attempts = {"count": 0}

    def responder(tag, player_id, request, index):
        if tag == "night_seer":
            attempts["count"] += 1
            if attempts["count"] == 1:
                return json.dumps({"target": player_id.upper(), "reason": "自分。"})
        return default_responder()(tag, player_id, request, index)

    outcome, _brain, _case, _trial, _config, _rules = run_case(responder)

    seer = _night_by_phase(outcome, "seer_inspection")[0]
    assert seer["attempts"] == 2
    assert seer["ability_used"] is True
    assert seer["target"] != seer["actor"]


def test_lowercase_answer_is_accepted(run_case):
    """プロンプトはP1形式で渡すが、p1で返っても形式の誤りとしない。"""

    def responder(tag, player_id, request, index):
        if tag == "night_seer":
            return json.dumps({"target": request.choices[0].lower(), "reason": "選ぶ。"})
        return default_responder()(tag, player_id, request, index)

    outcome, _brain, _case, _trial, _config, _rules = run_case(responder)

    seer = _night_by_phase(outcome, "seer_inspection")[0]
    assert seer["attempts"] == 1
    assert seer["target"] == seer["target"].lower()
