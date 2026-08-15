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
