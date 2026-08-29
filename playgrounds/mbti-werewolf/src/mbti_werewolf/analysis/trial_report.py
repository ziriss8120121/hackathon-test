"""Trialの補助分析（設計書6.10、F-61）。

同じ人物・役割・条件を共有する17ケースを1表に並べる。RQ1の確認的分析ではなく、
1 Trialの中を見るための補助である。
"""

from __future__ import annotations

from typing import Any, Dict, List, Sequence

from .html import fmt_number, md_table, page, table_html
from .indicators import METRIC_LABELS, RQ1_METRICS

WINNER = {"village": "村人陣営", "werewolf": "人狼陣営"}

HEADERS = (
    "ケース",
    "構成",
    "勝敗",
    "追放",
    "村人正答",
    "得票集中",
    "最終エントロピー",
    "収束ラウンド",
    "修正率",
)


def composition_text(row: Dict[str, Any]) -> str:
    if row.get("composition") == "mixed":
        return "混合"
    return "同質 {0}".format(row.get("homogeneous_type") or "")


def case_href(row: Dict[str, Any]) -> str:
    return "{0}/result.html".format(row["_dir_name"])


def render_markdown(trial: Dict[str, Any], cases: Sequence[Dict[str, Any]]) -> str:
    lines = [
        "# Trial {0}".format(trial.get("trial_id")),
        "",
        "この表は補助分析である。RQ1の確認的比較は実験全体の `rq1.md` を見る。",
        "",
        "## 固定条件",
        "",
        "- パターン: `{0}`".format(trial.get("pattern_id") or "—"),
        "- seed: `{0}`".format(trial.get("trial_seed") or "—"),
        "- 指標版: `{0}`".format((cases[0].get("indicator_version") if cases else None) or "v1"),
        "",
        "## 17ケースの比較",
        "",
        md_table(HEADERS, [_row(c) for c in cases]),
        "",
        "## 混合と同質16タイプの差",
        "",
        _diff_markdown(cases),
        "",
    ]
    return "\n".join(lines)


def render_html(trial: Dict[str, Any], cases: Sequence[Dict[str, Any]]) -> str:
    links = "".join(
        '<li><a href="{0}">{1}</a> {2}</li>'.format(
            case_href(case), case["case_id"], composition_text(case)
        )
        for case in cases
    )
    body = (
        '<p class="sub">この表は補助分析である。RQ1の確認的比較は実験全体の '
        '<a href="../rq1.html">rq1.html</a> を見る。</p>'
        "<h2>17ケースの比較</h2>"
        "{0}"
        "<h2>ケースの結果画面</h2>"
        "<ul>{1}</ul>"
        "<h2>混合と同質16タイプの差</h2>"
        "{2}"
    ).format(
        table_html(HEADERS, [_row(c) for c in cases]),
        links,
        table_html(
            ("指標", "混合", "同質中央値", "差"),
            _diff_rows(cases),
        ),
    )
    payload = {
        "trial_id": trial.get("trial_id"),
        "cases": [
            {key: case.get(key) for key in ("case_id", "composition", "homogeneous_type", "winner") + RQ1_METRICS}
            for case in cases
        ],
    }
    return page(
        "Trial {0}".format(trial.get("trial_id")),
        body,
        payload=payload,
        nav=[("../experiment.html", "実験"), ("../rq1.html", "RQ1"), ("../rq2.html", "RQ2")],
    )


def _row(case: Dict[str, Any]) -> List[Any]:
    executed = case.get("executed") or []
    if isinstance(executed, str):
        executed_text = executed
    else:
        executed_text = ", ".join(str(v).upper() for v in executed) or "なし"
    return [
        case.get("case_id"),
        composition_text(case),
        WINNER.get(case.get("winner"), "無効試合" if not case.get("valid") else "—"),
        executed_text,
        fmt_number(case.get("village_correct"), 0),
        fmt_number(case.get("vote_concentration")),
        fmt_number(case.get("final_entropy")),
        fmt_number(case.get("convergence_round"), 0),
        fmt_number(case.get("correction_rate")),
    ]


def _diff_rows(cases: Sequence[Dict[str, Any]]) -> List[List[Any]]:
    from .stats import median

    mixed = next((c for c in cases if c.get("composition") == "mixed"), None)
    homo = [c for c in cases if c.get("composition") == "homogeneous"]
    if mixed is None or not homo:
        return []
    rows = []
    for key in RQ1_METRICS:
        left = mixed.get(key)
        right = median([c.get(key) for c in homo])
        delta = None if left is None or right is None else left - right
        rows.append(
            [METRIC_LABELS[key], fmt_number(left), fmt_number(right), fmt_number(delta)]
        )
    return rows


def _diff_markdown(cases: Sequence[Dict[str, Any]]) -> str:
    rows = _diff_rows(cases)
    if not rows:
        return "混合ケースまたは同質ケースがないため差を出せない。"
    lines = [
        "混合1ケースの値と、同質16ケースの中央値の差（混合 − 同質）。",
        "",
        md_table(("指標", "混合", "同質中央値", "差"), rows),
    ]
    return "\n".join(lines)
