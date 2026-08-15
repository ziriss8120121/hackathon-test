"""心理機能からMBTI候補が出ること、結果カードに載ることを確認する。"""

from __future__ import annotations

import random

from mbti_werewolf.agents.functions import FUNCTION_CODES
from mbti_werewolf.agents.mbti_types import (
    DEFAULT_MBTI_TYPES,
    DISPLAY_NAMES,
    TYPE_STACKS,
    mbti_candidates_text,
    types_for_dominant,
    winning_mbti_text,
)
from mbti_werewolf.config import PROMPT_VERSION
from mbti_werewolf.engine.roles import build_players
from mbti_werewolf.record.result_view import render_result_html
from mbti_werewolf.record.summary import render_summary
from mbti_werewolf.record.timeline import render_timeline
from mbti_werewolf.runner import Runner

from conftest import read_json


def test_confluence_table_covers_16_types_and_8_dominants():
    assert len(TYPE_STACKS) == 16
    assert set(TYPE_STACKS) == {
        "ISTJ",
        "ISFJ",
        "INFJ",
        "INTJ",
        "ISTP",
        "ISFP",
        "INFP",
        "INTP",
        "ESTP",
        "ESFP",
        "ENFP",
        "ENTP",
        "ESTJ",
        "ESFJ",
        "ENFJ",
        "ENTJ",
    }
    for code in FUNCTION_CODES:
        types = types_for_dominant(code)
        assert len(types) == 2, "{} の主機能候補は2タイプである".format(code)
        assert all(TYPE_STACKS[name][0] == code for name in types)


def test_fe_maps_to_esfj_and_enfj():
    assert types_for_dominant("Fe") == ["ESFJ", "ENFJ"]
    assert mbti_candidates_text("Fe") == "ESFJ / ENFJ"


def test_entp_stack_matches_requirements_example():
    assert TYPE_STACKS["ENTP"] == ("Ne", "Ti", "Fe", "Si")
    assert TYPE_STACKS["INFP"] == ("Fi", "Ne", "Si", "Te")


def test_winning_mbti_uses_winning_team_only():
    players = [
        {"player_id": "p1", "function": "Ne", "role": "villager"},
        {"player_id": "p2", "function": "Ti", "role": "villager"},
        {"player_id": "p3", "function": "Fe", "role": "werewolf"},
        {"player_id": "p4", "function": "Si", "role": "villager"},
    ]
    assert winning_mbti_text(players, "werewolf") == "p3（Fe）→ ESFJ / ENFJ"
    village = winning_mbti_text(players, "village")
    assert "p3" not in village
    assert "ENFP / ENTP" in village
    assert winning_mbti_text(players, None) == "（決着していません）"


def test_summary_and_html_show_winner_mbti(tmp_path, make_config):
    """既定のMVPロースター（v1改善）ではMBTIタイプが確定して表示されること。"""
    runner = Runner(tmp_path)
    series_id, _ = runner.run_series(make_config())
    log = read_json(tmp_path / series_id / "r001" / "run_log.json")
    summary = (tmp_path / series_id / "r001" / "summary.md").read_text(encoding="utf-8")
    html = (tmp_path / series_id / "r001" / "result.html").read_text(encoding="utf-8")
    series = (tmp_path / series_id / "series_summary.md").read_text(encoding="utf-8")

    winner_role = "werewolf" if log["result"]["winner"] == "werewolf" else "villager"
    winner = next(p for p in log["players"] if p["role"] == winner_role)
    expected = "{}（{}）".format(winner["mbti_type"], winner["display_name"])

    assert "| 勝ったMBTI |" in summary
    assert "| 人狼だったMBTI |" in summary
    assert expected in summary
    assert all(entry.get("mbti_type") for entry in log["metrics"]["per_player"])

    assert "勝ったMBTI" in html
    assert '"mbti_type": "{}"'.format(winner["mbti_type"]) in html

    assert "勝ったMBTI" in series
    assert "MBTI候補" in series


def test_default_roster_resolves_mvp_identity(make_config):
    """CLAUDE.mdの4人MVP（討論者/擁護者/仲介者/幹部）がそのまま割り当てられること。"""
    config = make_config(brain={"provider": "stub"})
    assert config.mbti_types == DEFAULT_MBTI_TYPES

    players = build_players(config, random.Random(config.seed), PROMPT_VERSION)
    assert [p.mbti_type for p in players] == DEFAULT_MBTI_TYPES
    assert [p.display_name for p in players] == [DISPLAY_NAMES[t] for t in DEFAULT_MBTI_TYPES]
    for player, mbti_type in zip(players, DEFAULT_MBTI_TYPES):
        assert player.function_stack == TYPE_STACKS[mbti_type]
        assert player.function == TYPE_STACKS[mbti_type][0]


def test_legacy_functions_override_falls_back_without_mbti_type(make_config):
    """--functions を直接指定する旧来の使い方は、MBTIタイプ紐付けなしで今までどおり動くこと。

    mbti_types は既定のまま（4件）なので、player_count=8 に広げると
    5人目以降はそもそも対応が無く、1〜4人目も主機能が食い違えば
    紐付けられない（黙って mbti_type=None のまま＝旧仕様の表示にフォールバックする）。
    """
    config = make_config(
        player_count=8,
        functions=["Ne", "Ti", "Fe", "Si", "Ni", "Se", "Te", "Fi"],
        role_composition={"werewolf": 2, "villager": 6},
        brain={"provider": "stub"},
    )
    players = build_players(config, random.Random(config.seed), PROMPT_VERSION)

    assert len(players) == 8
    # p1 は Ne が既定mbti_typesの先頭(ENTP)の主機能と偶然一致するため紐付く。
    assert players[0].mbti_type == "ENTP"
    # それ以外は主機能が食い違う、またはmbti_typesの範囲外のため紐付かない。
    assert all(p.mbti_type is None for p in players[1:])
    assert [p.function for p in players] == [
        "Ne", "Ti", "Fe", "Si", "Ni", "Se", "Te", "Fi",
    ]


def test_old_run_log_without_mbti_fields_still_renders():
    """mbti_type等のキーを持たない旧形式のrun_logでも壊れずに表示できること。"""
    old_style_run_log = {
        "schema_version": "1",
        "run_id": "s-legacy-r001",
        "series_id": "s-legacy",
        "run_index": 1,
        "status": "done",
        "phase": "finished",
        "config": {
            "player_count": 4,
            "turn_count": 3,
            "seed": 42,
            "base_seed": 42,
            "role_assignment_mode": "seeded_random",
            "functions": ["Ne", "Ti", "Fe", "Si"],
            "history_mode": "none",
        },
        "brain": {"provider": "stub", "model": "", "endpoint_kind": "stub"},
        "players": [
            {"player_id": "p1", "function": "Ne", "role": "villager", "agent_prompt_version": "v1"},
            {"player_id": "p2", "function": "Ti", "role": "villager", "agent_prompt_version": "v1"},
            {"player_id": "p3", "function": "Fe", "role": "werewolf", "agent_prompt_version": "v1"},
            {"player_id": "p4", "function": "Si", "role": "villager", "agent_prompt_version": "v1"},
        ],
        "speaking_order": ["p1", "p2", "p3", "p4"],
        "turns": [],
        "votes": [],
        "result": {
            "executed": "p3",
            "executed_role": "werewolf",
            "executed_function": "Fe",
            "winner": "village",
            "vote_counts": {"p3": 4},
            "tie_break": None,
        },
        "metrics": {
            "per_player": [
                {
                    "player_id": pid,
                    "function": fn,
                    "mbti_types": mbti_candidates_text(fn),
                    "role": role,
                    "speech_count": 0,
                    "avg_chars": 0.0,
                    "final_vote": "",
                    "win": None,
                    "suspicion_count": 0,
                    "suspected_by_count": 0,
                    "question_count": 0,
                    "rebuttal_count": 0,
                    "agreement_count": 0,
                    "hypothesis_count": 0,
                }
                for pid, fn, role in (
                    ("p1", "Ne", "villager"),
                    ("p2", "Ti", "villager"),
                    ("p3", "Fe", "werewolf"),
                    ("p4", "Si", "villager"),
                )
            ]
        },
        "timing": {"started_at": "", "ended_at": "", "elapsed_seconds": 0, "ai_wait_seconds": 0, "machine_name": ""},
        "failure": None,
    }

    summary = render_summary(old_style_run_log)
    timeline = render_timeline(old_style_run_log)
    html = render_result_html(old_style_run_log)

    # MBTIタイプ未確定のため、旧仕様の候補2タイプ表示にフォールバックする。
    assert "ESFJ / ENFJ" in summary
    assert "ESFJ / ENFJ" in timeline
    assert "勝ったMBTI" in summary
    assert "MBTI人狼 実行結果" in html
