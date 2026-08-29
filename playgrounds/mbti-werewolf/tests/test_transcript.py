"""`transcript.md` の形式（設計書6.10／要求定義書の最優先事項）。

先行実験のWORLD A / B結果文書と並べて読めることを検査する。章の順序と表の列が
ずれると、先行実験と本システムの結果を比較できなくなる。参照先の文書を読み、
見出しと表の列を実物と突き合わせる。文書側の形が変わればこのテストが落ちる。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from mbti_werewolf.record.transcript import (
    EMPTY_MEMO,
    PASS_TEXT,
    SKIP_TEXT,
    render_transcript,
    write_transcript,
)

from v2_support import default_responder

REFERENCE = (
    Path(__file__).resolve().parents[3]
    / "docs"
    / "m-plus-experiment"
    / "04_world-A-result_v1.md"
)


def _headings(text: str, level: int = 2):
    prefix = "#" * level
    return [
        line[len(prefix) + 1 :].strip()
        for line in text.splitlines()
        if line.startswith(prefix + " ") and not line.startswith(prefix + "# ")
    ]


def _tables(text: str):
    """`| a | b |` の見出し行をすべて拾う。"""

    return [
        line.strip()
        for line in text.splitlines()
        if line.startswith("|") and "---" not in line
    ]


@pytest.fixture(scope="module")
def reference_text():
    assert REFERENCE.is_file(), REFERENCE
    return REFERENCE.read_text(encoding="utf-8")


def test_section_order_matches_the_reference_document(case_log, reference_text):
    log, _outcome, _brain = case_log()
    text = render_transcript(log)

    assert _headings(text) == _headings(reference_text)


def test_discussion_round_headings_use_the_reference_wording(case_log):
    log, outcome, _brain = case_log()
    text = render_transcript(log)

    rounds = sorted({e["round"] for e in outcome.discussion.events})
    assert _headings(text, level=3) == ["第{0}ラウンド".format(r) for r in rounds]


def test_discussion_and_vote_tables_have_the_memo_column(case_log, reference_text):
    """公開発言と投票にprivate memoを横並びで載せる（設計書5.3、6.10）。"""

    log, _outcome, _brain = case_log()
    text = render_transcript(log)

    headers = {line for line in _tables(text) if "private memo" in line}
    reference_headers = {
        line for line in _tables(reference_text) if "private memo" in line
    }
    assert headers == reference_headers
    assert headers == {"| ID | 公開発言 | private memo |", "| ID | 投票先 | private memo |"}


def test_initial_role_table_matches_the_reference(case_log, reference_text):
    log, _outcome, _brain = case_log()
    text = render_transcript(log)

    assert "| ID | 開始時役職 |" in _tables(text)
    assert "| ID | 開始時役職 |" in _tables(reference_text)


def test_player_ids_are_uppercase(case_log):
    """人が読む出力ではP1〜P8にする（設計書6.10）。"""

    log, outcome, _brain = case_log()
    text = render_transcript(log)

    assert re.search(r"\bp[1-8]\b", text) is None
    for player in outcome.players:
        assert player.display_id in text


def test_mbti_is_not_written_in_the_transcript(case_log):
    """先行実験の結果文書がタイプ名を出していないため、形式を揃える（設計書6.10）。"""

    from mbti_werewolf.agents.mbti_types import TYPE_STACKS

    log, _outcome, _brain = case_log()
    text = render_transcript(log)

    for mbti in TYPE_STACKS:
        assert mbti not in text


def test_night_section_merges_thief_inspect_and_swap(case_log):
    """怪盗の確認と交換を1つの番号にまとめる（先行実験の書き方に合わせる）。"""

    log, _outcome, _brain = case_log()
    text = render_transcript(log)

    night = text.split("## 夜処理")[1].split("##")[0].strip()
    steps = [line for line in night.splitlines() if re.match(r"^\d+\. ", line)]
    assert len(steps) == 3
    assert steps[0].startswith("1. 占い師")
    assert steps[1].startswith("2. 人狼")
    assert steps[2].startswith("3. 怪盗")
    assert "を確認" in steps[2] and "選択" in steps[2]


def test_both_werewolves_appear_in_one_night_step(case_log):
    log, outcome, _brain = case_log()
    text = render_transcript(log)

    wolves = [p.display_id for p in outcome.players if p.initial_role == "werewolf"]
    assert "人狼{0}は互いを人狼仲間として確認。".format("と".join(wolves)) in text


def test_pass_stays_as_a_row(case_log):
    """見送りを表から消さない。誰が黙っていたかを読めなくなる（設計書6.10）。"""

    def responder(tag, player_id, request, index):
        if tag == "speak" and player_id == "p1":
            return json.dumps({"speak": False, "memo": "様子を見る。"}, ensure_ascii=False)
        return default_responder()(tag, player_id, request, index)

    log, _outcome, _brain = case_log(responder)
    text = render_transcript(log)

    rows = [line for line in text.splitlines() if line.startswith("| P1 |")]
    assert rows
    assert any(PASS_TEXT in row for row in rows)
    assert all("様子を見る。" in row for row in rows if PASS_TEXT in row)


def test_skip_is_worded_differently_from_pass(case_log):
    """本人が選んだ見送りと、応答が得られなかったスキップを区別する（設計書4.5）。"""

    def responder(tag, player_id, request, index):
        if tag == "speak" and player_id == "p2":
            return "うーん"
        return default_responder()(tag, player_id, request, index)

    log, _outcome, _brain = case_log(responder)
    text = render_transcript(log)

    rows = [line for line in text.splitlines() if line.startswith("| P2 |")]
    skip_rows = [row for row in rows if SKIP_TEXT in row]
    assert skip_rows
    assert all(EMPTY_MEMO in row for row in skip_rows)
    assert PASS_TEXT not in text.split("## 公開議論")[1].split("## 投票")[0].replace(
        SKIP_TEXT, ""
    )


def test_no_execution_is_stated_with_its_reason(case_log):
    log, _outcome, _brain = case_log()
    log["result"].update(
        {
            "executed": [],
            "executed_count": 0,
            "executed_roles": [],
            "no_execution_reason": "top_vote_count_is_one",
            "top_vote_count": 1,
            "winner": "werewolf",
        }
    )
    text = render_transcript(log)

    assert "- 追放者: なし（最多得票が1票のため）" in text
    assert "- 判定理由: 最多得票が1票のみで誰も追放されず" in text


def test_invalid_game_replaces_the_result_section(case_log):
    """無効試合では勝敗行を出さない（設計書6.10）。"""

    def responder(tag, player_id, request, index):
        if tag == "vote":
            return "決められない"
        return default_responder()(tag, player_id, request, index)

    log, _outcome, _brain = case_log(responder)
    text = render_transcript(log)

    result = text.split("## 結果")[1]
    assert "- 結果: 無効試合" in result
    assert "- 理由: 有効投票なし" in result
    assert "勝敗" not in result


def test_abstain_is_shown_in_the_vote_table(case_log):
    def responder(tag, player_id, request, index):
        if tag == "vote" and player_id == "p3":
            return "決められない"
        return default_responder()(tag, player_id, request, index)

    log, _outcome, _brain = case_log(responder)
    text = render_transcript(log)

    assert "| P3 | （棄権） | {0} |".format(EMPTY_MEMO) in text
    assert "- 有効票数: 7（棄権1件）" in text


def test_anomalies_are_listed_in_the_conditions_and_result(case_log):
    def responder(tag, player_id, request, index):
        if tag == "night_seer":
            return "分かりません"
        return default_responder()(tag, player_id, request, index)

    log, _outcome, _brain = case_log(responder)
    text = render_transcript(log)

    assert text.count("占い師の確認で有効な回答が得られず能力未使用") == 2
    assert "- 異常処理: なし" not in text


def test_conditions_record_what_is_needed_to_reproduce(case_log):
    log, _outcome, _brain = case_log()
    text = render_transcript(log)
    conditions = text.split("## 実行条件（固定記録）")[1].split("## 開始時役職")[0]

    for label in (
        "- ルール正本:",
        "- Agent設定正本:",
        "- 実験計画正本:",
        "- seed:",
        "- 役職配布手順:",
        "- 使用モデル:",
        "- Agent生成条件:",
        "- 参加者属性:",
        "- 夜処理順:",
        "- 異常処理:",
    ):
        assert label in conditions, label

    assert "- 夜処理順: 占い師 → 人狼 → 怪盗" in conditions
    assert "- 議論方式: 自由議論" in conditions


def test_condition_labels_match_the_reference_document(reference_text, case_log):
    """先行実験が持つ条件項目を落としていないこと。"""

    log, _outcome, _brain = case_log()
    text = render_transcript(log)

    def labels(source: str) -> set:
        block = source.split("## 実行条件（固定記録）")[1].split("## 開始時役職")[0]
        return {
            match.group(1)
            for match in re.finditer(r"^- ([^:]+):", block, re.M)
        }

    missing = labels(reference_text) - labels(text)
    # 先行実験の「発言順」「議論ラウンド数」は自由議論では事前に決まらないため、
    # 「問い合わせ順」「議論の上限」へ置き換えている（設計書0.5）。
    assert missing == {"発言順", "議論ラウンド数"}
    assert {"問い合わせ順", "議論の上限"} <= labels(text)


def test_transcript_is_written_to_disk(tmp_path, case_log):
    log, _outcome, _brain = case_log()
    path = tmp_path / "c00-mixed" / "transcript.md"

    write_transcript(path, log)

    assert path.read_text(encoding="utf-8") == render_transcript(log)
    assert path.read_text(encoding="utf-8").endswith("\n")


def test_table_cells_survive_newlines_and_pipes(case_log):
    """発言に改行や縦棒が入っても表が壊れないこと。"""

    def responder(tag, player_id, request, index):
        if tag == "speak":
            return json.dumps(
                {"speak": True, "speech": "1行目\n2行目 | 区切り", "memo": "改行入り\nmemo"},
                ensure_ascii=False,
            )
        return default_responder()(tag, player_id, request, index)

    log, _outcome, _brain = case_log(responder)
    text = render_transcript(log)

    body = text.split("## 公開議論")[1].split("## 結果")[0]
    rows = [line for line in body.splitlines() if line.startswith("| P")]
    assert rows
    for row in rows:
        assert row.count("|") == 4, row
    assert "1行目 2行目 ／ 区切り" in body
    assert "改行入り memo" in body
