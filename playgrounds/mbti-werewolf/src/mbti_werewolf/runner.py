"""実験 → Trial → ケースの実行管理（設計書3.5、6.1、6.5）。

ケースを1件終えるごとにファイルへ書き出す。1,700ケースの実行は途中で止まる前提な
ので、止まった時点までの結果が必ず残る形にしている。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from . import experiment as experiment_module
from . import masterdata
from .brains.factory import create_case_brain
from .engine import rules as rules_module
from .engine.case import CaseEngine
from .config import ENV_RUNS_DIR, ExperimentConfig, apply_fixed_conditions
from .record.case_log import STATUS_DONE, STATUS_FAILED, build_case_log, write_json
from .record.result_view import (
    write_failure_html,
    write_latest_redirect,
    write_result_html,
)
from .record.summary import write_summary
from .record.metrics_csv import write_experiment_metrics, write_trial_metrics
from .record.timing import seconds_per_call, write_timing_note
from .record.transcript import write_transcript

STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_SKIPPED = "skipped"

#: 1ケースあたりの実行回数の上限。1回目が失敗したら1回だけ作り直して試す。
#: 失敗のまま次へ進むのは、1ケースの失敗で17ケースを止めないためである（F-51）。
DEFAULT_CASE_ATTEMPTS = 2

#: 失敗の分類（設計書6.5、F-59）。BrainErrorのkindに合わせ、それ以外を internal にする。
ERROR_KINDS = ("unreachable", "rate_limited", "timeout", "invalid_response", "internal")


class ResumeError(Exception):
    """再開しようとした実験のファイルが読めない、または足りない。"""


def default_runs_dir() -> Path:
    """出力先。v1と同じ `runs/` を共有する。ファイル名で世代を判別できる（F-37）。"""

    override = os.environ.get(ENV_RUNS_DIR)
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[3] / "runs"


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def error_kind_of(exc: BaseException) -> str:
    """例外を6.5の5分類へ落とす。`kind` で原因を判別できる状態にする（NF-07）。"""

    kind = getattr(exc, "kind", None)
    return kind if kind in ERROR_KINDS else "internal"


@dataclass
class CaseResult:
    case_id: str
    status: str
    directory: Path
    winner: Optional[str] = None
    valid: bool = False
    inference_calls: int = 0
    elapsed_seconds: float = 0.0
    ai_wait_seconds: float = 0.0
    attempt: int = 1
    error: Optional[Dict[str, str]] = None


@dataclass
class RunTotals:
    """件数の集計（設計書6.5）。

    実験の `status.json` は実験全体の進み具合を出す。再開のたびに0から数え直すと、
    100 Trialの実行で「どこまで終わったか」が読めなくなる。そのため前回までに完了して
    いたケースも `case_done` に含める。一方、実行担当が画面で見る要約は今回の実行で
    何をしたかなので、こちらは今回分だけを数える。この2つを分けて持つ。
    """

    case_total: int = 0
    #: 今回の実行で完了したケース。
    case_done: int = 0
    #: 今回の実行で上限まで失敗したケース。
    case_failed: int = 0
    #: 前回までに完了していて、再開で飛ばしたケース。
    case_prior_done: int = 0
    #: `--cases` で対象外にしたケース。
    case_filtered: int = 0
    trial_total: int = 0
    trial_done: int = 0
    trial_complete: int = 0
    results: List[CaseResult] = field(default_factory=list)

    @property
    def total_done(self) -> int:
        """実験全体で完了しているケース。"""

        return self.case_done + self.case_prior_done

    @property
    def case_skipped(self) -> int:
        """今回の実行で実行しなかったケース。"""

        return self.case_prior_done + self.case_filtered

    @property
    def case_pending(self) -> int:
        return self.case_total - self.total_done - self.case_failed - self.case_filtered


class ExperimentRunner:
    def __init__(
        self,
        config: ExperimentConfig,
        data_dir: Optional[Path] = None,
        runs_dir: Optional[Path] = None,
        on_progress: Optional[Callable[[str], None]] = None,
        case_attempts: int = DEFAULT_CASE_ATTEMPTS,
        case_filter: Optional[Sequence[str]] = None,
    ) -> None:
        self.config = config
        self.data_dir = Path(data_dir) if data_dir else experiment_module.default_data_dir()
        self.runs_dir = Path(runs_dir) if runs_dir else default_runs_dir()
        self._on_progress = on_progress or (lambda _message: None)
        self.case_attempts = max(1, case_attempts)
        #: `c00` や `c05-ISTJ` の形で実行対象を絞る。1ケースだけの実測に使う。
        self.case_filter = [str(v) for v in case_filter] if case_filter else None

    # --- 入力 ---------------------------------------------------------------

    def load_inputs(self):
        pool = masterdata.load_person_pool(
            self.data_dir / "persons" / "{0}.json".format(self.config.pool_id)
        )
        pattern_set = masterdata.load_pattern_set(
            self.data_dir / "patterns" / "{0}.json".format(self.config.pattern_set_id),
            pool,
        )
        rule_set = rules_module.load_rule_set(
            rules_module.rule_set_path(self.data_dir, self.config.rule_set_id)
        )
        return pool, pattern_set, rule_set

    def _load_rule_set(self, rule_set_id: str):
        return rules_module.load_rule_set(
            rules_module.rule_set_path(self.data_dir, rule_set_id)
        )

    # --- 実行 ---------------------------------------------------------------

    def run(self, experiment_id: Optional[str] = None) -> Dict[str, Any]:
        """新しい実験を始める。"""

        pool, pattern_set, rule_set = self.load_inputs()
        plan = experiment_module.build_experiment(
            self.config, rule_set, pool, pattern_set, experiment_id=experiment_id
        )

        exp_dir = self.runs_dir / plan.experiment_id
        exp_dir.mkdir(parents=True, exist_ok=True)
        write_json(exp_dir / "experiment.json", plan.to_dict())
        # 使用したマスタデータのスナップショットを残す。`data/` を後から書き換えても
        # 過去の実験結果が指す人物定義は変わらない（F-03、F-09）。
        write_json(exp_dir / "pool_snapshot.json", pool.to_dict())
        write_json(exp_dir / "pattern_snapshot.json", pattern_set.to_dict())

        return self._run_trials(plan.experiment_id, exp_dir, plan.trials, resumed=False)

    def resume(self, experiment_id: str) -> Dict[str, Any]:
        """止まった実験を続ける（設計書3.5）。

        Trialの固定条件は `trial.json` から復元する。完了済みのケースは実行しない。
        """

        exp_dir = self.runs_dir / experiment_id
        experiment_path = exp_dir / "experiment.json"
        if not experiment_path.is_file():
            raise ResumeError("実験のファイルがない: {0}".format(experiment_path))

        saved = json.loads(experiment_path.read_text(encoding="utf-8"))
        trial_dirs = sorted(
            d for d in exp_dir.iterdir() if d.is_dir() and (d / "trial.json").is_file()
        )
        if not trial_dirs:
            raise ResumeError(
                "trial.json を持つTrialのディレクトリがない: {0}".format(exp_dir)
            )

        rule_set = self._load_rule_set(str(saved.get("rule_set_id", self.config.rule_set_id)))
        if rule_set.rule_set_version != str(saved.get("rule_set_version", "")):
            raise ResumeError(
                "ルールセットの版が実験の記録と違う: いま {0} / 記録 {1}".format(
                    rule_set.rule_set_version, saved.get("rule_set_version")
                )
            )

        trials = []
        for trial_dir in trial_dirs:
            raw = json.loads((trial_dir / "trial.json").read_text(encoding="utf-8"))
            config, notes = apply_fixed_conditions(self.config, raw["fixed_conditions"])
            for note in notes:
                self._on_progress(
                    "{0}: Trialの記録で条件を上書き（{1}）".format(raw["trial_id"], note)
                )
            trials.append(experiment_module.restore_trial(raw, config, rule_set))

        return self._run_trials(experiment_id, exp_dir, trials, resumed=True)

    def _run_trials(
        self, experiment_id: str, exp_dir: Path, trials, resumed: bool
    ) -> Dict[str, Any]:
        totals = RunTotals(trial_total=len(trials))
        totals.case_total = sum(len(t.cases) for t in trials)
        started_at = _now()
        self._write_experiment_status(
            exp_dir, experiment_id, STATUS_RUNNING, totals, started_at
        )

        for trial in trials:
            trial_dir = exp_dir / trial.dir_name
            trial_dir.mkdir(parents=True, exist_ok=True)
            if not resumed:
                write_json(trial_dir / "trial.json", trial.to_dict())

            for case in trial.cases:
                if self._should_skip(case, resumed):
                    case_dir = trial_dir / case.dir_name
                    if resumed and case.status == STATUS_DONE:
                        totals.case_prior_done += 1
                    else:
                        totals.case_filtered += 1
                    totals.results.append(
                        CaseResult(
                            case_id=case.case_id,
                            status=STATUS_SKIPPED,
                            directory=case_dir,
                        )
                    )
                    continue

                self._write_experiment_status(
                    exp_dir,
                    experiment_id,
                    STATUS_RUNNING,
                    totals,
                    started_at,
                    current_trial_id=trial.trial_id,
                    current_case_id=case.case_id,
                )
                result = self._run_case_with_attempts(
                    trial, case, trial.rule_set, trial_dir
                )
                totals.results.append(result)
                if result.status == STATUS_DONE:
                    totals.case_done += 1
                else:
                    totals.case_failed += 1

                case.status = result.status
                # ケースを1件終えるごとに trial.json を更新する。途中で止めても
                # どこまで終わったかがファイルから読める（設計書3.5）。
                write_json(trial_dir / "trial.json", trial.to_dict())
                self._write_trial_status(trial_dir, trial)
                if result.status == STATUS_DONE:
                    self._point_latest_at(exp_dir, trial, case)

            totals.trial_done += 1
            if all(c.status == STATUS_DONE for c in trial.cases):
                totals.trial_complete += 1
            self._write_trial_status(trial_dir, trial)
            write_trial_metrics(trial_dir / "trial_metrics.csv", self._case_logs(trial_dir))

        write_experiment_metrics(
            exp_dir / "experiment_metrics.csv", self._all_case_logs(exp_dir)
        )
        summary = self._build_summary(experiment_id, exp_dir, totals, resumed)
        write_json(exp_dir / "experiment_summary.json", summary)
        write_timing_note(
            exp_dir / "timing.md",
            summary,
            {
                "provider": self.config.brain.provider,
                "model": self.config.brain.model,
            },
        )
        self._write_experiment_status(
            exp_dir, experiment_id, STATUS_DONE, totals, started_at
        )
        return summary

    # --- 集計CSVと最新結果リンク ---------------------------------------------

    def _case_logs(self, trial_dir: Path) -> List[Dict[str, Any]]:
        """1 Trialの `case_log.json` をケース順に読む（設計書6.9）。

        実行中に集めた結果ではなくファイルから読む。再開したときに、前回までに
        完了したケースもCSVへ入る必要がある。実行中の結果だけを使うと、再開した
        実行のCSVに今回のケースしか出ない。
        """

        logs: List[Dict[str, Any]] = []
        if not trial_dir.is_dir():
            return logs
        for case_dir in sorted(d for d in trial_dir.iterdir() if d.is_dir()):
            path = case_dir / "case_log.json"
            if not path.is_file():
                continue
            try:
                logs.append(json.loads(path.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, ValueError, OSError):
                # 書き込み途中で止まったファイルはCSVから外す。ここで例外にすると
                # 1件の壊れたファイルで実験全体のCSVが出なくなる。
                self._on_progress("{0} を読めないためCSVから外した".format(path))
        return logs

    def _all_case_logs(self, exp_dir: Path) -> List[Dict[str, Any]]:
        logs: List[Dict[str, Any]] = []
        for trial_dir in sorted(
            d for d in exp_dir.iterdir() if d.is_dir() and (d / "trial.json").is_file()
        ):
            logs.extend(self._case_logs(trial_dir))
        return logs

    def _point_latest_at(self, exp_dir: Path, trial, case) -> None:
        """`runs/latest.html` を直近に完了したケースへ向ける（設計書7.6）。

        1ケース終えるごとに更新する。長時間の実行中でも、いま何が出ているかを
        スマートフォンから確認できる状態にしておくため。
        """

        target = "{0}/{1}/{2}/result.html".format(
            exp_dir.name, trial.dir_name, case.dir_name
        )
        write_latest_redirect(self.runs_dir, case.case_id, target)

    def _should_skip(self, case, resumed: bool) -> bool:
        """完了済みのケースと、対象外に絞られたケースを実行しない。"""

        if self.case_filter is not None:
            names = (case.dir_name, "c{0:02d}".format(case.case_index), case.case_id)
            if not any(value in self.case_filter for value in names):
                return True
        # 失敗したケースは再開の対象にする。done だけを飛ばす（設計書3.5）。
        return resumed and case.status == STATUS_DONE

    # --- 1ケース -------------------------------------------------------------

    def _run_case_with_attempts(self, trial, case, rule_set, trial_dir: Path) -> CaseResult:
        case_dir = trial_dir / case.dir_name
        attempt = self._previous_attempts(case_dir)
        last: Optional[CaseResult] = None

        for offset in range(self.case_attempts):
            attempt += 1
            last = self._run_case(trial, case, rule_set, trial_dir, attempt)
            if last.status == STATUS_DONE:
                return last
            if offset + 1 < self.case_attempts:
                self._on_progress(
                    "{0}: {1}回目が失敗（{2}）。作り直して再実行する".format(
                        case.case_id, attempt, last.error["kind"] if last.error else "不明"
                    )
                )

        return last if last else CaseResult(
            case_id=case.case_id, status=STATUS_FAILED, directory=case_dir
        )

    def _previous_attempts(self, case_dir: Path) -> int:
        """前回までの実行回数。再開したケースに attempt を加算する（設計書3.5）。"""

        path = case_dir / "status.json"
        if not path.is_file():
            return 0
        try:
            saved = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError, OSError):
            return 0
        return int(saved.get("attempt", 0) or 0)

    def _run_case(self, trial, case, rule_set, trial_dir: Path, attempt: int) -> CaseResult:
        case_dir = trial_dir / case.dir_name
        case_dir.mkdir(parents=True, exist_ok=True)
        started_at = _now()
        max_rounds = trial.config.discussion.max_rounds
        self._write_case_status(
            case_dir,
            case,
            STATUS_RUNNING,
            attempt=attempt,
            started_at=started_at,
            max_rounds=max_rounds,
        )

        try:
            # ケースごとに脳を作る。Stubは呼び出し順で出力が決まるため、ケース間で
            # 状態を共有すると17ケースの比較に別の変数が入る。
            #
            # 脳とエンジンの生成もこの中に入れる。外に出すと、モデル名の誤りや接続
            # 不能で生成に失敗したときに実験全体が止まり、1ケースの失敗で17ケースを
            # 止めないという決まり（3.5、F-51）を満たせない。
            brain = create_case_brain(trial.config, seed=trial.trial_seed)
            engine = CaseEngine(case, rule_set, trial.config, brain, trial.trial_seed)
            outcome = engine.run()
        except Exception as exc:  # noqa: BLE001 - 失敗を記録して次のケースへ進む
            error = {"kind": error_kind_of(exc), "message": str(exc)}
            self._write_case_status(
                case_dir,
                case,
                STATUS_FAILED,
                attempt=attempt,
                started_at=started_at,
                max_rounds=max_rounds,
                error=error,
            )
            # 失敗時も result.html を残す（設計書7.5）。実行担当がブラウザだけで
            # 何が起きたかを追えるようにするため。
            write_failure_html(case_dir / "result.html", case, error, attempt)
            self._on_progress("{0}: 失敗 ({1})".format(case.case_id, error["kind"]))
            return CaseResult(
                case_id=case.case_id,
                status=STATUS_FAILED,
                directory=case_dir,
                attempt=attempt,
                error=error,
            )

        log = build_case_log(
            case, outcome, trial.config, rule_set, brain.describe(), trial, attempt=attempt
        )
        write_json(case_dir / "case_log.json", log)
        write_json(case_dir / "config.json", log["config"])
        write_transcript(case_dir / "transcript.md", log)
        write_summary(case_dir / "summary.md", log)
        write_result_html(case_dir / "result.html", log)
        self._write_case_status(
            case_dir,
            case,
            STATUS_DONE,
            attempt=attempt,
            started_at=started_at,
            max_rounds=max_rounds,
            outcome=outcome,
        )

        result = log["result"]
        self._on_progress(
            "{0}: {1} / {2}ラウンド / 呼び出し{3}回".format(
                case.case_id,
                "無効試合" if not result["valid"] else "{0}の勝利".format(result["winner"]),
                log["discussion"]["rounds"],
                outcome.inference_calls,
            )
        )
        return CaseResult(
            case_id=case.case_id,
            status=STATUS_DONE,
            directory=case_dir,
            winner=result["winner"],
            valid=result["valid"],
            inference_calls=outcome.inference_calls,
            elapsed_seconds=outcome.elapsed_seconds,
            ai_wait_seconds=outcome.ai_wait_seconds,
            attempt=attempt,
        )

    # --- status.json ---------------------------------------------------------

    def _write_case_status(
        self,
        case_dir: Path,
        case,
        status: str,
        attempt: int,
        started_at: str,
        max_rounds: int,
        error: Optional[Dict[str, str]] = None,
        outcome=None,
    ) -> None:
        discussion = getattr(outcome, "discussion", None)
        write_json(
            case_dir / "status.json",
            {
                "case_id": case.case_id,
                "trial_id": case.trial_id,
                "experiment_id": case.experiment_id,
                "composition": case.composition,
                "homogeneous_type": case.homogeneous_type,
                "status": status,
                "phase": getattr(outcome, "phase", None),
                "round": discussion.rounds if discussion else None,
                "max_rounds": max_rounds,
                "speech_count": discussion.total_speeches if discussion else None,
                "inference_calls": getattr(outcome, "inference_calls", None),
                "attempt": attempt,
                "started_at": started_at,
                "updated_at": _now(),
                "error": error,
            },
        )

    def _write_trial_status(self, trial_dir: Path, trial) -> None:
        counts: Dict[str, int] = {}
        for case in trial.cases:
            counts[case.status] = counts.get(case.status, 0) + 1
        done = counts.get(STATUS_DONE, 0)

        write_json(
            trial_dir / "status.json",
            {
                "trial_id": trial.trial_id,
                "experiment_id": trial.experiment_id,
                "trial_index": trial.trial_index,
                "status": STATUS_DONE if done == len(trial.cases) else STATUS_RUNNING,
                "case_total": len(trial.cases),
                "case_done": done,
                "case_failed": counts.get(STATUS_FAILED, 0),
                "case_pending": counts.get(STATUS_PENDING, 0),
                # 17ケースが1つでも欠けると対応あり比較に使えない（設計書3.5、9.4）。
                "complete": done == len(trial.cases),
                "updated_at": _now(),
            },
        )

    def _write_experiment_status(
        self,
        exp_dir: Path,
        experiment_id: str,
        status: str,
        totals: RunTotals,
        started_at: str,
        current_trial_id: Optional[str] = None,
        current_case_id: Optional[str] = None,
    ) -> None:
        write_json(
            exp_dir / "status.json",
            {
                "experiment_id": experiment_id,
                "status": status,
                "trial_total": totals.trial_total,
                "trial_done": totals.trial_done,
                "trial_complete": totals.trial_complete,
                "case_total": totals.case_total,
                # 実験全体の完了数。前回までに完了していたケースを含む。
                "case_done": totals.total_done,
                "case_failed": totals.case_failed,
                "case_skipped": totals.case_filtered,
                "case_pending": totals.case_pending,
                "current_trial_id": current_trial_id,
                "current_case_id": current_case_id,
                "started_at": started_at,
                "updated_at": _now(),
                "error": None,
            },
        )

    def _build_summary(
        self, experiment_id: str, exp_dir: Path, totals: RunTotals, resumed: bool
    ) -> Dict[str, Any]:
        ran = [r for r in totals.results if r.status != STATUS_SKIPPED]
        calls = sum(r.inference_calls for r in ran)
        wait = round(sum(r.ai_wait_seconds for r in ran), 3)
        elapsed = round(sum(r.elapsed_seconds for r in ran), 3)
        return {
            "experiment_id": experiment_id,
            "directory": str(exp_dir),
            "resumed": resumed,
            "case_count": len(ran),
            "skipped_count": totals.case_skipped,
            "done_count": totals.case_done,
            "failed_count": totals.case_failed,
            "invalid_count": sum(1 for r in ran if r.status == STATUS_DONE and not r.valid),
            "trial_complete_count": totals.trial_complete,
            "inference_calls": calls,
            "elapsed_seconds": elapsed,
            "ai_wait_seconds": wait,
            "seconds_per_call": seconds_per_call(wait, calls),
            "cases": [
                {
                    "case_id": r.case_id,
                    "status": r.status,
                    "winner": r.winner,
                    "valid": r.valid,
                    "attempt": r.attempt,
                    "error": r.error,
                }
                for r in totals.results
            ],
        }
