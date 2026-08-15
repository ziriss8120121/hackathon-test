"""テスト共通の道具（設計書10章）。

推論を呼ばずに受入基準の大半を検証できるようにするため、テストは StubBrain と
このモジュールの差し替え用の脳だけを使う。LLMを呼ばないので、無料枠もモデルの
ダウンロードも消費しない（CIでも同じ構成で動く）。
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable, Dict, List, Optional

import pytest

from mbti_werewolf import config as config_module
from mbti_werewolf.brains import factory
from mbti_werewolf.brains.base import BaseBrain, BrainError

VOTER_RE = re.compile(r"あなた（(p\d+)）")


def is_vote_prompt(user: str) -> bool:
    return user.lstrip().startswith("# 投票")


def voter_of(user: str) -> str:
    found = VOTER_RE.search(user)
    return found.group(1) if found else ""


class FakeBrain(BaseBrain):
    """応答テキストを呼び出しごとに決められる脳。

    responder が文字列を返せばそれが応答になり、BrainError を送出すれば
    通信失敗として扱われる。
    """

    provider = "fake"
    endpoint_kind = "stub"
    name = "fake"
    backoff_base_seconds = 0.0

    def __init__(self, config, responder: Callable[[str, str, int], str]) -> None:
        super().__init__(config)
        self.responder = responder
        self.calls: List[Dict[str, Any]] = []

    def _complete(self, system: str, user: str, temperature: float) -> str:
        index = len(self.calls)
        self.calls.append({"system": system, "user": user, "temperature": temperature})
        return self.responder(system, user, index)


@pytest.fixture
def make_config():
    """既定設定を上書きした Config を返す。"""

    def factory_fn(**overrides: Any):
        brain = overrides.pop("brain", None) or {}
        brain.setdefault("provider", "stub")
        brain.setdefault("max_retries", 1)
        return config_module.load_config(overrides={**overrides, "brain": brain})

    return factory_fn


@pytest.fixture
def use_brain(monkeypatch):
    """provider="stub" で作られる脳を差し替える。

    Runner は brains/factory 経由でしか脳を作らないため、ここを差し替えるだけで
    画面経路・CLI経路の両方に同じ脳を注入できる。
    """

    def install(responder: Callable[[str, str, int], str]) -> Dict[str, Any]:
        created: Dict[str, Any] = {}

        def build(config):
            brain = FakeBrain(config, responder)
            created["brain"] = brain
            return brain

        monkeypatch.setitem(factory._REGISTRY, "stub", build)
        return created

    return install


def speech(text: str = "テストの発言です。") -> str:
    return json.dumps({"speech": text}, ensure_ascii=False)


def vote(target: str, reason: str = "テストの理由。") -> str:
    return json.dumps({"target": target, "reason": reason}, ensure_ascii=False)


def read_json(path) -> Optional[Dict[str, Any]]:
    with open(path, encoding="utf-8") as fp:
        return json.load(fp)


__all__ = [
    "BrainError",
    "FakeBrain",
    "is_vote_prompt",
    "read_json",
    "speech",
    "vote",
    "voter_of",
]
