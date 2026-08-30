"""設定から脳の実装を選んで返す（設計書2.3、5.5）。

engine と agents はこのモジュールも具体実装もimportしない。注入するのは
Runner だけである。推論手段を増やすときに触るのはここと設定の選択肢だけになる
（要件F-15）。
"""

from __future__ import annotations

from typing import Any, Callable, Dict

from ..config import ConfigError
from .gemini import GeminiBrain
from .ollama import OllamaBrain
from .stub import CaseStubBrain

_REGISTRY: Dict[str, Callable[[Any], Any]] = {
    "stub": CaseStubBrain,
    "ollama": OllamaBrain,
    "gemini": GeminiBrain,
}


class _BrainAdapterConfig:
    """実験条件を、brains/ が期待する形へ合わせる薄い層（設計書0.4）。

    `brains/` の実装は `config.brain.max_retries` と `config.seed` を読む。実験条件は
    通信の再試行を `max_transport_retries` として持ち、seedはTrial単位で決まるため、
    ここで名前を橋渡しする。`brains/` を作り直さずに流用するための措置である。
    """

    def __init__(self, experiment_config, brain_config, seed: int, judge: bool = False) -> None:
        self.seed = seed
        self.brain = _AdaptedBrainConfig(brain_config, judge=judge)
        self.experiment = experiment_config


class _AdaptedBrainConfig:
    def __init__(self, brain_config, judge: bool = False) -> None:
        self.provider = brain_config.provider
        self.model = brain_config.model
        self.temperature = brain_config.temperature
        self.timeout_seconds = brain_config.timeout_seconds
        #: 通信失敗時の再試行。形式が崩れたときの再送はAgent側が数える。
        self.max_retries = brain_config.max_transport_retries
        #: Ollamaの num_predict の算出に使う。発言は200字、Judgeはバッチ8件なので
        #: 後者の方を長く取る。
        self.max_output_chars = 800 if judge else 400


def create_case_brain(experiment_config, seed: int, judge: bool = False) -> Any:
    """エージェント用とJudge用で別インスタンスを返す（設計書0.4）。

    温度が違うため、同じ設定オブジェクトから2つ作れる形にしている。
    """

    brain_config = experiment_config.judge_brain if judge else experiment_config.brain
    adapted = _BrainAdapterConfig(experiment_config, brain_config, seed, judge=judge)

    if brain_config.provider == "stub":
        return CaseStubBrain(adapted, seed=seed)

    factory = _REGISTRY.get(brain_config.provider)
    if factory is None:
        raise ConfigError(
            "未知の provider です: {}。使えるのは {} です。".format(
                brain_config.provider, ", ".join(sorted(_REGISTRY))
            )
        )
    brain = factory(adapted)
    # ルール文書v0.7の「回答機会は最大3回」はAgentが数える。Brain内部では再送しない。
    brain.max_format_retries = 0
    return brain


def probe_brain(experiment_config, seed: int, judge: bool = False) -> Any:
    """実行前の接続確認。Stubは対象外なので None を返す。

    失敗しても実験は止めない。1ケースの失敗で17ケースを止めない決まり（3.5）に合わせ、
    ここでは警告の材料だけを返す。
    """

    brain = create_case_brain(experiment_config, seed=seed, judge=judge)
    probe = getattr(brain, "probe", None)
    if probe is None:
        return None
    return probe()
