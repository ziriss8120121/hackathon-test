"""心理機能からMBTI候補が出ること、結果カードに載ることを確認する。"""

from __future__ import annotations

from mbti_werewolf.agents.functions import FUNCTION_CODES
from mbti_werewolf.agents.mbti_types import (
    TYPE_STACKS,
    mbti_candidates_text,
    types_for_dominant,
    winning_mbti_text,
)
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
    runner = Runner(tmp_path)
    series_id, _ = runner.run_series(make_config())
    log = read_json(tmp_path / series_id / "r001" / "run_log.json")
    summary = (tmp_path / series_id / "r001" / "summary.md").read_text(encoding="utf-8")
    html = (tmp_path / series_id / "r001" / "result.html").read_text(encoding="utf-8")
    series = (tmp_path / series_id / "series_summary.md").read_text(encoding="utf-8")

    assert "| 勝ったMBTI |" in summary
    assert "| 人狼だったMBTI |" in summary
    assert "ESFJ / ENFJ" in summary
    assert "ENFP / ENTP" in summary
    assert all(entry.get("mbti_types") for entry in log["metrics"]["per_player"])

    assert "勝ったMBTI" in html
    assert '"Fe": ["ESFJ", "ENFJ"]' in html or '"Fe":["ESFJ","ENFJ"]' in html

    assert "勝ったMBTI" in series
    assert "MBTI候補" in series
