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
from .stub import StubBrain

_REGISTRY: Dict[str, Callable[[Any], Any]] = {
    "stub": StubBrain,
    "ollama": OllamaBrain,
    "gemini": GeminiBrain,
}


def create_brain(config) -> Any:
    provider = config.brain.provider
    factory = _REGISTRY.get(provider)
    if factory is None:
        raise ConfigError(
            "未知の provider です: {}。使えるのは {} です。".format(
                provider, ", ".join(sorted(_REGISTRY))
            )
        )
    return factory(config)


# --- ここから下はv2.0（8人ワンナイト）用 ---------------------------------


class _BrainAdapterConfig:
    """v2.0の設定を、brains/ が期待する形へ合わせる薄い層（設計書0.4）。

    v1のBrainは `config.brain.max_retries` と `config.seed` を読む。v2.0の設定は
    通信の再試行を `max_transport_retries` として持ち、seedはTrial単位で決まるため、
    ここで名前を橋渡しする。brains/ を作り直さずに流用するための措置である。
    """

    def __init__(self, experiment_config, brain_config, seed: int) -> None:
        self.seed = seed
        self.brain = _AdaptedBrainConfig(brain_config)
        self.experiment = experiment_config


class _AdaptedBrainConfig:
    def __init__(self, brain_config) -> None:
        self.provider = brain_config.provider
        self.model = brain_config.model
        self.temperature = brain_config.temperature
        self.timeout_seconds = brain_config.timeout_seconds
        #: 通信失敗時の再試行。形式が崩れたときの再送はAgent側が数える。
        self.max_retries = brain_config.max_transport_retries
        #: Ollamaの num_predict の算出に使う。v2.0の発言上限より余裕を持たせる。
        self.max_output_chars = 400


def create_case_brain(experiment_config, seed: int, judge: bool = False) -> Any:
    """エージェント用とJudge用で別インスタンスを返す（設計書0.4）。

    温度が違うため、同じ設定オブジェクトから2つ作れる形にしている。
    """

    from .stub import CaseStubBrain

    brain_config = experiment_config.judge_brain if judge else experiment_config.brain
    adapted = _BrainAdapterConfig(experiment_config, brain_config, seed)

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
