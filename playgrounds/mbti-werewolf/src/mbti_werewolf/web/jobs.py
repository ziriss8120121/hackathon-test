"""画面からの実験実行を1本に制限する（設計書8.3）。

推論待ちが大半なのでスレッドで足りる。同時に2本走らせるとローカルLLMのメモリを
食い潰し、待機時間の計測も汚れる。実行中の再要求は 409 にする。
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, Dict, Optional


class BusyError(Exception):
    """すでに実行中である。"""

    def __init__(self, experiment_id: Optional[str] = None) -> None:
        super().__init__("実行中の実験があります")
        self.experiment_id = experiment_id


class JobManager:
    def __init__(self, runs_dir: Path) -> None:
        self.runs_dir = Path(runs_dir)
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="mbti-run")
        self._busy = False
        self._current_id: Optional[str] = None

    def current_id(self) -> Optional[str]:
        with self._lock:
            if self._busy:
                return self._current_id
        return running_on_disk(self.runs_dir)

    def submit(
        self,
        experiment_id: str,
        fn: Callable[[], Any],
        prepare: Optional[Callable[[], None]] = None,
    ) -> None:
        """1本だけ受け付ける。ディスク上の CLI 実行も実行中とみなす。

        `prepare` はロックの内側で走らせる。開始用の status.json を先に書くと、
        そのファイル自身を実行中と誤認しないようにするためである。
        """

        with self._lock:
            disk_id = running_on_disk(self.runs_dir)
            if self._busy or disk_id:
                raise BusyError(self._current_id or disk_id)
            self._busy = True
            self._current_id = experiment_id
            if prepare is not None:
                prepare()
            self._executor.submit(self._run, fn)

    def _run(self, fn: Callable[[], Any]) -> None:
        try:
            fn()
        finally:
            with self._lock:
                self._busy = False
                self._current_id = None


def running_on_disk(runs_dir: Path) -> Optional[str]:
    """CLI から始めた実行も、status.json が running なら同時起動しない。"""

    if not runs_dir.is_dir():
        return None
    for path in sorted(runs_dir.iterdir()):
        status_path = path / "status.json"
        if not path.is_dir() or not status_path.is_file():
            continue
        try:
            import json

            payload: Dict[str, Any] = json.loads(status_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if payload.get("status") == "running":
            return str(payload.get("experiment_id") or path.name)
    return None
