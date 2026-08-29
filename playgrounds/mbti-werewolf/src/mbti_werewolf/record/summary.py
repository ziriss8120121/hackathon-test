"""ケースの要約Markdown（設計書6.10）。

会話は載せない。`transcript.md` が全文を持っているため、同じ内容を2つのファイルへ
置くと、片方だけ直したときに食い違う。

`transcript.md` と役割が分かれる点が1つある。`transcript.md` は先行実験の結果文書と
形式を揃えるためMBTIを書かないが、こちらは書く。どのMBTI条件のケースだったかを人が
確認する場所が必要であり、それがこのファイルである（6.10）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from ..engine.roles import role_label
from .case_metrics import SUSPECT_UNKNOWN, case_metrics, player_metrics

_GENDER_LABELS = {"male": "男性", "female": "女性"}

UNKNOWN_TEXT = "判断不能"
MISSING_TEXT = "—"


def _upper(player_id: Optional[str]) -> str:
    return player_id.upper() if player_id else ""


def _suspect_text(suspect: Optional[str]) -> str:
    """`"unknown"`（本人が判断できないと答えた）と欠損（応答が得られなかった）を
    別の文言にする。混ぜると、判断しなかったことと記録できなかったことが読み分け
    られなくなる（9.1）。
    """

    if suspect is None:
        return MISSING_TEXT
    if suspect == SUSPECT_UNKNOWN:
        return UNKNOWN_TEXT
    return _upper(suspect)


def _number(value: Any, suffix: str = "") -> str:
    if value is None:
        return MISSING_TEXT
    return "{0}{1}".format(value, suffix)


def _signed(value: Optional[int]) -> str:
    if value is None:
        return MISSING_TEXT
    if value == 0:
        return "±0"
    return "{0:+d}".format(value)


def _flag_text(value: Optional[int]) -> str:
    if value is None:
        return MISSING_TEXT
    return "○" if value else "×"


def render_summary(case_log: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("# ケース要約 {0}".format(case_log["case_id"]))
    lines.append("")
    lines.extend(_overview(case_log))
    lines.extend(_players(case_log))
    lines.extend(_answers(case_log))
    lines.extend(_metrics(case_log))
    lines.extend(_conditions(case_log))
    return "\n".join(lines).rstrip() + "\n"


def _overview(case_log: Dict[str, Any]) -> List[str]:
    result = case_log["result"]
    composition = case_log["composition"]
    if composition == "mixed":
        composition_text = "混合構成（人物プールのMBTIをそのまま使用）"
    else:
        composition_text = "同質構成（8人全員が {0}）".format(case_log["homogeneous_type"])

    lines = [
        "## 概要",
        "",
        "- 構成種別: {0}".format(composition_text),
        "- 状態: {0}".format(case_log["status"]),
    ]

    if not result["valid"]:
        lines.append("- 結果: 無効試合（{0}）".format(result["invalid_reason"]))
    else:
        winner = "村人陣営" if result["winner"] == "village" else "人狼陣営"
        executed = (
            "、".join(_upper(pid) for pid in result["executed"])
            if result["executed"]
            else "なし"
        )
        lines.append("- 勝敗: {0}の勝利".format(winner))
        lines.append("- 追放者: {0}".format(executed))
    lines.append("")
    return lines


def _players(case_log: Dict[str, Any]) -> List[str]:
    lines = [
        "## 参加者",
        "",
        "| ID | 人物 | MBTI | 年齢 | 性別 | 開始時役職 | 最終役職 | 発言 | 見送り |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    rows = {row["player_id"]: row for row in player_metrics(case_log)}
    for player in case_log["players"]:
        row = rows[player["player_id"]]
        lines.append(
            "| {0} | {1} | {2} | {3} | {4} | {5} | {6} | {7}回 | {8}回 |".format(
                _upper(player["player_id"]),
                player["person_id"],
                player["mbti"],
                player["age"],
                _GENDER_LABELS.get(player["gender"], player["gender"]),
                role_label(player["initial_role"]),
                role_label(player["final_role"]),
                row["speech_count"],
                row["pass_count"],
            )
        )
    lines.append("")
    return lines


def _answers(case_log: Dict[str, Any]) -> List[str]:
    """議論前と投票前の個別判断を1つの表で対比する（設計書6.10）。

    2つの時点を別の表にすると、誰の判断がどう変わったかを目で追う作業が発生する。
    判断の変化そのものが仮説H2の観察対象なので、横に並べる。
    """

    lines = [
        "## 個別判断の変化（議論前 → 投票前）",
        "",
        "| ID | 議論前の疑い | 自信 | 投票前の疑い | 自信 | 自信の変化 | 投票予定 | 実際の投票 | 正答 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in player_metrics(case_log):
        lines.append(
            "| {0} | {1} | {2} | {3} | {4} | {5} | {6} | {7} | {8} |".format(
                _upper(row["player_id"]),
                _suspect_text(row["pre_suspect"]),
                _number(row["pre_confidence"]),
                _suspect_text(row["final_suspect"]),
                _number(row["final_confidence"]),
                _signed(row["confidence_delta"]),
                _suspect_text(row["planned_vote"]),
                "（棄権）" if row["abstained"] else _upper(row["actual_vote"]),
                _flag_text(row["vote_correct"]),
            )
        )
    lines.append("")
    lines.append(
        "「正答」は投票先の最終役職が人狼だったかを示す。棄権と応答なしは {0} にする。".format(
            MISSING_TEXT
        )
    )
    lines.append("")
    return lines


def _metrics(case_log: Dict[str, Any]) -> List[str]:
    metrics = case_metrics(case_log)
    lines = [
        "## 指標",
        "",
        "| 指標 | 値 | 意味 |",
        "| --- | --- | --- |",
    ]
    for key, label, suffix in _METRIC_ROWS:
        lines.append(
            "| `{0}` | {1} | {2} |".format(key, _number(metrics[key], suffix), label)
        )
    lines.append("")
    lines.append(
        "`final_entropy` と `convergence_round` は公開スタンス系列が必要なため、"
        "Judgeを実行するまで {0} のままである（設計書6.9）。".format(MISSING_TEXT)
    )
    lines.append("")
    return lines


#: 表に出す指標と、非エンジニアが読める説明。設計書9.1〜9.3の定義に対応する。
_METRIC_ROWS = (
    ("village_correct", "追放者に人狼が含まれたか（1で村人陣営の的中）", ""),
    ("village_vote_accuracy", "人狼以外6人の投票が人狼へ向いた割合", ""),
    ("vote_concentration", "最多得票数 ÷ 有効票数。1に近いほど票が集まった", ""),
    ("final_entropy", "最終発言時点の疑念の散らばり。0が集中、1が分散", ""),
    ("convergence_round", "疑いが最終的な最多得票者へ固定した最初のラウンド", ""),
    ("correction_rate", "議論前に誤っていた人のうち投票前に正した割合", ""),
    ("deterioration_rate", "議論前に正しかった人のうち投票前に誤った割合", ""),
    ("mean_confidence_delta", "自信度の平均変化（投票前 − 議論前）", ""),
    ("plan_vote_mismatch_rate", "投票予定と実際の投票がずれた割合", ""),
    ("pass_rate", "見送り ÷ 問い合わせ。沈黙の量", ""),
    ("speech_count_gini", "発言回数の偏り。0が均等、1に近いほど1人へ集中", ""),
    ("decided_from_unknown_count", "議論前に判断不能だった人が投票前に決めた件数", "人"),
    ("rounds", "議論のラウンド数", ""),
    ("total_speeches", "公開発言の件数", "件"),
    ("total_chars", "公開発言の合計文字数", "字"),
)


def _conditions(case_log: Dict[str, Any]) -> List[str]:
    versions = case_log["versions"]
    config = case_log["config"]
    brain = case_log["brain"]
    timing = case_log["timing"]
    limits = case_log["discussion"]["limits"]

    lines = [
        "## 実行条件",
        "",
        "| 項目 | 値 |",
        "| --- | --- |",
        "| ルールセット | `{0}` v{1} |".format(
            versions["rule_set_id"], versions["rule_set_version"]
        ),
        "| 人格プロンプト版 | `{0}` |".format(versions["persona_prompt_version"]),
        "| Judge評価基準版 | `{0}` |".format(versions["judge_criteria_version"]),
        "| 指標版 | `{0}`（確定日 {1}） |".format(
            config["indicator_version"], config["indicator_frozen_at"] or "未確定"
        ),
        "| 人物プール / パターン | `{0}` / `{1}` |".format(
            versions["pool_id"], versions["pattern_id"]
        ),
        "| Trial / seed | {0} / `{1}` |".format(
            config["trial_index"], config["trial_seed"]
        ),
        "| 使用モデル | {0}（{1}） |".format(
            brain.get("model") or MISSING_TEXT, brain.get("provider")
        ),
        "| 議論の上限 | max_rounds={0}、max_speeches={1}、max_total_chars={2}、max_speech_chars={3}、max_consecutive_speeches={4} |".format(
            limits["max_rounds"],
            limits["max_speeches"],
            limits["max_total_chars"],
            limits["max_speech_chars"],
            limits["max_consecutive_speeches"],
        ),
        "| 実行時間 | {0}秒（うちAI待機 {1}秒） |".format(
            timing["elapsed_seconds"], timing["ai_wait_seconds"]
        ),
        "| 推論呼び出し | {0}回 |".format(timing["inference_calls"]),
        "| 実行機 | {0} |".format(timing["machine_name"]),
        "",
    ]

    if case_log.get("failure"):
        failure = case_log["failure"]
        lines.extend(
            [
                "## 失敗の記録",
                "",
                "- 種別: {0}".format(failure.get("kind")),
                "- 内容: {0}".format(failure.get("message")),
                "- 試行回数: {0}".format(case_log.get("attempt")),
                "",
            ]
        )

    lines.append(
        "会話全文は同じディレクトリの `transcript.md` にある。生データは `case_log.json`。"
    )
    lines.append("")
    return lines


def write_summary(path: Path, case_log: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_summary(case_log), encoding="utf-8")
