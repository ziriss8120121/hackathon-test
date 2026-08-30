"""発言単位の事後評価（設計書3.4、5.5、6.8）。

ゲーム実行とは別のコマンドで動く。入力は `case_log.json` だけで、`engine` にも
`agents` にも依存しない。1,700ケースの実行には日単位の時間がかかるため、評価
基準を変えるたびにゲームを回し直す構成にはしない（F-41、F-45、NF-18）。

Judgeへ役職・最終役職・MBTI・個別判断・投票・勝敗を渡さない。正解を知った評価に
すると公開会話から読み取れる内容の評価にならず、またMBTI条件と評価が循環参照に
なるためである（3.4、F-46）。渡す情報をこのモジュールの中だけで組み立てることで、
その制約を1か所に閉じている。
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from string import Template
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from ..brains.base import Request
from . import stance as stance_module

SCHEMA_VERSION = "2"
DEFAULT_CRITERIA_VERSION = "v1"
DEFAULT_BATCH_SIZE = 8

#: 1バッチあたりの問い合わせ回数の上限。`speech_id` の対応が取れない応答を
#: 送り直す回数であり、通信の再試行（`max_transport_retries`）とは別である。
#: 途中の応答で取れた分は保持するので、送り直すのは欠けている発言だけになる。
DEFAULT_BATCH_ATTEMPTS = 3

_GENDER_LABELS = {"male": "男性", "female": "女性"}


class JudgeError(Exception):
    """評価基準が読めない、または評価の入力が揃っていない。"""


def criteria_dir(version: str = DEFAULT_CRITERIA_VERSION) -> Path:
    return Path(__file__).resolve().parent / "criteria" / version


def judge_file_name(version: str = DEFAULT_CRITERIA_VERSION) -> str:
    """版をファイル名に含める。`v2` にしても `v1` の評価が残る（F-45）。"""

    return "judge.{0}.json".format(version)


def _upper(player_id: str) -> str:
    return str(player_id).upper()


def _internal(value: object) -> str:
    return str(value).strip().lower()


class Criteria:
    """`judge/criteria/{version}/` の評価基準（設計書5.5）。

    プロンプトの生成と応答の検証が同じ `labels.json` を見る。片方だけを直して
    定義がずれることを防ぐため、ラベルの一覧をコードへ書かない。
    """

    def __init__(self, version: str = DEFAULT_CRITERIA_VERSION) -> None:
        self.version = version
        self._dir = criteria_dir(version)
        if not self._dir.is_dir():
            raise JudgeError("評価基準のディレクトリがない: {0}".format(self._dir))

        raw = json.loads((self._dir / "labels.json").read_text(encoding="utf-8"))
        self._labels: Tuple[Dict[str, str], ...] = tuple(raw["labels"])
        self.labels: Tuple[str, ...] = tuple(item["name"] for item in self._labels)
        self.fallback_label: str = str(raw.get("fallback_label", "other"))
        if self.fallback_label not in self.labels:
            raise JudgeError(
                "fallback_label がラベル一覧にない: {0}".format(self.fallback_label)
            )
        self._directions: Tuple[Dict[str, str], ...] = tuple(raw["stance"]["directions"])
        self.directions: Tuple[str, ...] = tuple(
            item["name"] for item in self._directions
        )
        self._strengths: Tuple[Dict[str, Any], ...] = tuple(raw["stance"]["strengths"])
        self.strengths: Tuple[int, ...] = tuple(
            int(item["value"]) for item in self._strengths
        )

    def _read(self, name: str) -> Template:
        path = self._dir / "{0}.md".format(name)
        if not path.is_file():
            raise JudgeError("評価基準のファイルがない: {0}".format(path))
        return Template(path.read_text(encoding="utf-8"))

    def system_prompt(self) -> str:
        return self._read("system_judge").safe_substitute(
            label_definitions="\n".join(
                "- {0}: {1}".format(item["name"], item["definition"])
                for item in self._labels
            ),
            direction_definitions=" / ".join(
                "{0}（{1}）".format(item["name"], item["definition"])
                for item in self._directions
            ),
            strength_definitions=" / ".join(
                "{0}（{1}）".format(item["value"], item["definition"])
                for item in self._strengths
            ),
        )

    def render_user(self, **values: object) -> str:
        return self._read("user_judge").safe_substitute(**values)


@dataclass
class SpeechEvaluation:
    """1発言の評価。`speech_id` と1対1に対応する（設計書6.8）。"""

    speech_id: str
    labels: List[str] = field(default_factory=list)
    mentions: List[str] = field(default_factory=list)
    stances: List[Dict[str, Any]] = field(default_factory=list)
    parse_failed: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "speech_id": self.speech_id,
            "labels": list(self.labels),
            "mentions": list(self.mentions),
            "stances": [dict(s) for s in self.stances],
            "parse_failed": self.parse_failed,
        }


def spoken_events(case_log: Dict[str, Any]) -> List[Dict[str, Any]]:
    """評価の対象になる発言（設計書6.7）。

    見送りとスキップには `speech_id` が振られていないため対象外になる。
    """

    events = case_log.get("discussion", {}).get("events", [])
    return [e for e in events if e.get("spoke") and e.get("speech_id")]


class CaseJudge:
    """1ケースを評価して `judge.{version}.json` の中身を作る。"""

    def __init__(
        self,
        brain,
        criteria: Optional[Criteria] = None,
        batch_size: int = DEFAULT_BATCH_SIZE,
        batch_attempts: int = DEFAULT_BATCH_ATTEMPTS,
    ) -> None:
        self.brain = brain
        self.criteria = criteria or Criteria()
        self.batch_size = max(1, batch_size)
        self.batch_attempts = max(1, batch_attempts)

    # --- 評価 -----------------------------------------------------------------

    def evaluate(self, case_log: Dict[str, Any]) -> Dict[str, Any]:
        players = list(case_log.get("players", []))
        if not players:
            raise JudgeError("参加者がいないケースは評価できない")

        player_ids = [str(p["player_id"]) for p in players]
        speeches = spoken_events(case_log)
        speakers = {s["speech_id"]: str(s["player_id"]) for s in speeches}

        started = time.perf_counter()
        wait_seconds = 0.0
        inference_calls = 0
        found: Dict[str, SpeechEvaluation] = {}

        for batch in _batches(speeches, self.batch_size):
            evaluations, wait, calls = self._evaluate_batch(
                batch, speeches, players, player_ids, speakers
            )
            found.update(evaluations)
            wait_seconds += wait
            inference_calls += calls

        results: List[SpeechEvaluation] = []
        for speech in speeches:
            speech_id = speech["speech_id"]
            results.append(
                found.get(speech_id)
                # 上限まで送り直しても対応が取れなかった発言。評価を捏造せず、
                # 評価できなかったことを残す（設計書6.8）。
                or SpeechEvaluation(speech_id=speech_id, parse_failed=True)
            )

        stances_by_speech = {r.speech_id: r.stances for r in results}
        series = stance_module.derive_stance_series(
            speeches, stances_by_speech, player_ids
        )

        return {
            "schema_version": SCHEMA_VERSION,
            "case_id": case_log["case_id"],
            "judge_criteria_version": self.criteria.version,
            "judge_brain": _describe(self.brain),
            "judge_batch_size": self.batch_size,
            "evaluated_at": _now(),
            "speeches": [r.to_dict() for r in results],
            "stance_series": series,
            "timing": {
                "elapsed_seconds": round(time.perf_counter() - started, 3),
                "ai_wait_seconds": round(wait_seconds, 3),
                "inference_calls": inference_calls,
            },
        }

    # --- 1バッチ ---------------------------------------------------------------

    def _evaluate_batch(
        self,
        batch: Sequence[Dict[str, Any]],
        all_speeches: Sequence[Dict[str, Any]],
        players: Sequence[Dict[str, Any]],
        player_ids: Sequence[str],
        speakers: Dict[str, str],
    ) -> Tuple[Dict[str, SpeechEvaluation], float, int]:
        pending = {s["speech_id"] for s in batch}
        found: Dict[str, SpeechEvaluation] = {}
        wait_seconds = 0.0
        calls = 0

        request = Request(
            system=self.criteria.system_prompt(),
            user=self.criteria.render_user(
                participants=_participants_text(players),
                transcript=_transcript_text(all_speeches, batch[-1]["speech_id"]),
                batch=_batch_text(batch),
                batch_count=len(batch),
            ),
            expect_keys=("evaluations",),
            choices=tuple(_upper(pid) for pid in player_ids),
            subjects=tuple(s["speech_id"] for s in batch),
            tag="judge:{0}".format(batch[0]["speech_id"]),
        )

        for _ in range(self.batch_attempts):
            response = self.brain.generate(request)
            calls += 1
            wait_seconds += response.wait_seconds

            for entry in _entries(response.data):
                evaluation = self._normalize(entry, pending, player_ids, speakers)
                if evaluation is None:
                    continue
                found[evaluation.speech_id] = evaluation
                pending.discard(evaluation.speech_id)

            # 取れた分は保持するので、次の問い合わせで欠けが埋まればそこで終わる。
            if not pending:
                break

        return found, wait_seconds, calls

    def _normalize(
        self,
        entry: Any,
        pending: Sequence[str],
        player_ids: Sequence[str],
        speakers: Dict[str, str],
    ) -> Optional[SpeechEvaluation]:
        """1件の評価を検証して内部表記へ揃える。

        `speech_id` が対応しない項目は捨てる。モデルがIDを作り出した場合に、
        存在しない発言の評価が混ざらないようにするためである（AC-06）。
        """

        if not isinstance(entry, dict):
            return None
        speech_id = str(entry.get("speech_id", "")).strip()
        if speech_id not in pending:
            return None

        known = set(player_ids)
        speaker = speakers.get(speech_id)

        labels = _unique(
            _internal(value)
            for value in _as_list(entry.get("labels"))
            if _internal(value) in self.criteria.labels
        )
        if not labels:
            labels = [self.criteria.fallback_label]

        mentions = _unique(
            _internal(value)
            for value in _as_list(entry.get("mentions"))
            if _internal(value) in known
        )

        stances: List[Dict[str, Any]] = []
        for raw in _as_list(entry.get("stances")):
            stance = self._normalize_stance(raw, known, speaker)
            if stance is not None:
                stances.append(stance)

        return SpeechEvaluation(
            speech_id=speech_id, labels=labels, mentions=mentions, stances=stances
        )

    def _normalize_stance(
        self, raw: Any, known: Sequence[str], speaker: Optional[str]
    ) -> Optional[Dict[str, Any]]:
        """対象・向き・強度が揃ったスタンスだけを残す。

        対象が空のスタンス、および発言者自身へ向いたスタンスは落とす。どちらも
        疑念分布の対象にならず、残しても各人1件の正規化（5.5）で使えないためである。
        """

        if not isinstance(raw, dict):
            return None
        target = _internal(raw.get("target"))
        if target not in known or target == speaker:
            return None
        direction = _internal(raw.get("direction"))
        if direction not in self.criteria.directions:
            return None
        try:
            strength = int(str(raw.get("strength")).strip())
        except (TypeError, ValueError):
            return None
        if strength not in self.criteria.strengths:
            return None
        return {"target": target, "direction": direction, "strength": strength}


# --- プロンプトの素材 ---------------------------------------------------------


def _participants_text(players: Sequence[Dict[str, Any]]) -> str:
    """参加者一覧。役職とMBTIは載せない（設計書5.5の「渡さない情報」）。"""

    return "\n".join(
        "- {0}: {1}歳 / {2}".format(
            _upper(p["player_id"]),
            p["age"],
            _GENDER_LABELS.get(p.get("gender"), p.get("gender")),
        )
        for p in players
    )


def _transcript_text(
    speeches: Sequence[Dict[str, Any]], last_speech_id: str
) -> str:
    """そのバッチの最後の発言までの会話全文（設計書5.5）。

    要約せずに渡す。あとの発言を見せないのは、評価が後知恵にならないようにする
    ためである。
    """

    lines: List[str] = []
    for index, speech in enumerate(speeches, start=1):
        lines.append(
            "{0}. {1}: {2}".format(
                index, _upper(speech["player_id"]), speech.get("speech_text", "")
            )
        )
        if speech["speech_id"] == last_speech_id:
            break
    return "\n".join(lines) if lines else "（発言はありません）"


def _batch_text(batch: Sequence[Dict[str, Any]]) -> str:
    return "\n".join(
        "- {0} / {1}: {2}".format(
            speech["speech_id"], _upper(speech["player_id"]), speech.get("speech_text", "")
        )
        for speech in batch
    )


# --- 小物 ---------------------------------------------------------------------


def _batches(
    items: Sequence[Dict[str, Any]], size: int
) -> List[List[Dict[str, Any]]]:
    return [list(items[i : i + size]) for i in range(0, len(items), size)]


def _entries(data: Optional[Dict[str, Any]]) -> List[Any]:
    if not isinstance(data, dict):
        return []
    value = data.get("evaluations")
    return list(value) if isinstance(value, list) else []


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def _unique(values) -> List[str]:
    seen: List[str] = []
    for value in values:
        if value not in seen:
            seen.append(value)
    return seen


def _describe(brain) -> Dict[str, str]:
    describe = getattr(brain, "describe", None)
    return dict(describe()) if callable(describe) else {}


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


# --- 実験の走査 ---------------------------------------------------------------


@dataclass
class JudgeSummary:
    experiment_id: str
    directory: Path
    target_count: int = 0
    done_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    inference_calls: int = 0
    elapsed_seconds: float = 0.0
    failures: List[Dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "directory": str(self.directory),
            "target_count": self.target_count,
            "done_count": self.done_count,
            "failed_count": self.failed_count,
            "skipped_count": self.skipped_count,
            "inference_calls": self.inference_calls,
            "elapsed_seconds": round(self.elapsed_seconds, 3),
            "failures": [dict(f) for f in self.failures],
        }


class ExperimentJudge:
    """実験1件のケースを走査して評価する（設計書3.4）。

    `runs/` を直接読み書きし、Runnerを経由しない。ゲーム実行が終わったケースに
    対して評価だけを何度でも回せるようにするためである。
    """

    def __init__(
        self,
        runs_dir: Path,
        brain_factory: Callable[[], Any],
        criteria: Optional[Criteria] = None,
        batch_size: int = DEFAULT_BATCH_SIZE,
        batch_attempts: int = DEFAULT_BATCH_ATTEMPTS,
        on_progress: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.runs_dir = Path(runs_dir)
        self.brain_factory = brain_factory
        self.criteria = criteria or Criteria()
        self.batch_size = batch_size
        self.batch_attempts = batch_attempts
        self._on_progress = on_progress or (lambda _message: None)

    def case_dirs(self, experiment_id: str) -> List[Path]:
        exp_dir = self.runs_dir / experiment_id
        if not exp_dir.is_dir():
            raise JudgeError("実験のディレクトリがない: {0}".format(exp_dir))
        dirs: List[Path] = []
        for trial_dir in sorted(
            d for d in exp_dir.iterdir() if d.is_dir() and (d / "trial.json").is_file()
        ):
            dirs.extend(
                sorted(
                    d
                    for d in trial_dir.iterdir()
                    if d.is_dir() and (d / "case_log.json").is_file()
                )
            )
        return dirs

    def targets(self, experiment_id: str, force: bool = False) -> List[Path]:
        """評価するケース。既に同じ版の評価があるものは対象外にする（設計書5.5）。"""

        name = judge_file_name(self.criteria.version)
        if force:
            return self.case_dirs(experiment_id)
        return [d for d in self.case_dirs(experiment_id) if not (d / name).is_file()]

    def run(self, experiment_id: str, force: bool = False) -> Dict[str, Any]:
        exp_dir = self.runs_dir / experiment_id
        summary = JudgeSummary(experiment_id=experiment_id, directory=exp_dir)
        all_dirs = self.case_dirs(experiment_id)
        targets = self.targets(experiment_id, force=force)
        summary.target_count = len(targets)
        summary.skipped_count = len(all_dirs) - len(targets)
        name = judge_file_name(self.criteria.version)
        started = time.perf_counter()

        for case_dir in targets:
            try:
                case_log = json.loads(
                    (case_dir / "case_log.json").read_text(encoding="utf-8")
                )
            except (json.JSONDecodeError, ValueError, OSError) as exc:
                summary.failed_count += 1
                summary.failures.append({"case": case_dir.name, "message": str(exc)})
                self._on_progress("{0}: case_log.json を読めない".format(case_dir.name))
                continue

            if case_log.get("status") != "done":
                summary.target_count -= 1
                summary.skipped_count += 1
                continue

            try:
                # ケースごとに脳を作る。Stubは呼び出し順で出力が決まるため、
                # ケース間で状態を共有すると評価が実行順に依存する。
                judge = CaseJudge(
                    self.brain_factory(),
                    criteria=self.criteria,
                    batch_size=self.batch_size,
                    batch_attempts=self.batch_attempts,
                )
                payload = judge.evaluate(case_log)
            except Exception as exc:  # noqa: BLE001 - 1ケースの失敗で全体を止めない
                summary.failed_count += 1
                summary.failures.append(
                    {
                        "case": case_dir.name,
                        "kind": getattr(exc, "kind", "internal"),
                        "message": str(exc),
                    }
                )
                self._on_progress("{0}: 評価に失敗（{1}）".format(case_dir.name, exc))
                continue

            _write_json(case_dir / name, payload)
            summary.done_count += 1
            summary.inference_calls += payload["timing"]["inference_calls"]
            unresolved = sum(1 for s in payload["speeches"] if s["parse_failed"])
            self._on_progress(
                "{0}: 発言{1}件 / 呼び出し{2}回{3}".format(
                    case_dir.name,
                    len(payload["speeches"]),
                    payload["timing"]["inference_calls"],
                    " / 評価できず{0}件".format(unresolved) if unresolved else "",
                )
            )

        summary.elapsed_seconds = time.perf_counter() - started
        return summary.to_dict()


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
