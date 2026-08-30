"""OllamaBrain の通信と失敗分類（設計書5.6、1.4、M5）。

実モデルは呼ばない。httpx の応答を差し替えて、接続不能・タイムアウト・モデルなしが
所定の kind になることと、APIキーなしでも動くことを確かめる。CIでは LLM を呼ばない
（設計書10章）。
"""

from __future__ import annotations

import json
import os

import pytest

from mbti_werewolf.brains.base import BrainError, Request
from mbti_werewolf.brains.factory import create_case_brain, probe_brain
from mbti_werewolf.brains.ollama import OllamaBrain, _has_model

httpx = pytest.importorskip("httpx")


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text or (json.dumps(payload) if payload is not None else "")

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


def _brain(v2_config, **brain_overrides):
    settings = {
        "provider": "ollama",
        "model": "gemma3:4b",
        "max_transport_retries": 1,
        "timeout_seconds": 5,
    }
    settings.update(brain_overrides)
    config = v2_config(brain=settings)
    brain = create_case_brain(config, seed=42)
    brain.backoff_base_seconds = 0
    return brain


def test_stub_probe_is_skipped(v2_config):
    assert probe_brain(v2_config(), seed=42) is None


def test_connect_error_is_unreachable(monkeypatch, v2_config):
    def boom(*_args, **_kwargs):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(httpx, "post", boom)
    brain = _brain(v2_config)

    with pytest.raises(BrainError) as exc:
        brain.generate(Request(system="s", user="u", expect_keys=("target",)))

    assert exc.value.kind == "unreachable"
    assert "Ollamaに接続できません" in exc.value.message


def test_timeout_is_timeout(monkeypatch, v2_config):
    def boom(*_args, **_kwargs):
        raise httpx.TimeoutException("slow")

    monkeypatch.setattr(httpx, "post", boom)
    brain = _brain(v2_config)

    with pytest.raises(BrainError) as exc:
        brain.generate(Request(system="s", user="u", expect_keys=("target",)))

    assert exc.value.kind == "timeout"


def test_missing_model_is_invalid_response(monkeypatch, v2_config):
    monkeypatch.setattr(
        httpx, "post", lambda *_a, **_k: FakeResponse(status_code=404, text="not found")
    )
    brain = _brain(v2_config)

    with pytest.raises(BrainError) as exc:
        brain.generate(Request(system="s", user="u", expect_keys=("target",)))

    assert exc.value.kind == "invalid_response"
    assert "ollama pull gemma3:4b" in exc.value.message


def test_rate_limited_is_classified(monkeypatch, v2_config):
    monkeypatch.setattr(
        httpx, "post", lambda *_a, **_k: FakeResponse(status_code=429, text="busy")
    )
    brain = _brain(v2_config)

    with pytest.raises(BrainError) as exc:
        brain.generate(Request(system="s", user="u", expect_keys=("target",)))

    assert exc.value.kind == "rate_limited"


def test_json_response_is_parsed(monkeypatch, v2_config):
    posted = {}

    def fake_post(url, json=None, timeout=None):
        posted["url"] = url
        posted["payload"] = json
        posted["timeout"] = timeout
        return FakeResponse(
            payload={
                "response": '{"target": "P2", "reason": "確認する。"}'
            }
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    brain = _brain(v2_config)
    result = brain.generate(
        Request(system="rules", user="誰を見る", expect_keys=("target",))
    )

    assert result.parse_failed is False
    assert result.data["target"] == "P2"
    assert posted["payload"]["format"] == "json"
    assert posted["payload"]["keep_alive"] == "30m"
    assert posted["payload"]["model"] == "gemma3:4b"
    assert posted["payload"]["options"]["seed"] == 43
    assert "/api/generate" in posted["url"]


def test_ollama_does_not_need_an_api_key(monkeypatch, v2_config):
    """課金経路がないことの確認（設計書1.4）。Ollamaはキーを読まない。"""

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(
        httpx,
        "post",
        lambda *_a, **_k: FakeResponse(
            payload={"response": '{"target": "P3", "reason": "見る。"}'}
        ),
    )
    brain = _brain(v2_config)
    result = brain.generate(Request(system="s", user="u", expect_keys=("target",)))

    assert result.parse_failed is False
    assert "GEMINI_API_KEY" not in os.environ


def test_probe_reports_missing_server(monkeypatch, v2_config):
    def boom(*_args, **_kwargs):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(httpx, "get", boom)
    result = probe_brain(
        v2_config(brain={"provider": "ollama", "model": "gemma3:4b"}), seed=42
    )

    assert result["ok"] is False
    assert result["kind"] == "unreachable"


def test_probe_reports_missing_model(monkeypatch, v2_config):
    monkeypatch.setattr(
        httpx,
        "get",
        lambda *_a, **_k: FakeResponse(payload={"models": [{"name": "other:1b"}]}),
    )
    result = probe_brain(
        v2_config(brain={"provider": "ollama", "model": "gemma3:4b"}), seed=42
    )

    assert result["ok"] is False
    assert result["has_model"] is False
    assert "ollama pull gemma3:4b" in result["message"]


def test_probe_succeeds_when_model_is_present(monkeypatch, v2_config):
    monkeypatch.setattr(
        httpx,
        "get",
        lambda *_a, **_k: FakeResponse(payload={"models": [{"name": "gemma3:4b"}]}),
    )
    result = probe_brain(
        v2_config(brain={"provider": "ollama", "model": "gemma3:4b"}), seed=42
    )

    assert result["ok"] is True
    assert result["has_model"] is True


def test_model_name_matches_tagged_variants():
    assert _has_model(["gemma3:4b"], "gemma3:4b")
    assert _has_model(["gemma3:4b-instruct-q4_K_M"], "gemma3:4b")
    assert not _has_model(["gemma3:latest"], "gemma3:4b")


def test_gemini_probe_without_key(monkeypatch, v2_config):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    result = probe_brain(
        v2_config(brain={"provider": "gemini", "model": "gemini-3.1-flash-lite"}),
        seed=42,
    )

    assert result["ok"] is False
    assert "GEMINI_API_KEY" in result["message"]


def test_empty_response_is_invalid(monkeypatch, v2_config):
    monkeypatch.setattr(
        httpx, "post", lambda *_a, **_k: FakeResponse(payload={"response": "  "})
    )
    brain = _brain(v2_config)

    with pytest.raises(BrainError) as exc:
        brain.generate(Request(system="s", user="u", expect_keys=("target",)))

    assert exc.value.kind == "invalid_response"


def test_live_probe_skips_when_ollama_is_down(v2_config):
    """実機があるときだけ接続を確かめる。CIでは skip になる。"""

    brain = _brain(v2_config)
    result = brain.probe()
    if not result["ok"]:
        pytest.skip(result["message"])
    assert result["has_model"] is True
    assert isinstance(brain, OllamaBrain)
