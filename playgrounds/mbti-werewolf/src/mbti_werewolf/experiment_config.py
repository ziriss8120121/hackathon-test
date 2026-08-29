"""v2.0の実験条件（設計書6.4）。

移行期間だけの名前である。M3でv1を削除する際に `config.py` へ改名する（設計書0.4）。
v1の `config.py` は4人版の1試合を前提にしているため、実験 → Trial → ケースの
3層を表せない。ここでは実験全体の条件を1つのオブジェクトへまとめ、Trialとケースは
ここから導出する。
"""

from __future__ import annotations

import copy
import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PERSONA_PROMPT_VERSION = "v2"
JUDGE_CRITERIA_VERSION = "v1"
INDICATOR_VERSION = "v1"

ENV_MACHINE = "MBTI_WEREWOLF_MACHINE"
ENV_RUNS_DIR = "MBTI_WEREWOLF_RUNS_DIR"

KNOWN_PROVIDERS = ("stub", "ollama", "gemini")


class ConfigError(Exception):
    """実験条件が不正である。"""


@dataclass
class DiscussionConfig:
    """自由議論の終了条件と上限（設計書4.5）。

    値はルールセットではなく設定側が持つ。ルール文書v0.7は上限の存在だけを定め、
    具体的な値を実行条件として扱うため（設計書4.1）。
    """

    max_rounds: int = 6
    max_speeches: int = 40
    max_total_chars: int = 6000
    max_speech_chars: int = 200
    max_consecutive_speeches: Optional[int] = 2
    stop_on_all_pass: bool = True

    def validate(self) -> None:
        for name in ("max_rounds", "max_speeches", "max_total_chars", "max_speech_chars"):
            value = getattr(self, name)
            if not isinstance(value, int) or value < 1:
                raise ConfigError("discussion.{0} は1以上の整数にする: {1}".format(name, value))
        if self.max_consecutive_speeches is not None:
            if not isinstance(self.max_consecutive_speeches, int) or self.max_consecutive_speeches < 1:
                raise ConfigError(
                    "discussion.max_consecutive_speeches は1以上の整数かnullにする: {0}".format(
                        self.max_consecutive_speeches
                    )
                )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BrainConfig:
    """推論経路の設定。`max_transport_retries` は通信の再試行であり、
    ルールの回答機会（`max_response_attempts`）とは別物である（設計書6.4）。
    """

    provider: str = "stub"
    model: str = ""
    temperature: float = 0.8
    timeout_seconds: int = 120
    max_transport_retries: int = 3

    def validate(self, label: str) -> None:
        if self.provider not in KNOWN_PROVIDERS:
            raise ConfigError(
                "{0}.provider が未知の値: {1}（{2}）".format(
                    label, self.provider, " / ".join(KNOWN_PROVIDERS)
                )
            )
        if self.provider != "stub" and not self.model:
            raise ConfigError("{0}.model は provider が stub 以外のとき必須".format(label))
        if not 0.0 <= float(self.temperature) <= 2.0:
            raise ConfigError("{0}.temperature は0.0〜2.0にする: {1}".format(label, self.temperature))
        if self.timeout_seconds < 1:
            raise ConfigError("{0}.timeout_seconds は1以上にする: {1}".format(label, self.timeout_seconds))
        if self.max_transport_retries < 0:
            raise ConfigError(
                "{0}.max_transport_retries は0以上にする: {1}".format(label, self.max_transport_retries)
            )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ExperimentConfig:
    pool_id: str = "pool-001"
    pattern_set_id: str = "pattern-set-001"
    rule_set_id: str = "onenight-8p-v0.7"
    trial_count: int = 1
    trial_range: Optional[List[int]] = None
    base_seed: int = 42
    pattern_selection_mode: str = "seeded_random_without_replacement"
    discussion: DiscussionConfig = field(default_factory=DiscussionConfig)
    persona_prompt_version: str = PERSONA_PROMPT_VERSION
    judge_criteria_version: str = JUDGE_CRITERIA_VERSION
    judge_batch_size: int = 8
    indicator_version: str = INDICATOR_VERSION
    indicator_frozen_at: Optional[str] = None
    brain: BrainConfig = field(default_factory=BrainConfig)
    judge_brain: BrainConfig = field(
        default_factory=lambda: BrainConfig(temperature=0.2, timeout_seconds=180)
    )
    machine_name: str = ""

    def validate(self) -> None:
        if self.trial_count < 1:
            raise ConfigError("trial_count は1以上にする: {0}".format(self.trial_count))
        if self.trial_range is not None:
            if len(self.trial_range) != 2:
                raise ConfigError("trial_range は [開始, 終了] の2要素にする: {0}".format(self.trial_range))
            start, end = self.trial_range
            if start < 1 or end < start:
                raise ConfigError("trial_range が不正: {0}".format(self.trial_range))
            if end > self.trial_count:
                raise ConfigError(
                    "trial_range の終了が trial_count を超えている: {0} > {1}".format(end, self.trial_count)
                )
        if self.judge_batch_size < 1:
            raise ConfigError("judge_batch_size は1以上にする: {0}".format(self.judge_batch_size))
        self.discussion.validate()
        self.brain.validate("brain")
        self.judge_brain.validate("judge_brain")

    def trial_indices(self) -> Tuple[int, ...]:
        """実行対象のTrial番号。`trial_range` があればその範囲だけを返す（F-55）。"""

        if self.trial_range is None:
            return tuple(range(1, self.trial_count + 1))
        start, end = self.trial_range
        return tuple(range(start, end + 1))

    def trial_seed(self, trial_index: int) -> int:
        """`trial_seed = base_seed + trial_index - 1`。Trial 1は base_seed そのまま。"""

        return self.base_seed + trial_index - 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pool_id": self.pool_id,
            "pattern_set_id": self.pattern_set_id,
            "rule_set_id": self.rule_set_id,
            "trial_count": self.trial_count,
            "trial_range": list(self.trial_range) if self.trial_range else None,
            "base_seed": self.base_seed,
            "pattern_selection_mode": self.pattern_selection_mode,
            "discussion": self.discussion.to_dict(),
            "persona_prompt_version": self.persona_prompt_version,
            "judge_criteria_version": self.judge_criteria_version,
            "judge_batch_size": self.judge_batch_size,
            "indicator_version": self.indicator_version,
            "indicator_frozen_at": self.indicator_frozen_at,
            "brain": self.brain.to_dict(),
            "judge_brain": self.judge_brain.to_dict(),
            "machine_name": self.machine_name,
        }


#: null が「未指定」ではなく「値としてのnull」を意味する項目。
#: 上書きの多くはCLI由来で、指定がない引数が None として届く。そのため既定では
#: None を無視するが、この3項目は null 自体が有効な設定値なので通す。
#: `max_consecutive_speeches: null` は「連続発言の上限を設けない」を意味する。
NULLABLE_KEYS = ("trial_range", "indicator_frozen_at", "max_consecutive_speeches")


def _merge(base: Dict[str, Any], overrides: Dict[str, Any]) -> Dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in overrides.items():
        if value is None and key in NULLABLE_KEYS:
            merged[key] = None
        elif isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value)
        elif value is not None:
            merged[key] = value
    return merged


def from_dict(raw: Dict[str, Any]) -> ExperimentConfig:
    known = {f for f in ExperimentConfig.__dataclass_fields__}
    unknown = sorted(set(raw) - known)
    if unknown:
        raise ConfigError("未知の設定項目: {0}".format(", ".join(unknown)))

    data = dict(raw)
    discussion = DiscussionConfig(**data.pop("discussion", {}) or {})
    brain = BrainConfig(**data.pop("brain", {}) or {})
    judge_defaults = {"temperature": 0.2, "timeout_seconds": 180}
    judge_raw = data.pop("judge_brain", None) or {}
    judge_brain = BrainConfig(**_merge(judge_defaults, judge_raw))

    config = ExperimentConfig(
        discussion=discussion, brain=brain, judge_brain=judge_brain, **data
    )
    if not config.machine_name:
        config.machine_name = os.environ.get(ENV_MACHINE, "")
    config.validate()
    return config


#: `trial.json` の `fixed_conditions` と設定項目の対応（設計書6.6）。
#: 再開時にどれを復元するかをここ1か所で決める。
_FIXED_CONDITION_KEYS = (
    ("discussion", "discussion"),
    ("persona_prompt_version", "persona_prompt_version"),
    ("judge_criteria_version", "judge_criteria_version"),
)


def apply_fixed_conditions(
    config: ExperimentConfig, fixed: Dict[str, Any]
) -> Tuple[ExperimentConfig, List[str]]:
    """`trial.json` の固定条件を設定へ戻す（設計書3.5、5.7）。

    再開時はTrialの記録が正本である。いま渡された設定の方を書き換える。同じTrialの
    17ケースを違う条件で実行すると、その差がMBTIの差と区別できなくなり、Trial全体が
    対応あり比較に使えなくなる。

    戻した項目のうち、渡された設定と違っていたものを文言で返す。実行担当が意図と
    違う条件で再開していないかを気付けるようにするため（F-53）。
    """

    raw = config.to_dict()
    notes: List[str] = []

    for config_key, fixed_key in _FIXED_CONDITION_KEYS:
        if fixed_key not in fixed:
            continue
        saved = fixed[fixed_key]
        if raw[config_key] != saved:
            notes.append(
                "{0}: 指定 {1} → Trialの記録 {2}".format(config_key, raw[config_key], saved)
            )
            raw[config_key] = copy.deepcopy(saved)

    # brain は provider と model だけを記録しているため、他の項目は指定を残す。
    for config_key in ("brain", "judge_brain"):
        saved = fixed.get(config_key)
        if not saved:
            continue
        for field_name in ("provider", "model"):
            if field_name not in saved:
                continue
            if raw[config_key][field_name] != saved[field_name]:
                notes.append(
                    "{0}.{1}: 指定 {2} → Trialの記録 {3}".format(
                        config_key,
                        field_name,
                        raw[config_key][field_name] or "（空）",
                        saved[field_name] or "（空）",
                    )
                )
                raw[config_key][field_name] = saved[field_name]

    return from_dict(raw), notes


def load_config(
    path: Optional[Path] = None, overrides: Optional[Dict[str, Any]] = None
) -> ExperimentConfig:
    """既定値 → ファイル → 上書きの順に重ねる（設計書6.4）。"""

    raw: Dict[str, Any] = ExperimentConfig().to_dict()
    if path is not None:
        loaded = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ConfigError("設定ファイルはJSONオブジェクトにする: {0}".format(path))
        raw = _merge(raw, loaded)
    if overrides:
        raw = _merge(raw, overrides)
    return from_dict(raw)
