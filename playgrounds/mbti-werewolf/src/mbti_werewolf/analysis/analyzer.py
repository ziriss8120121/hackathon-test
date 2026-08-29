"""実験ディレクトリを読んで分析出力を書く（設計書3.6）。"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from ..agents.mbti_types import TYPE_STACKS
from ..config import INDICATOR_VERSION
from ..judge.judge import judge_file_name
from ..record.metrics_csv import (
    write_experiment_metrics,
    write_speech_labels,
    write_trial_metrics,
)
from ..record.result_view import write_latest_redirect
from . import experiment_report, rq_report, trial_report
from .indicators import (
    RQ1_METRICS,
    enriched_case_metrics,
    exclusion_reason,
    frozen_note,
    speech_label_rows,
)
from .stats import friedman, iqr, median, wilcoxon_signed_rank

HOMOGENEOUS_TYPES = tuple(TYPE_STACKS)


class AnalyzeError(Exception):
    """分析の入力が揃っていない。"""


class Analyzer:
    def __init__(
        self,
        runs_dir: Path,
        criteria_version: str = "v1",
        on_progress=None,
    ) -> None:
        self.runs_dir = Path(runs_dir)
        self.criteria_version = criteria_version
        self._on_progress = on_progress or (lambda _message: None)

    def run(self, experiment_id: str) -> Dict[str, Any]:
        exp_dir = self.runs_dir / experiment_id
        if not exp_dir.is_dir():
            raise AnalyzeError("実験のディレクトリがない: {0}".format(exp_dir))

        experiment = _read_json(exp_dir / "experiment.json") or {}
        status = _read_json(exp_dir / "status.json") or {}
        config = experiment.get("config") or {}
        indicator_version = config.get("indicator_version") or INDICATOR_VERSION
        frozen_at = config.get("indicator_frozen_at")
        started_at = status.get("started_at")

        trials = self._load_trials(exp_dir)
        if not trials:
            raise AnalyzeError("分析できるTrialがない: {0}".format(exp_dir))

        all_logs: List[Dict[str, Any]] = []
        speech_rows: List[Dict[str, Any]] = []
        eligible: List[Dict[str, Any]] = []
        exclusions: List[Dict[str, str]] = []

        for trial in trials:
            cases = trial["cases"]
            all_logs.extend(case["_log"] for case in cases)
            for case in cases:
                if case.get("_judge"):
                    speech_rows.extend(speech_label_rows(case["_log"], case["_judge"]))

            reason = exclusion_reason(cases)
            missing_judge = [c for c in cases if not c.get("_judge")]
            if reason is None and missing_judge:
                reason = "Judge評価がないケースがある（{0}件）".format(len(missing_judge))
            if reason is None:
                eligible.append(trial)
            else:
                exclusions.append({"trial_id": trial["trial_id"], "reason": reason})

            (trial["directory"] / "trial_report.md").write_text(
                trial_report.render_markdown(trial, cases), encoding="utf-8"
            )
            (trial["directory"] / "trial.html").write_text(
                trial_report.render_html(trial, cases), encoding="utf-8"
            )
            write_trial_metrics(
                trial["directory"] / "trial_metrics.csv",
                [case["_log"] for case in cases],
            )
            self._on_progress("{0}: trial_report.md".format(trial["trial_id"]))

        write_experiment_metrics(exp_dir / "experiment_metrics.csv", all_logs)
        write_speech_labels(exp_dir / "speech_labels.csv", speech_rows)

        rq1 = self._rq1(eligible, exclusions, indicator_version, frozen_at, started_at)
        rq2 = self._rq2(eligible, exclusions, indicator_version)
        manipulation = self._manipulation(eligible)

        summary = {
            "experiment_id": experiment_id,
            "indicator_version": indicator_version,
            "indicator_frozen_at": frozen_at,
            "trial_total": len(trials),
            "eligible_count": len(eligible),
            "excluded_count": len(exclusions),
            "exclusions": exclusions,
            "case_done": sum(1 for t in trials for c in t["cases"] if c.get("status") == "done"),
            "case_failed": sum(1 for t in trials for c in t["cases"] if c.get("status") != "done"),
            "mixed_values": _collect_values(eligible, mixed=True),
            "homogeneous_values": _collect_values(eligible, mixed=False),
            "trials": [
                {"trial_id": t["trial_id"], "dir_name": t["directory"].name} for t in trials
            ],
        }

        (exp_dir / "experiment_report.md").write_text(
            experiment_report.render_markdown(summary), encoding="utf-8"
        )
        (exp_dir / "experiment.html").write_text(
            experiment_report.render_html(summary), encoding="utf-8"
        )
        (exp_dir / "rq1.md").write_text(rq_report.render_rq1_markdown(rq1), encoding="utf-8")
        (exp_dir / "rq1.html").write_text(rq_report.render_rq1_html(rq1), encoding="utf-8")
        (exp_dir / "rq2.md").write_text(rq_report.render_rq2_markdown(rq2), encoding="utf-8")
        (exp_dir / "rq2.html").write_text(rq_report.render_rq2_html(rq2), encoding="utf-8")
        (exp_dir / "manipulation_check.md").write_text(
            rq_report.render_manipulation_markdown(manipulation), encoding="utf-8"
        )

        write_latest_redirect(
            self.runs_dir, experiment_id, "{0}/experiment.html".format(experiment_id)
        )
        return {
            "experiment_id": experiment_id,
            "directory": str(exp_dir),
            "trial_total": len(trials),
            "eligible_count": len(eligible),
            "excluded_count": len(exclusions),
            "speech_label_rows": len(speech_rows),
        }

    def _load_trials(self, exp_dir: Path) -> List[Dict[str, Any]]:
        trials: List[Dict[str, Any]] = []
        for trial_dir in sorted(
            d for d in exp_dir.iterdir() if d.is_dir() and (d / "trial.json").is_file()
        ):
            raw = _read_json(trial_dir / "trial.json") or {}
            cases = []
            for case_dir in sorted(d for d in trial_dir.iterdir() if d.is_dir()):
                log = _read_json(case_dir / "case_log.json")
                if not log:
                    continue
                judge = _read_json(case_dir / judge_file_name(self.criteria_version))
                row = enriched_case_metrics(log, judge)
                row["_log"] = log
                row["_judge"] = judge
                row["_dir_name"] = case_dir.name
                # CSVへJudge列を戻すため、ログ上の指標も同じ値で上書きする。
                log["_metrics_overlay"] = {
                    "final_entropy": row["final_entropy"],
                    "convergence_round": row["convergence_round"],
                }
                cases.append(row)
            trials.append(
                {
                    "trial_id": raw.get("trial_id") or trial_dir.name,
                    "trial_index": raw.get("trial_index"),
                    "trial_seed": raw.get("trial_seed"),
                    "pattern_id": raw.get("pattern_id"),
                    "directory": trial_dir,
                    "cases": cases,
                }
            )
        return trials

    def _rq1(
        self,
        eligible: Sequence[Dict[str, Any]],
        exclusions: Sequence[Dict[str, str]],
        indicator_version: str,
        frozen_at: Optional[str],
        started_at: Optional[str],
    ) -> Dict[str, Any]:
        pairs = []
        for trial in eligible:
            mixed = next(c for c in trial["cases"] if c.get("composition") == "mixed")
            homo = [c for c in trial["cases"] if c.get("composition") == "homogeneous"]
            pairs.append(
                {
                    "trial_id": trial["trial_id"],
                    "mixed": mixed,
                    "homogeneous_median": {
                        key: median([c.get(key) for c in homo]) for key in RQ1_METRICS
                    },
                }
            )
        tests = {}
        for key in RQ1_METRICS:
            left = [p["mixed"].get(key) for p in pairs]
            right = [p["homogeneous_median"].get(key) for p in pairs]
            result = wilcoxon_signed_rank(left, right)
            result["mixed_median"] = median(left)
            result["homogeneous_median"] = median(right)
            tests[key] = result
        return {
            "indicator_version": indicator_version,
            "frozen_note": frozen_note(frozen_at, started_at),
            "eligible_count": len(eligible),
            "exclusions": list(exclusions),
            "tests": tests,
            "pairs": [
                {
                    "trial_id": p["trial_id"],
                    "mixed": {k: p["mixed"].get(k) for k in RQ1_METRICS},
                    "homogeneous_median": p["homogeneous_median"],
                }
                for p in pairs
            ],
        }

    def _rq2(
        self, eligible: Sequence[Dict[str, Any]], exclusions, indicator_version: str
    ) -> Dict[str, Any]:
        friedman_out = {}
        for key in RQ1_METRICS:
            matrix = []
            for trial in eligible:
                by_type = {
                    c.get("homogeneous_type"): c.get(key)
                    for c in trial["cases"]
                    if c.get("composition") == "homogeneous"
                }
                matrix.append([by_type.get(name) for name in HOMOGENEOUS_TYPES])
            friedman_out[key] = friedman(matrix)

        values_by_type = {name: [] for name in HOMOGENEOUS_TYPES}
        for trial in eligible:
            for case in trial["cases"]:
                name = case.get("homogeneous_type")
                if name in values_by_type:
                    values_by_type[name].append(case.get("village_correct"))

        ranking = []
        for name in HOMOGENEOUS_TYPES:
            values = values_by_type[name]
            ranking.append(
                {
                    "type": name,
                    "median": median(values),
                    "iqr": iqr(values),
                    "n": sum(1 for v in values if v is not None),
                }
            )
        ranking.sort(key=lambda item: (item["median"] is None, -(item["median"] or 0), item["type"]))
        ranking_rows = []
        for index, item in enumerate(ranking, start=1):
            ranking_rows.append(
                [
                    index,
                    item["type"],
                    None if item["median"] is None else item["median"],
                    None if item["iqr"] is None else item["iqr"],
                    item["n"],
                ]
            )
        return {
            "indicator_version": indicator_version,
            "eligible_count": len(eligible),
            "exclusions": list(exclusions),
            "friedman": friedman_out,
            "ranking_rows": ranking_rows,
        }

    def _manipulation(self, eligible: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
        sources = rq_report.tendency_sources()
        buckets: Dict[str, Dict[str, List[Any]]] = defaultdict(
            lambda: {"speech_count": [], "total_chars": [], "pass_rate": [], "labels": []}
        )
        for trial in eligible:
            for case in trial["cases"]:
                name = case.get("homogeneous_type")
                if not name:
                    continue
                buckets[name]["speech_count"].append(case.get("total_speeches"))
                buckets[name]["total_chars"].append(case.get("total_chars"))
                buckets[name]["pass_rate"].append(case.get("pass_rate"))
                judge = case.get("_judge") or {}
                for speech in judge.get("speeches") or []:
                    buckets[name]["labels"].extend(speech.get("labels") or [])

        type_rows = []
        source_acc: Dict[str, Dict[str, List[Any]]] = defaultdict(
            lambda: {"speech_count": [], "total_chars": [], "pass_rate": []}
        )
        for name in HOMOGENEOUS_TYPES:
            data = buckets[name]
            origin = sources.get(name, "drafted")
            top_label = _mode(data["labels"])
            type_rows.append(
                [
                    name,
                    origin,
                    median(data["speech_count"]),
                    median(data["total_chars"]),
                    median(data["pass_rate"]),
                    top_label or "—",
                ]
            )
            source_acc[origin]["speech_count"].extend(data["speech_count"])
            source_acc[origin]["total_chars"].extend(data["total_chars"])
            source_acc[origin]["pass_rate"].extend(data["pass_rate"])

        source_rows = []
        for origin in ("recorded", "drafted"):
            data = source_acc[origin]
            source_rows.append(
                [
                    origin,
                    median(data["speech_count"]),
                    median(data["total_chars"]),
                    median(data["pass_rate"]),
                ]
            )
        return {"type_rows": type_rows, "source_rows": source_rows}


def _collect_values(eligible: Sequence[Dict[str, Any]], mixed: bool) -> Dict[str, List[Any]]:
    collected = {key: [] for key in RQ1_METRICS}
    want = "mixed" if mixed else "homogeneous"
    for trial in eligible:
        for case in trial["cases"]:
            if case.get("composition") != want:
                continue
            for key in RQ1_METRICS:
                collected[key].append(case.get(key))
    return collected


def _mode(values: Sequence[str]) -> Optional[str]:
    if not values:
        return None
    counts: Dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return max(counts, key=lambda name: (counts[name], name))


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, ValueError, OSError):
        return None
