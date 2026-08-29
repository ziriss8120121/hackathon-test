"""RQ1・RQ2と操作確認（設計書9.4、6.10）。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Sequence

from ..agents.mbti_types import TYPE_STACKS
from .html import fmt_number, md_table, page, table_html
from .indicators import METRIC_LABELS, RQ1_METRICS

HOMOGENEOUS_TYPES = tuple(TYPE_STACKS)

RECORDED_TYPES = (
    "ENFP",
    "ISTJ",
    "INFJ",
    "ESTP",
    "INTJ",
    "ESFJ",
    "ENTP",
    "ISFP",
)


def render_rq1_markdown(result: Dict[str, Any]) -> str:
    lines = [
        "# RQ1 混合構成と同質構成の比較",
        "",
        result["frozen_note"],
        "",
        "単位はTrialである。混合側は `c00` の値、同質側は `c01`〜`c16` の中央値をペアにする。",
        "検定はWilcoxon符号付順位検定（両側）。効果量は対応ありの順位相関 r。",
        "同質側を中央値にしたのは、1タイプの極端な値が平均を引っ張るのを避けるためである。",
        "混合側は1ケース、同質側は16ケースの中央値なので、両側の測定誤差の大きさが違う。",
        "",
        "- 有効Trial数: {0}".format(result["eligible_count"]),
        "- 除外Trial数: {0}".format(len(result["exclusions"])),
        "- 指標版: `{0}`".format(result["indicator_version"]),
        "",
        "## 除外したTrial",
        "",
        _exclusions_md(result["exclusions"]),
        "",
        "## 指標ごとの比較",
        "",
        md_table(
            ("指標", "混合 中央値", "同質 中央値", "Wilcoxon p", "効果量 r", "組数"),
            _rq1_rows(result),
        ),
        "",
        "## 根拠Trial",
        "",
        md_table(("Trial",) + tuple(METRIC_LABELS[k] for k in ("village_correct", "final_entropy", "correction_rate")),
                 _evidence_rows(result)),
        "",
    ]
    return "\n".join(lines)


def render_rq1_html(result: Dict[str, Any]) -> str:
    body = (
        '<p class="note">{0}</p>'
        "<p>単位はTrial。混合側は c00、同質側は16ケースの中央値。Wilcoxon符号付順位検定（両側）。</p>"
        "<h2>指標ごとの比較</h2>"
        "{1}"
        "<h2>除外したTrial</h2>"
        "{2}"
    ).format(
        result["frozen_note"],
        table_html(
            ("指標", "混合 中央値", "同質 中央値", "Wilcoxon p", "効果量 r", "組数"),
            _rq1_rows(result),
        ),
        table_html(
            ("Trial", "理由"),
            [(item["trial_id"], item["reason"]) for item in result["exclusions"]]
            or [("なし", "除外したTrialはない")],
        ),
    )
    return page("RQ1 混合と同質の比較", body, payload=result, nav=[("./experiment.html", "実験"), ("./rq2.html", "RQ2")])


def render_rq2_markdown(result: Dict[str, Any]) -> str:
    lines = [
        "# RQ2 同質構成16タイプの比較",
        "",
        "探索的分析である。あらかじめ方向を決めた仮説は置かない。",
        "16タイプの総当たりは120通りになり、多重比較の補正をかけると有効Trial数では何も検出できない。",
        "そのためFriedman検定は全体の差があるかだけを見、タイプ間の個別比較は順位の提示にとどめる。",
        "",
        "- 有効Trial数: {0}".format(result["eligible_count"]),
        "- 指標版: `{0}`".format(result["indicator_version"]),
        "",
        "## Friedman検定（全体）",
        "",
        md_table(
            ("指標", "Q", "p", "有効行数"),
            [
                (
                    METRIC_LABELS[key],
                    fmt_number(item.get("q")),
                    fmt_number(item.get("p")),
                    item.get("n"),
                )
                for key, item in result["friedman"].items()
            ],
        ),
        "",
        "## タイプごとの中央値と順位（{0}）".format(METRIC_LABELS["village_correct"]),
        "",
        md_table(
            ("順位", "タイプ", "中央値", "四分位範囲", "有効Trial数"),
            result["ranking_rows"],
        ),
        "",
        "## 除外したTrial",
        "",
        _exclusions_md(result["exclusions"]),
        "",
    ]
    return "\n".join(lines)


def render_rq2_html(result: Dict[str, Any]) -> str:
    body = (
        '<p class="note">探索的分析である。タイプ間の個別比較は行わない。</p>'
        "<h2>Friedman検定（全体）</h2>"
        "{0}"
        "<h2>タイプごとの順位（村人正答）</h2>"
        "{1}"
    ).format(
        table_html(
            ("指標", "Q", "p", "有効行数"),
            [
                (METRIC_LABELS[key], fmt_number(item.get("q")), fmt_number(item.get("p")), item.get("n"))
                for key, item in result["friedman"].items()
            ],
        ),
        table_html(
            ("順位", "タイプ", "中央値", "四分位範囲", "有効Trial数"),
            result["ranking_rows"],
        ),
    )
    return page("RQ2 同質16タイプの比較", body, payload=result, nav=[("./experiment.html", "実験"), ("./rq1.html", "RQ1")])


def render_manipulation_markdown(result: Dict[str, Any]) -> str:
    lines = [
        "# 操作確認（MBTI条件が発言傾向に現れているか）",
        "",
        "RQ1・RQ2とは別の確認である。差が出ない場合、行動傾向文が効いていない可能性を示す。",
        "先行実験で使った8タイプと、本システムで新規に作った8タイプを分けて集計する。",
        "",
        "## タイプごとの発言傾向",
        "",
        md_table(
            ("タイプ", "文面の由来", "平均発言数", "平均文字数", "見送り率", "最多ラベル"),
            result["type_rows"],
        ),
        "",
        "## 由来ごとの集計",
        "",
        md_table(
            ("由来", "平均発言数", "平均文字数", "見送り率"),
            result["source_rows"],
        ),
        "",
    ]
    return "\n".join(lines)


def _exclusions_md(exclusions: Sequence[Dict[str, str]]) -> str:
    if not exclusions:
        return "除外したTrialはない。"
    return md_table(("Trial", "理由"), [(item["trial_id"], item["reason"]) for item in exclusions])


def _rq1_rows(result: Dict[str, Any]) -> List[List[Any]]:
    rows = []
    for key in RQ1_METRICS:
        item = result["tests"][key]
        rows.append(
            [
                METRIC_LABELS[key],
                fmt_number(item["mixed_median"]),
                fmt_number(item["homogeneous_median"]),
                fmt_number(item["p_two_sided"]),
                fmt_number(item["r"]),
                item["n"],
            ]
        )
    return rows


def _evidence_rows(result: Dict[str, Any]) -> List[List[Any]]:
    rows = []
    for trial in result.get("pairs") or []:
        rows.append(
            [
                trial["trial_id"],
                fmt_number(trial["mixed"].get("village_correct"), 0),
                fmt_number(trial["mixed"].get("final_entropy")),
                fmt_number(trial["mixed"].get("correction_rate")),
            ]
        )
    return rows


def tendency_sources(data_dir: Path = None) -> Dict[str, str]:
    """`tendencies.json` の `source` を読む。ファイルがなければ設計書5.2の分類を使う。"""

    sources = {name: ("recorded" if name in RECORDED_TYPES else "drafted") for name in HOMOGENEOUS_TYPES}
    path = Path(__file__).resolve().parents[1] / "agents" / "prompts" / "v2" / "tendencies.json"
    if not path.is_file():
        return sources
    raw = json.loads(path.read_text(encoding="utf-8"))
    for name, item in (raw.get("tendencies") or {}).items():
        if isinstance(item, dict) and item.get("source"):
            sources[name] = str(item["source"])
    return sources
