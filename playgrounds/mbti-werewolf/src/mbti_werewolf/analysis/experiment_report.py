"""実験全体の要約（設計書6.10、F-62）。

有効Trial数と除外理由を隠さない。RQの検出力は有効Trial数で決まる（9.4）。
"""

from __future__ import annotations

from typing import Any, Dict, List, Sequence

from .html import fmt_number, md_table, page, table_html
from .indicators import METRIC_LABELS, RQ1_METRICS
from .stats import median


def render_markdown(summary: Dict[str, Any]) -> str:
    lines = [
        "# 実験 {0}".format(summary["experiment_id"]),
        "",
        "- 指標版: `{0}`".format(summary.get("indicator_version") or "v1"),
        "- 指標の確定: {0}".format(summary.get("indicator_frozen_at") or "未確定"),
        "- Trial数: {0}".format(summary["trial_total"]),
        "- 有効Trial数: {0}".format(summary["eligible_count"]),
        "- 除外Trial数: {0}".format(summary["excluded_count"]),
        "- ケース数（完了）: {0}".format(summary["case_done"]),
        "- 失敗ケース: {0}".format(summary["case_failed"]),
        "",
        "## 除外したTrial",
        "",
        _exclusion_md(summary["exclusions"]),
        "",
        "## 構成種別ごとの集計（有効Trial）",
        "",
        _composition_md(summary),
        "",
    ]
    return "\n".join(lines)


def render_html(summary: Dict[str, Any]) -> str:
    trial_links = "".join(
        '<li><a href="{0}/trial.html">{1}</a></li>'.format(
            item["dir_name"], item["trial_id"]
        )
        for item in summary.get("trials", [])
    )
    body = (
        '<p class="sub">指標版 {0} / 確定 {1}</p>'
        "<h2>件数</h2>"
        "{2}"
        "<h2>除外したTrial</h2>"
        "{3}"
        "<h2>構成種別ごとの集計（有効Trial）</h2>"
        "{4}"
        "<h2>Trial</h2>"
        "<ul>{5}</ul>"
    ).format(
        summary.get("indicator_version") or "v1",
        summary.get("indicator_frozen_at") or "未確定",
        table_html(
            ("項目", "件数"),
            [
                ("Trial数", summary["trial_total"]),
                ("有効Trial数", summary["eligible_count"]),
                ("除外Trial数", summary["excluded_count"]),
                ("完了ケース", summary["case_done"]),
                ("失敗ケース", summary["case_failed"]),
            ],
        ),
        table_html(
            ("Trial", "理由"),
            [(item["trial_id"], item["reason"]) for item in summary["exclusions"]]
            or [("なし", "除外したTrialはない")],
        ),
        table_html(
            ("指標", "混合 中央値", "同質 中央値"),
            _composition_rows(summary),
        ),
        trial_links,
    )
    return page(
        "実験 {0}".format(summary["experiment_id"]),
        body,
        payload=summary,
        nav=[
            ("./rq1.html", "RQ1"),
            ("./rq2.html", "RQ2"),
            ("./manipulation_check.md", "操作確認"),
        ],
    )


def _exclusion_md(exclusions: Sequence[Dict[str, str]]) -> str:
    if not exclusions:
        return "除外したTrialはない。"
    return md_table(
        ("Trial", "理由"),
        [(item["trial_id"], item["reason"]) for item in exclusions],
    )


def _composition_rows(summary: Dict[str, Any]) -> List[List[Any]]:
    mixed = summary.get("mixed_values") or {}
    homo = summary.get("homogeneous_values") or {}
    rows = []
    for key in RQ1_METRICS:
        rows.append(
            [
                METRIC_LABELS[key],
                fmt_number(median(mixed.get(key) or [])),
                fmt_number(median(homo.get(key) or [])),
            ]
        )
    return rows


def _composition_md(summary: Dict[str, Any]) -> str:
    return md_table(("指標", "混合 中央値", "同質 中央値"), _composition_rows(summary))
