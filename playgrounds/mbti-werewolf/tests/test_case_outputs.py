"""M3の出力（`summary.md`、`result.html`、集計CSV）の形（設計書6.9、6.10、7.5）。

出力の形を先に固定しておく。1,700ケースを実行した後に列や見出しを変えると、
実行済みの出力と新しい出力が混ざり、分析側で読み分けられなくなる。
"""

from __future__ import annotations

import csv
import io
from html.parser import HTMLParser

from mbti_werewolf.record.case_result_view import (
    render_failure_html,
    render_latest_redirect,
    render_result_html,
)
from mbti_werewolf.record.case_metrics import JUDGE_DEPENDENT
from mbti_werewolf.record.case_summary import render_summary
from mbti_werewolf.record.metrics_csv import (
    EXPERIMENT_COLUMNS,
    TRIAL_COLUMNS,
    experiment_rows,
    trial_rows,
)


class _Nesting(HTMLParser):
    """開いたタグがすべて閉じているかだけを見る。"""

    VOID = {"meta", "br", "hr", "img", "input", "link"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.errors = []

    def handle_starttag(self, tag, attrs):
        if tag not in self.VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag in self.VOID:
            return
        if not self.stack:
            self.errors.append("閉じタグが余っている: {0}".format(tag))
        elif self.stack[-1] != tag:
            self.errors.append(
                "入れ子の不一致: {0} を閉じようとしたが {1} が開いている".format(tag, self.stack[-1])
            )
        else:
            self.stack.pop()

    def problems(self):
        remaining = ["閉じられていない: {0}".format(t) for t in self.stack]
        return self.errors + remaining


# --- summary.md -------------------------------------------------------------


def test_summary_has_the_documented_sections(case_log):
    log, _outcome, _brain = case_log()
    text = render_summary(log)

    order = ["## 概要", "## 参加者", "## 個別判断の変化", "## 指標", "## 実行条件"]
    positions = [text.index(heading) for heading in order]
    assert positions == sorted(positions)


def test_summary_does_not_repeat_the_conversation(case_log):
    """会話は `transcript.md` が持つ。2つのファイルへ置くと片方だけ古くなる（6.10）。"""

    log, _outcome, _brain = case_log()
    text = render_summary(log)

    spoken = [
        event["speech_text"]
        for event in log["discussion"]["events"]
        if event["spoke"] and event.get("speech_text")
    ]
    assert spoken, "この検査には発言が1件以上必要"
    for speech in spoken:
        assert speech not in text
    assert "公開議論" not in text


def test_summary_shows_mbti_unlike_the_transcript(case_log):
    """MBTIを人が確認する場所はこのファイルである（6.10）。"""

    log, _outcome, _brain = case_log()
    text = render_summary(log)

    for player in log["players"]:
        assert player["mbti"] in text


def test_summary_separates_unknown_from_a_missing_answer(case_log):
    log, _outcome, _brain = case_log()
    log["pre_discussion_answers"][0]["suspect"] = "unknown"
    log["pre_vote_answers"][1]["suspect"] = None

    text = render_summary(log)
    assert "判断不能" in text
    assert "—" in text


def test_summary_marks_judge_dependent_metrics_as_pending(case_log):
    log, _outcome, _brain = case_log()
    text = render_summary(log)

    assert "`final_entropy`" in text
    assert "`convergence_round`" in text
    assert "Judgeを実行するまで" in text


def test_summary_records_what_is_needed_to_reproduce(case_log):
    log, _outcome, _brain = case_log()
    text = render_summary(log)

    assert str(log["config"]["trial_seed"]) in text
    assert log["versions"]["rule_set_id"] in text
    assert log["versions"]["persona_prompt_version"] in text
    assert log["config"]["indicator_version"] in text


def test_summary_states_an_invalid_game_instead_of_a_winner(case_log):
    log, _outcome, _brain = case_log()
    log["result"]["valid"] = False
    log["result"]["invalid_reason"] = "no_valid_votes"

    text = render_summary(log)
    assert "無効試合" in text
    assert "の勝利" not in text


def test_summary_table_rows_hold_every_player(case_log):
    log, _outcome, _brain = case_log()
    text = render_summary(log)

    roster = text.split("## 参加者", 1)[1].split("##", 1)[0]
    rows = [line for line in roster.splitlines() if line.startswith("| P")]
    assert len(rows) == 8


# --- 集計CSV ---------------------------------------------------------------


def test_trial_csv_has_one_row_per_player(case_log):
    log, _outcome, _brain = case_log()
    rows = trial_rows([log])

    assert len(rows) == 8
    assert all(set(row) == set(TRIAL_COLUMNS) for row in rows)


def test_experiment_csv_has_one_row_per_case(case_log):
    log, _outcome, _brain = case_log()
    rows = experiment_rows([log, log])

    assert len(rows) == 2
    assert all(set(row) == set(EXPERIMENT_COLUMNS) for row in rows)


def test_csv_columns_documented_in_the_design_come_first():
    """列は末尾へ足す決まりなので、先頭側の並びが変わっていないことを見る（6.9）。"""

    assert TRIAL_COLUMNS[:12] == (
        "experiment_id",
        "trial_id",
        "case_id",
        "composition",
        "homogeneous_type",
        "player_id",
        "person_id",
        "age",
        "gender",
        "mbti",
        "initial_role",
        "final_role",
    )
    assert EXPERIMENT_COLUMNS[:9] == (
        "experiment_id",
        "trial_id",
        "case_id",
        "case_index",
        "composition",
        "homogeneous_type",
        "status",
        "valid",
        "invalid_reason",
    )


def test_judge_dependent_columns_are_empty_not_zero(case_log):
    """空欄は未算出、`0` は完全な集中を意味する。混ぜると読み方を誤る（6.9）。"""

    log, _outcome, _brain = case_log()
    row = experiment_rows([log])[0]

    assert JUDGE_DEPENDENT == ("final_entropy", "convergence_round")
    for column in JUDGE_DEPENDENT:
        assert row[column] == ""


def test_every_other_experiment_column_has_a_value(case_log):
    """Judge待ちの2列以外が空欄なら、算出漏れか記録漏れである。"""

    log, _outcome, _brain = case_log()
    row = experiment_rows([log])[0]

    # 状況によって空欄が正しい列。無効試合の理由、追放者なし、など。
    allowed_empty = {
        "homogeneous_type",
        "invalid_reason",
        "no_execution_reason",
        "correction_rate",
        "deterioration_rate",
    }
    empty = {
        key
        for key, value in row.items()
        if value == "" and key not in JUDGE_DEPENDENT and key not in allowed_empty
    }
    assert empty == set()


def test_multi_value_cells_use_a_pipe_not_a_comma(case_log):
    """カンマを使うと表計算ソフトで開いたときに列がずれる（6.9）。"""

    log, _outcome, _brain = case_log()
    log["result"]["executed"] = ["p2", "p5"]
    log["result"]["executed_roles"] = [
        {"player_id": "p2", "initial_role": "werewolf", "final_role": "werewolf"},
        {"player_id": "p5", "initial_role": "villager", "final_role": "villager"},
    ]

    row = experiment_rows([log])[0]
    assert row["executed"] == "p2|p5"
    assert row["executed_final_roles"] == "werewolf|villager"
    assert "," not in row["executed"]


def test_no_execution_leaves_the_cell_empty_with_a_zero_count(case_log):
    log, _outcome, _brain = case_log()
    log["result"]["executed"] = []
    log["result"]["executed_roles"] = []

    row = experiment_rows([log])[0]
    assert row["executed"] == ""
    assert row["executed_count"] == "0"


def test_booleans_are_written_as_words(case_log):
    log, _outcome, _brain = case_log()
    row = experiment_rows([log])[0]

    assert row["valid"] in ("true", "false")


def test_csv_round_trips_through_a_reader(case_log):
    """書いたCSVを読み直して列数が崩れていないことを見る。"""

    log, _outcome, _brain = case_log()
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(EXPERIMENT_COLUMNS))
    writer.writeheader()
    for row in experiment_rows([log]):
        writer.writerow(row)

    buffer.seek(0)
    parsed = list(csv.DictReader(buffer))
    assert len(parsed) == 1
    assert parsed[0]["case_id"] == log["case_id"]
    assert len(parsed[0]) == len(EXPERIMENT_COLUMNS)


# --- result.html ------------------------------------------------------------


def test_result_html_is_well_nested(case_log):
    log, _outcome, _brain = case_log()
    checker = _Nesting()
    checker.feed(render_result_html(log))

    assert checker.problems() == []


def test_result_html_is_self_contained(case_log):
    """`file://` で開くため、外部のCSSやスクリプトを読まない（7.5）。"""

    log, _outcome, _brain = case_log()
    html_text = render_result_html(log)

    assert "<style>" in html_text
    assert "<script" not in html_text
    assert "http://" not in html_text
    assert "https://" not in html_text


def test_result_html_has_a_viewport_for_phones(case_log):
    log, _outcome, _brain = case_log()
    assert 'name="viewport"' in render_result_html(log)


def test_wide_tables_carry_the_labels_needed_to_stack_on_a_phone(case_log):
    """狭い画面ではCSSが `data-label` から項目名を出す。

    属性が欠けると、折り返したときに値だけが並んで何の項目か分からなくなる。
    """

    log, _outcome, _brain = case_log()
    html_text = render_result_html(log)

    assert "max-width: 640px" in html_text
    assert 'data-label="public memo"' not in html_text
    for label in ("ID", "公開発言", "memo", "投票先", "MBTI", "最終役職"):
        assert 'data-label="{0}"'.format(label) in html_text


def test_stacking_applies_to_every_table_with_many_columns(case_log):
    """3列以上の表はすべて折り返しの対象にする。1つ漏れると横スクロールが残る。"""

    log, _outcome, _brain = case_log()
    html_text = render_result_html(log)

    plain = html_text.count("<table>")
    assert plain == 0, "stack が付いていない表が {0} 個ある".format(plain)


def test_result_html_holds_every_section(case_log):
    log, _outcome, _brain = case_log()
    html_text = render_result_html(log)

    for anchor in (
        "sec-result",
        "sec-roster",
        "sec-night",
        "sec-discussion",
        "sec-votes",
        "sec-answers",
        "sec-metrics",
        "sec-conditions",
    ):
        assert 'id="{0}"'.format(anchor) in html_text


def test_result_html_shows_the_memo_next_to_each_speech(case_log):
    log, _outcome, _brain = case_log()
    html_text = render_result_html(log)

    memos = [
        event["memo"]
        for event in log["discussion"]["events"]
        if event["spoke"] and event.get("memo")
    ]
    assert memos, "この検査にはmemo付きの発言が1件以上必要"
    assert "private memo" in html_text


def test_result_html_escapes_markup_in_speeches(case_log):
    """発言はモデルの出力なので、そのまま埋めるとHTMLが壊れる。"""

    log, _outcome, _brain = case_log()
    spoken = next(e for e in log["discussion"]["events"] if e["spoke"])
    spoken["speech_text"] = '<script>alert("x")</script> & <b>太字</b>'

    html_text = render_result_html(log)
    assert "<script>" not in html_text
    assert "&lt;script&gt;" in html_text
    assert "&amp;" in html_text


def test_result_html_uses_uppercase_player_ids(case_log):
    log, _outcome, _brain = case_log()
    html_text = render_result_html(log)

    assert ">P1<" in html_text


def test_result_html_words_pass_and_skip_differently(case_log):
    log, _outcome, _brain = case_log()
    events = log["discussion"]["events"]
    events[0].update({"spoke": False, "skipped": False, "speech_text": ""})
    events[1].update({"spoke": False, "skipped": True, "speech_text": ""})

    html_text = render_result_html(log)
    assert "（見送り）" in html_text
    assert "（応答が得られず記録なし）" in html_text


def test_result_html_states_an_invalid_game(case_log):
    log, _outcome, _brain = case_log()
    log["result"]["valid"] = False

    html_text = render_result_html(log)
    assert "無効試合" in html_text
    assert "陣営の勝利" not in html_text


def test_result_html_links_to_the_neighbouring_files(case_log):
    log, _outcome, _brain = case_log()
    html_text = render_result_html(log)

    assert './transcript.md' in html_text
    assert './summary.md' in html_text
    assert './case_log.json' in html_text


def test_night_wording_matches_the_transcript(case_log):
    """同じ夜処理を2つの言い方で書かない。文言は1か所で組み立てる。"""

    from mbti_werewolf.record.transcript import night_steps

    log, _outcome, _brain = case_log()
    html_text = render_result_html(log)

    for step in night_steps(log):
        # HTMLは属性用に引用符を実体参照へ変える。比較のため戻す。
        assert step.replace('"', "&quot;").replace("'", "&#x27;") in html_text


def test_failure_html_explains_how_to_retry():
    html_text = render_failure_html(
        "e-1-t001-c00", "mixed", None, {"kind": "timeout", "message": "遅い"}, 2
    )

    assert "失敗" in html_text
    assert "timeout" in html_text
    assert "--resume" in html_text
    checker = _Nesting()
    checker.feed(html_text)
    assert checker.problems() == []


def test_failure_html_names_the_homogeneous_type():
    html_text = render_failure_html(
        "e-1-t001-c01", "homogeneous", "ISTJ", {"kind": "internal", "message": "x"}, 1
    )
    assert "ISTJ" in html_text


# --- latest.html ------------------------------------------------------------


def test_latest_redirect_keeps_a_manual_link():
    """メタリフレッシュに対応しないアプリ内ブラウザでも辿れるようにする（7.6）。"""

    html_text = render_latest_redirect("e-1-t001-c00", "e-1/t001/c00-mixed/result.html")

    assert 'http-equiv="refresh"' in html_text
    assert 'href="./e-1/t001/c00-mixed/result.html"' in html_text
    assert "こちらをタップ" in html_text


def test_latest_redirect_uses_a_relative_path():
    """`file://` とGitHub Pagesの両方で同じように動くのは相対パスだけ。"""

    html_text = render_latest_redirect("e-1-t001-c00", "e-1/t001/c00-mixed/result.html")

    assert "url=./e-1/t001/c00-mixed/result.html" in html_text
    assert "http://" not in html_text
    assert "https://" not in html_text
