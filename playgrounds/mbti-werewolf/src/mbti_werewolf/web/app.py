"""操作画面のAPI（設計書7.4、8.3）。

画面は runs/ を読む薄い層にする。分析値は analyze が書いたファイルだけを返し、
ここで算出しない。コマンドから実行した結果も同じ一覧に現れる。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..config import ConfigError, load_config
from ..experiment import default_data_dir, make_experiment_id
from ..judge.judge import judge_file_name
from ..record.case_log import write_json
from ..runner import ExperimentRunner, ResumeError, default_runs_dir, STATUS_RUNNING
from .jobs import BusyError, JobManager

STATIC_DIR = Path(__file__).resolve().parent / "static"
ANALYSIS_KINDS = {
    "experiment": "experiment.html",
    "rq1": "rq1.html",
    "rq2": "rq2.html",
}
_EMBED_RE = re.compile(
    r'<script type="application/json" id="analysis-data">(.*?)</script>',
    re.DOTALL,
)


def create_app(
    data_dir: Optional[Path] = None,
    runs_dir: Optional[Path] = None,
):
    """テストから runs_dir を差し替えられるようにアプリを関数で作る。"""

    try:
        from fastapi import FastAPI, HTTPException
        from fastapi.responses import FileResponse, JSONResponse
        from fastapi.staticfiles import StaticFiles
    except ImportError:
        raise RuntimeError(
            "fastapi が入っていません。pip install fastapi uvicorn を実行してください。"
        )

    data_root = Path(data_dir) if data_dir else default_data_dir()
    runs_root = Path(runs_dir) if runs_dir else default_runs_dir()
    runs_root.mkdir(parents=True, exist_ok=True)
    jobs = JobManager(runs_root)

    app = FastAPI(title="MBTI人狼", docs_url=None, redoc_url=None)
    app.state.data_dir = data_root
    app.state.runs_dir = runs_root
    app.state.jobs = jobs

    @app.get("/health")
    def health() -> Dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/config/default")
    def default_config() -> Dict[str, Any]:
        # config/default.json はM3で削除した。既定値は config.py が持つ（設計書8.2）。
        return load_config().to_dict()

    @app.get("/api/data/pools")
    def list_pools() -> List[Dict[str, Any]]:
        return _list_json_dir(
            data_root / "persons",
            id_key="pool_id",
            extra=lambda raw: {
                "count": raw.get("count") or len(raw.get("persons") or []),
                "composition": raw.get("composition") or {},
            },
        )

    @app.get("/api/data/patterns")
    def list_patterns() -> List[Dict[str, Any]]:
        return _list_json_dir(
            data_root / "patterns",
            id_key="pattern_set_id",
            extra=lambda raw: {
                "pool_id": raw.get("pool_id"),
                "count": len(raw.get("patterns") or []),
            },
        )

    @app.get("/api/data/rules")
    def list_rules() -> List[Dict[str, Any]]:
        return _list_json_dir(
            data_root / "rules",
            id_key="rule_set_id",
            extra=lambda raw: {
                "rule_set_version": raw.get("rule_set_version"),
                "status": raw.get("status") or "active",
            },
        )

    @app.get("/api/experiments")
    def list_experiments() -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        for path in _experiment_dirs(runs_root):
            status = _read_json(path / "status.json") or {}
            experiment = _read_json(path / "experiment.json") or {}
            items.append(
                {
                    "experiment_id": path.name,
                    "status": status.get("status") or "unknown",
                    "trial_total": status.get("trial_total")
                    or len(experiment.get("trial_ids") or []),
                    "trial_complete": status.get("trial_complete"),
                    "case_done": status.get("case_done"),
                    "case_total": status.get("case_total") or experiment.get("case_count"),
                    "started_at": status.get("started_at") or "",
                    "current_trial_id": status.get("current_trial_id"),
                    "current_case_id": status.get("current_case_id"),
                }
            )
        items.sort(key=lambda item: item["started_at"] or item["experiment_id"], reverse=True)
        return items

    @app.post("/api/experiments")
    def start_experiment(body: Optional[Dict[str, Any]] = None):
        payload = dict(body or {})
        case_filter = _case_filter(payload.pop("cases", None))
        case_attempts = payload.pop("case_attempts", None)
        try:
            config = load_config(overrides=payload)
        except (ConfigError, ValueError, TypeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        experiment_id = make_experiment_id()
        runner = ExperimentRunner(
            config,
            data_dir=data_root,
            runs_dir=runs_root,
            case_filter=case_filter,
            case_attempts=int(case_attempts) if case_attempts else 2,
        )

        def prepare() -> None:
            exp_dir = runs_root / experiment_id
            exp_dir.mkdir(parents=True, exist_ok=True)
            write_json(
                exp_dir / "experiment.json",
                {
                    "schema_version": "2",
                    "experiment_id": experiment_id,
                    "config": config.to_dict(),
                    "rule_set_id": config.rule_set_id,
                    "trial_ids": [],
                    "case_count": 0,
                },
            )
            write_json(
                exp_dir / "status.json",
                {
                    "experiment_id": experiment_id,
                    "status": STATUS_RUNNING,
                    "trial_total": 0,
                    "case_total": 0,
                    "case_done": 0,
                    "started_at": "",
                },
            )

        try:
            jobs.submit(
                experiment_id,
                lambda: runner.run(experiment_id=experiment_id),
                prepare=prepare,
            )
        except BusyError as exc:
            return JSONResponse(
                {"experiment_id": exc.experiment_id, "status": "running"},
                status_code=409,
            )
        return JSONResponse(
            {"experiment_id": experiment_id, "status": "running"},
            status_code=202,
        )

    @app.get("/api/experiments/{experiment_id}")
    def get_experiment(experiment_id: str) -> Dict[str, Any]:
        exp_dir = _require_experiment(runs_root, experiment_id)
        status = _read_json(exp_dir / "status.json") or {}
        experiment = _read_json(exp_dir / "experiment.json") or {}
        status["experiment_id"] = experiment_id
        status["config"] = experiment.get("config")
        status["trial_ids"] = experiment.get("trial_ids") or []
        return status

    @app.post("/api/experiments/{experiment_id}/resume")
    def resume_experiment(experiment_id: str):
        exp_dir = _require_experiment(runs_root, experiment_id)
        experiment = _read_json(exp_dir / "experiment.json") or {}
        config_raw = experiment.get("config") or {}
        try:
            config = load_config(overrides=config_raw)
        except (ConfigError, ValueError, TypeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        runner = ExperimentRunner(config, data_dir=data_root, runs_dir=runs_root)
        try:
            jobs.submit(experiment_id, lambda: runner.resume(experiment_id))
        except BusyError as exc:
            return JSONResponse(
                {"experiment_id": exc.experiment_id, "status": "running"},
                status_code=409,
            )
        except ResumeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(
            {"experiment_id": experiment_id, "status": "running"}, status_code=202
        )

    @app.get("/api/experiments/{experiment_id}/trials")
    def list_trials(experiment_id: str) -> List[Dict[str, Any]]:
        exp_dir = _require_experiment(runs_root, experiment_id)
        items: List[Dict[str, Any]] = []
        for trial_dir in _trial_dirs(exp_dir):
            trial = _read_json(trial_dir / "trial.json") or {}
            status = _read_json(trial_dir / "status.json") or {}
            items.append(
                {
                    "trial_id": trial.get("trial_id") or trial_dir.name,
                    "trial_index": trial.get("trial_index"),
                    "complete": status.get("complete", trial.get("complete")),
                    "status": status.get("status"),
                    "case_done": status.get("case_done"),
                    "case_failed": status.get("case_failed"),
                    "case_total": status.get("case_total") or len(trial.get("cases") or []),
                    "cases": trial.get("cases") or [],
                }
            )
        return items

    @app.get("/api/experiments/{experiment_id}/analysis/{kind}")
    def get_analysis(experiment_id: str, kind: str) -> Dict[str, Any]:
        if kind not in ANALYSIS_KINDS:
            raise HTTPException(status_code=404, detail="未知の分析種別です")
        exp_dir = _require_experiment(runs_root, experiment_id)
        path = exp_dir / ANALYSIS_KINDS[kind]
        if not path.is_file():
            return {"status": "missing", "kind": kind, "experiment_id": experiment_id}
        payload = _embedded_json(path)
        if payload is None:
            return {"status": "missing", "kind": kind, "experiment_id": experiment_id}
        payload["status"] = "ready"
        payload["kind"] = kind
        return payload

    @app.get("/api/trials/{trial_id}")
    def get_trial(trial_id: str) -> Dict[str, Any]:
        trial_dir = _require_trial(runs_root, trial_id)
        trial = _read_json(trial_dir / "trial.json")
        if trial is None:
            raise HTTPException(status_code=404, detail="Trialの記録がありません")
        status = _read_json(trial_dir / "status.json") or {}
        trial["status"] = status
        cases = []
        for case in trial.get("cases") or []:
            case_id = case.get("case_id")
            case_dir = _case_dir_for(trial_dir, case_id) if case_id else None
            case_status = _read_json(case_dir / "status.json") if case_dir else None
            row = dict(case)
            if case_status:
                row["status"] = case_status.get("status", row.get("status"))
                row["error"] = case_status.get("error")
            if case_dir:
                row["dir_name"] = case_dir.name
                row["result_href"] = "/runs/{0}/{1}/{2}/result.html".format(
                    trial_dir.parent.name, trial_dir.name, case_dir.name
                )
            cases.append(row)
        trial["cases"] = cases
        return trial

    @app.get("/api/cases/{case_id}")
    def get_case(case_id: str) -> Dict[str, Any]:
        case_dir = _require_case(runs_root, case_id)
        status = _read_json(case_dir / "status.json") or {}
        status["case_id"] = case_id
        status["result_href"] = "/runs/{0}/{1}/{2}/result.html".format(
            case_dir.parent.parent.name, case_dir.parent.name, case_dir.name
        )
        return status

    @app.get("/api/cases/{case_id}/log")
    def get_case_log(case_id: str) -> Dict[str, Any]:
        case_dir = _require_case(runs_root, case_id)
        log = _read_json(case_dir / "case_log.json")
        if log is None:
            raise HTTPException(status_code=404, detail="ケースログがまだありません")
        return log

    @app.get("/api/cases/{case_id}/judge")
    def get_case_judge(case_id: str, version: str = "v1") -> Dict[str, Any]:
        case_dir = _require_case(runs_root, case_id)
        payload = _read_json(case_dir / judge_file_name(version))
        if payload is None:
            return {"status": "missing", "case_id": case_id, "version": version}
        payload["status"] = "ready"
        return payload

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    if STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    app.mount("/runs", StaticFiles(directory=str(runs_root), html=True), name="runs")
    return app


def _list_json_dir(directory: Path, id_key: str, extra) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    if not directory.is_dir():
        return items
    for path in sorted(directory.glob("*.json")):
        raw = _read_json(path)
        if raw is None:
            continue
        row = {id_key: raw.get(id_key) or path.stem}
        row.update(extra(raw))
        items.append(row)
    return items


def _experiment_dirs(runs_dir: Path) -> List[Path]:
    if not runs_dir.is_dir():
        return []
    return sorted(
        path
        for path in runs_dir.iterdir()
        if path.is_dir() and (path / "experiment.json").is_file()
    )


def _trial_dirs(exp_dir: Path) -> List[Path]:
    return sorted(
        path
        for path in exp_dir.iterdir()
        if path.is_dir() and (path / "trial.json").is_file()
    )


def _require_experiment(runs_dir: Path, experiment_id: str) -> Path:
    path = runs_dir / experiment_id
    if not path.is_dir() or not (path / "experiment.json").is_file():
        raise _http_404("実験がありません: {0}".format(experiment_id))
    return path


def _require_trial(runs_dir: Path, trial_id: str) -> Path:
    exp_id, index = _split_trial_id(trial_id)
    if exp_id is None:
        raise _http_404("Trial IDが不正です: {0}".format(trial_id))
    path = runs_dir / exp_id / "t{0}".format(index)
    if not path.is_dir():
        raise _http_404("Trialがありません: {0}".format(trial_id))
    return path


def _require_case(runs_dir: Path, case_id: str) -> Path:
    trial_id, index = _split_case_id(case_id)
    if trial_id is None:
        raise _http_404("ケースIDが不正です: {0}".format(case_id))
    trial_dir = _require_trial(runs_dir, trial_id)
    case_dir = _case_dir_for(trial_dir, case_id)
    if case_dir is None:
        raise _http_404("ケースがありません: {0}".format(case_id))
    return case_dir


def _split_trial_id(trial_id: str):
    if "-t" not in trial_id:
        return None, None
    exp_id, _, index = trial_id.rpartition("-t")
    if not exp_id or not index.isdigit():
        return None, None
    return exp_id, index


def _split_case_id(case_id: str):
    if "-c" not in case_id:
        return None, None
    trial_id, _, index = case_id.rpartition("-c")
    if not trial_id or not index.isdigit():
        return None, None
    return trial_id, index


def _case_dir_for(trial_dir: Path, case_id: str) -> Optional[Path]:
    _trial_id, index = _split_case_id(case_id)
    if index is None:
        return None
    matches = sorted(trial_dir.glob("c{0}-*".format(index)))
    return matches[0] if matches else None


def _case_filter(value: Any) -> Optional[List[str]]:
    if not value:
        return None
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [part.strip() for part in str(value).split(",") if part.strip()]


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _embedded_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    match = _EMBED_RE.search(text)
    if not match:
        return None
    try:
        payload = json.loads(match.group(1))
    except ValueError:
        return None
    return payload if isinstance(payload, dict) else None


def _http_404(detail: str):
    from fastapi import HTTPException

    return HTTPException(status_code=404, detail=detail)
