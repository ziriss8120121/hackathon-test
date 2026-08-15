"""操作画面のためのローカルサーバー（設計書7.4、8.3）。

HTTPの受け付け、runs/ の読み取り、静的ファイルの配信だけを行う。ゲームのルールも
推論の呼び出しもここには持たない。

実行は単一ワーカーのスレッドで行い、実行中の再要求は 409 を返す。ローカルの
推論を並列に叩くとメモリを食い潰し、待機時間の計測も汚れるためである。
進捗はメモリではなく status.json に書くので、画面を再読み込みしても表示が復元できる。
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from ..config import Config, ConfigError, default_config_dict, load_config
from ..runner import Runner, make_run_id

STATIC_DIR = Path(__file__).resolve().parent / "static"


class RunInProgress(RuntimeError):
    """実行中に別の実行を要求されたことを表す。"""

    def __init__(self, series_id: str) -> None:
        super().__init__(series_id)
        self.series_id = series_id


class JobManager:
    """同時に1本だけ実行させるための管理（設計書8.3）。"""

    def __init__(self, runner: Runner) -> None:
        self._runner = runner
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._lock = threading.Lock()
        self._current: Optional[Dict[str, Any]] = None

    @property
    def current(self) -> Optional[Dict[str, Any]]:
        with self._lock:
            return dict(self._current) if self._current else None

    def start(self, config: Config) -> Dict[str, Any]:
        with self._lock:
            if self._current is not None:
                raise RunInProgress(self._current["series_id"])
            series_id = self._runner.create_series(config)
            job = {
                "series_id": series_id,
                "run_id": make_run_id(series_id, 1),
                "game_count": config.game_count,
            }
            self._current = job

        self._executor.submit(self._execute, series_id, config)
        return job

    def _execute(self, series_id: str, config: Config) -> None:
        try:
            self._runner.execute_series(series_id, config)
        finally:
            with self._lock:
                self._current = None

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False)


def create_app(runs_dir: Optional[Path] = None) -> FastAPI:
    runner = Runner(runs_dir)
    jobs = JobManager(runner)

    app = FastAPI(title="MBTI人狼シミュレーター", version="0.1.0")
    app.state.runner = runner
    app.state.jobs = jobs

    @app.get("/health")
    def health() -> Dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/config/default")
    def config_default() -> Dict[str, Any]:
        return default_config_dict()

    @app.post("/api/runs", status_code=202)
    def create_run(payload: Dict[str, Any] = Body(default_factory=dict)) -> JSONResponse:
        try:
            config = _build_config(payload)
        except ConfigError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        try:
            job = jobs.start(config)
        except RunInProgress as exc:
            raise HTTPException(
                status_code=409,
                detail="別の実行が進行中です（series_id: {}）。完了を待ってください。".format(
                    exc.series_id
                ),
            )

        return JSONResponse(
            status_code=202,
            content={
                "run_id": job["run_id"],
                "series_id": job["series_id"],
                "game_count": job["game_count"],
                "status": "queued",
            },
        )

    @app.get("/api/runs")
    def list_runs(limit: int = 100) -> Dict[str, Any]:
        return {
            "runs": runner.list_runs(limit=limit),
            "current": jobs.current,
        }

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str) -> Dict[str, Any]:
        status = runner.load_status(_safe_run_id(run_id))
        if status is None:
            raise HTTPException(status_code=404, detail="実行が見つかりません。")
        return status

    @app.get("/api/runs/{run_id}/log")
    def get_run_log(run_id: str) -> Dict[str, Any]:
        run_log = runner.load_run_log(_safe_run_id(run_id))
        if run_log is None:
            raise HTTPException(
                status_code=404, detail="run_log.json がまだありません。"
            )
        return run_log

    @app.get("/api/series/{series_id}")
    def get_series(series_id: str) -> Dict[str, Any]:
        series = runner.load_series(_safe_id(series_id))
        if series is None:
            raise HTTPException(status_code=404, detail="seriesが見つかりません。")
        return series

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    if runner.runs_dir.exists():
        # result.html を画面から開けるようにする。実行環境を持たないメンバーは
        # このサーバーを起動せず、ファイルを直接開く（要件NF-15）。
        app.mount("/runs", StaticFiles(directory=str(runner.runs_dir)), name="runs")

    return app


def _build_config(payload: Dict[str, Any]) -> Config:
    """画面のフォーム入力を最優先で反映した設定を作る（設計書8.2）。"""
    if not payload:
        return load_config()
    known = set(Config.__dataclass_fields__) | {"brain"}
    overrides = {key: value for key, value in payload.items() if key in known}
    return load_config(overrides=overrides)


def _safe_id(value: str) -> str:
    if "/" in value or "\\" in value or ".." in value:
        raise HTTPException(status_code=400, detail="IDの形式が不正です。")
    return value


def _safe_run_id(value: str) -> str:
    value = _safe_id(value)
    if "-r" not in value:
        raise HTTPException(status_code=400, detail="run_id の形式が不正です。")
    return value
