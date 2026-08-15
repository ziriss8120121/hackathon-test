"""実行の管理と出力の書き込み（設計書2.2、3.1、3.5、6.1）。

画面から実行してもコマンドから実行しても、通るのはこのモジュールである。
進捗をメモリ上の辞書ではなく status.json に書くため、CLIで実行した試合の進捗も
画面から見える。別々の登録処理を持たないことで、両経路で同じ実行と出力になる
（要件AC-16、NF-15）。

1試合だけの実行も1試合のseriesとして扱う。多試合実行と構造を分けないことで、
集計と一覧の処理を1本にできる。
"""

from __future__ import annotations

import csv
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from .brains.base import BrainError
from .brains.factory import create_brain
from .config import PROMPT_VERSION, Config, runs_root
from .engine.game import GameEngine, GameRecord
from .record.metrics import CSV_COLUMNS, csv_rows
from .record.result_view import render_result_html
from .record.run_log import build_run_log
from .record.series import render_series_summary
from .record.summary import render_summary
from .record.timeline import render_timeline

def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def new_series_id(runs_dir: Path, moment: Optional[datetime] = None) -> str:
    moment = moment or datetime.now()
    base = "s-{}".format(moment.strftime("%Y%m%d-%H%M%S"))
    series_id = base
    suffix = 2
    while (runs_dir / series_id).exists():
        series_id = "{}-{}".format(base, suffix)
        suffix += 1
    return series_id


def run_dir_name(run_index: int) -> str:
    return "r{:03d}".format(run_index)


def make_run_id(series_id: str, run_index: int) -> str:
    return "{}-{}".format(series_id, run_dir_name(run_index))


def split_run_id(run_id: str) -> Tuple[str, int]:
    """run_id から series_id と run_index を取り出す。

    run_id が series_id を含むため、APIは run_id だけで保存先を特定できる。
    """
    marker = run_id.rfind("-r")
    if marker == -1:
        raise ValueError("run_id の形式が不正です: {}".format(run_id))
    series_id = run_id[:marker]
    try:
        run_index = int(run_id[marker + 2 :])
    except ValueError:
        raise ValueError("run_id の形式が不正です: {}".format(run_id))
    return series_id, run_index


def write_text(path: Path, text: str) -> None:
    """書き込み途中のファイルを読まれないように、一時ファイル経由で置き換える。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, tmp_name = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as fp:
            fp.write(text)
        os.replace(tmp_name, str(path))
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


def write_json(path: Path, payload: Any) -> None:
    write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def read_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        with path.open(encoding="utf-8") as fp:
            return json.load(fp)
    except (FileNotFoundError, json.JSONDecodeError, ValueError):
        return None


class Runner:
    def __init__(self, runs_dir: Optional[Path] = None) -> None:
        self.runs_dir = Path(runs_dir) if runs_dir else runs_root()

    # --- パス ---------------------------------------------------------------

    def series_dir(self, series_id: str) -> Path:
        return self.runs_dir / series_id

    def run_dir(self, run_id: str) -> Path:
        series_id, run_index = split_run_id(run_id)
        return self.series_dir(series_id) / run_dir_name(run_index)

    # --- 実行の作成 ---------------------------------------------------------

    def create_series(self, config: Config) -> str:
        """series と各試合のディレクトリを先に作る。

        画面からの実行は 202 を即座に返すため、run_id と config.json、status.json は
        実行前に用意しておく。実行前から一覧に現れるので、待っている間も
        「受け付けられたこと」が画面から分かる（設計書3.1）。
        """
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        series_id = new_series_id(self.runs_dir)
        series_path = self.series_dir(series_id)
        series_path.mkdir(parents=True, exist_ok=True)

        started = now_iso()
        for run_index in range(1, config.game_count + 1):
            run_config = config.for_run(run_index)
            run_id = make_run_id(series_id, run_index)
            run_path = series_path / run_dir_name(run_index)
            run_path.mkdir(parents=True, exist_ok=True)
            write_json(run_path / "config.json", run_config.to_dict())
            write_json(
                run_path / "status.json",
                {
                    "run_id": run_id,
                    "series_id": series_id,
                    "status": "queued",
                    "phase": "setup",
                    "turn": 0,
                    "turn_count": run_config.turn_count,
                    "started_at": None,
                    "updated_at": started,
                    "error": None,
                },
            )

        write_json(
            series_path / "series.json",
            {
                "series_id": series_id,
                "status": "queued",
                "config": config.to_dict(),
                "game_count": config.game_count,
                "created_at": started,
                "started_at": None,
                "ended_at": None,
                "elapsed_seconds": 0.0,
                "ai_wait_seconds": 0.0,
                "success_count": 0,
                "failure_count": 0,
                "current_run_id": None,
                "runs": [],
            },
        )
        return series_id

    # --- 実行 ---------------------------------------------------------------

    def execute_series(
        self,
        series_id: str,
        config: Config,
        on_run_finished: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        """seriesの全試合を順番に実行する。

        1試合の失敗で全体を止めない。100試合のうち数試合が無料枠やタイムアウトで
        落ちても、残りの結果から傾向を読めるようにする（設計書3.5）。
        """
        series_path = self.series_dir(series_id)
        series = read_json(series_path / "series.json") or {}
        series.update({"status": "running", "started_at": now_iso()})
        write_json(series_path / "series.json", series)

        started = datetime.now()
        entries: List[Dict[str, Any]] = []
        run_logs: List[Dict[str, Any]] = []

        for run_index in range(1, config.game_count + 1):
            run_id = make_run_id(series_id, run_index)
            series["current_run_id"] = run_id
            write_json(series_path / "series.json", series)

            run_log = self.execute_run(series_id, run_index, config.for_run(run_index))
            run_logs.append(run_log)

            result = run_log.get("result") or {}
            entry = {
                "run_index": run_index,
                "run_id": run_id,
                "status": run_log.get("status"),
                "winner": result.get("winner"),
                "executed": result.get("executed"),
                "elapsed_seconds": (run_log.get("timing") or {}).get("elapsed_seconds"),
                "error_kind": (run_log.get("failure") or {}).get("kind"),
            }
            entries.append(entry)

            success = sum(1 for e in entries if e["status"] == "done")
            series.update(
                {
                    "runs": entries,
                    "success_count": success,
                    "failure_count": len(entries) - success,
                    "ai_wait_seconds": round(
                        sum(
                            (log.get("timing") or {}).get("ai_wait_seconds", 0.0)
                            for log in run_logs
                        ),
                        3,
                    ),
                }
            )
            write_json(series_path / "series.json", series)

            if on_run_finished is not None:
                on_run_finished(entry)

        success = sum(1 for e in entries if e["status"] == "done")
        if success == len(entries):
            status = "done"
        elif success == 0:
            status = "failed"
        else:
            status = "partial"

        series.update(
            {
                "status": status,
                "current_run_id": None,
                "ended_at": now_iso(),
                "elapsed_seconds": round(
                    (datetime.now() - started).total_seconds(), 3
                ),
            }
        )
        write_json(series_path / "series.json", series)
        write_text(
            series_path / "series_summary.md",
            render_series_summary(series, run_logs),
        )
        return series

    def execute_run(
        self, series_id: str, run_index: int, run_config: Config
    ) -> Dict[str, Any]:
        """1試合を実行し、出力ファイル一式を書く。"""
        run_id = make_run_id(series_id, run_index)
        run_path = self.series_dir(series_id) / run_dir_name(run_index)
        run_path.mkdir(parents=True, exist_ok=True)
        write_json(run_path / "config.json", run_config.to_dict())

        started_at = now_iso()
        started = datetime.now()

        def write_status(
            status: str,
            phase: str,
            turn: int,
            error: Optional[Dict[str, str]] = None,
        ) -> None:
            write_json(
                run_path / "status.json",
                {
                    "run_id": run_id,
                    "series_id": series_id,
                    "status": status,
                    "phase": phase,
                    "turn": turn,
                    "turn_count": run_config.turn_count,
                    "started_at": started_at,
                    "updated_at": now_iso(),
                    "error": error,
                },
            )

        write_status("running", "setup", 0)

        failure: Optional[Dict[str, Any]] = None
        status = "done"
        record = GameRecord()
        engine: Optional[GameEngine] = None
        brain_info: Dict[str, str] = {
            "provider": run_config.brain.provider,
            "model": run_config.brain.model,
            "endpoint_kind": "unknown",
            "name": run_config.brain.provider,
        }

        try:
            brain = create_brain(run_config)
            brain_info = brain.describe()
            engine = GameEngine(
                config=run_config,
                brain=brain,
                prompt_version=PROMPT_VERSION,
                on_progress=lambda phase, turn: write_status("running", phase, turn),
            )
            record = engine.run()
        except BrainError as exc:
            # 原因が判別できる形で終了し、部分結果を残す（要件NF-07、F-37）。
            status = "failed"
            failure = exc.to_dict()
            record = _partial(engine, record)
        except Exception as exc:  # 想定外の例外も部分結果を残して終了する
            status = "failed"
            failure = {"kind": "internal", "message": "{}: {}".format(type(exc).__name__, exc)}
            record = _partial(engine, record)

        ended = datetime.now()
        timing = {
            "started_at": started_at,
            "ended_at": now_iso(),
            "elapsed_seconds": round((ended - started).total_seconds(), 3),
            "ai_wait_seconds": round(record.ai_wait_seconds, 3),
            "machine_name": run_config.machine_name,
        }

        run_log = build_run_log(
            run_id=run_id,
            series_id=series_id,
            run_index=run_index,
            status=status,
            config=run_config,
            brain_info=brain_info,
            record=record,
            timing=timing,
            failure=failure,
        )

        write_json(run_path / "run_log.json", run_log)
        write_text(run_path / "summary.md", render_summary(run_log))
        write_text(run_path / "timeline.md", render_timeline(run_log))
        write_text(run_path / "result.html", render_result_html(run_log))
        _write_metrics_csv(run_path / "metrics.csv", run_log)
        write_text(
            self.runs_dir / "latest.html",
            _render_latest_redirect(run_id, "{}/{}/result.html".format(series_id, run_dir_name(run_index))),
        )

        write_status(
            status,
            record.phase,
            run_config.turn_count if status == "done" else _last_turn(record),
            error=failure,
        )
        return run_log

    def run_series(self, config: Config) -> Tuple[str, Dict[str, Any]]:
        """create_series と execute_series をまとめて行う（CLI用）。"""
        series_id = self.create_series(config)
        return series_id, self.execute_series(series_id, config)

    # --- 読み取り -----------------------------------------------------------

    def load_status(self, run_id: str) -> Optional[Dict[str, Any]]:
        return read_json(self.run_dir(run_id) / "status.json")

    def load_run_log(self, run_id: str) -> Optional[Dict[str, Any]]:
        return read_json(self.run_dir(run_id) / "run_log.json")

    def load_series(self, series_id: str) -> Optional[Dict[str, Any]]:
        return read_json(self.series_dir(series_id) / "series.json")

    def list_runs(self, limit: int = 200) -> List[Dict[str, Any]]:
        """runs/ を走査して実行の一覧を作る（設計書7.4）。

        一覧をディレクトリの走査で作るため、コマンドから実行した結果も
        画面の一覧に現れる。
        """
        if not self.runs_dir.exists():
            return []

        items: List[Dict[str, Any]] = []
        for series_path in sorted(self.runs_dir.iterdir(), reverse=True):
            if not series_path.is_dir() or not series_path.name.startswith("s-"):
                continue
            series = read_json(series_path / "series.json") or {}
            by_run_id = {
                entry.get("run_id"): entry for entry in series.get("runs") or []
            }

            for run_path in sorted(series_path.iterdir()):
                if not run_path.is_dir():
                    continue
                status = read_json(run_path / "status.json")
                if status is None:
                    continue
                run_id = status.get("run_id", "")
                entry = by_run_id.get(run_id) or {}
                items.append(
                    {
                        "run_id": run_id,
                        "series_id": series.get("series_id", series_path.name),
                        "status": status.get("status"),
                        "phase": status.get("phase"),
                        "turn": status.get("turn"),
                        "turn_count": status.get("turn_count"),
                        "started_at": status.get("started_at")
                        or status.get("updated_at"),
                        "winner": entry.get("winner"),
                        "executed": entry.get("executed"),
                        "elapsed_seconds": entry.get("elapsed_seconds"),
                        "error_kind": (status.get("error") or {}).get("kind")
                        if status.get("error")
                        else entry.get("error_kind"),
                        "provider": (series.get("config") or {})
                        .get("brain", {})
                        .get("provider"),
                    }
                )
                if len(items) >= limit:
                    return items
        return items


_LATEST_TEMPLATE = """<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="0; url=./__TARGET__">
<title>MBTI人狼 最新の結果</title>
<style>
body { font-family: "Hiragino Sans", "Noto Sans JP", system-ui, sans-serif; background: #12141a; color: #e6e8ee;
  display: flex; align-items: center; justify-content: center; min-height: 100vh; margin: 0; padding: 24px; }
a { color: #7aa2f7; }
</style>
</head>
<body>
<p>最新の実行結果（<code>__RUN_ID__</code>）へ移動します。自動で切り替わらない場合は
<a href="./__TARGET__">こちらをタップ</a>してください。</p>
</body>
</html>
"""


def _render_latest_redirect(run_id: str, target: str) -> str:
    """最新の result.html への自己完結リダイレクトページ（v1改善：スマホからの共有用）。

    メタリフレッシュに対応しないブラウザ（LINEアプリ内ブラウザなど）向けに、
    手動リンクも必ず添える。
    """
    return _LATEST_TEMPLATE.replace("__TARGET__", target).replace("__RUN_ID__", run_id)


def _partial(engine: Any, fallback: GameRecord) -> GameRecord:
    if engine is None:
        return fallback
    record = engine.partial_record()
    record.phase = "failed"
    return record


def _last_turn(record: GameRecord) -> int:
    return record.turns[-1]["turn"] if record.turns else 0


def _write_metrics_csv(path: Path, run_log: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, tmp_name = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="") as fp:
            writer = csv.writer(fp)
            writer.writerow(CSV_COLUMNS)
            writer.writerows(csv_rows(run_log))
        os.replace(tmp_name, str(path))
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise
