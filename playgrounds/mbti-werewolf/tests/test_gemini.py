"""GeminiBrain の通信と失敗分類（設計書5.6、5.7、M8）。

実APIは呼ばない。httpx の応答を差し替えて、キーなし・429・認証失敗が所定の
kind になることを確かめる。CIでは LLM を呼ばない（設計書10章）。
"""

from __future__ import annotations

import json

import pytest

from mbti_werewolf.brains.base import BrainError, Request
from mbti_werewolf.brains.factory import create_case_brain, probe_brain

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


def _brain(v2_config, monkeypatch, key="test-key", **brain_overrides):
    if key:
        monkeypatch.setenv("GEMINI_API_KEY", key)
    else:
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    settings = {
        "provider": "gemini",
        "model": "gemini-3.1-flash-lite",
        "max_transport_retries": 1,
        "timeout_seconds": 5,
    }
    settings.update(brain_overrides)
    brain = create_case_brain(v2_config(brain=settings), seed=42)
    brain.backoff_base_seconds = 0
    return brain


def _ok_payload(text='{"target": "p2", "reason": "確認する。"}'):
    return {"candidates": [{"content": {"parts": [{"text": text}]}}]}


def test_missing_key_is_unreachable_and_probe_fails(monkeypatch, v2_config):
    brain = _brain(v2_config, monkeypatch, key="")
    probe = probe_brain(
        v2_config(brain={"provider": "gemini", "model": "gemini-3.1-flash-lite"}),
        seed=42,
    )

    assert probe["ok"] is False
    assert probe["kind"] == "unreachable"

    with pytest.raises(BrainError) as exc:
        brain.generate(Request(system="s", user="u", expect_keys=("target",)))
    assert exc.value.kind == "unreachable"
    assert "GEMINI_API_KEY" in exc.value.message


def test_probe_does_not_call_the_api_when_key_exists(monkeypatch, v2_config):
    def boom(*_args, **_kwargs):
        raise AssertionError("probe が Gemini API を呼んだ")

    monkeypatch.setattr(httpx, "post", boom)
    brain = _brain(v2_config, monkeypatch)
    result = brain.probe()

    assert result["ok"] is True
    assert result["kind"] is None


def test_rate_limited_is_classified(monkeypatch, v2_config):
    monkeypatch.setattr(
        httpx, "post", lambda *_a, **_k: FakeResponse(status_code=429, text="quota")
    )
    brain = _brain(v2_config, monkeypatch)

    with pytest.raises(BrainError) as exc:
        brain.generate(Request(system="s", user="u", expect_keys=("target",)))
    assert exc.value.kind == "rate_limited"


def test_auth_failure_is_unreachable(monkeypatch, v2_config):
    monkeypatch.setattr(
        httpx, "post", lambda *_a, **_k: FakeResponse(status_code=403, text="denied")
    )
    brain = _brain(v2_config, monkeypatch)

    with pytest.raises(BrainError) as exc:
        brain.generate(Request(system="s", user="u", expect_keys=("target",)))
    assert exc.value.kind == "unreachable"


def test_json_candidate_is_parsed(monkeypatch, v2_config):
    posted = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        posted["url"] = url
        posted["payload"] = json
        posted["headers"] = headers
        posted["timeout"] = timeout
        return FakeResponse(payload=_ok_payload())

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr("mbti_werewolf.brains.gemini.time.sleep", lambda *_a, **_k: None)
    brain = _brain(v2_config, monkeypatch)
    result = brain.generate(
        Request(system="rules", user="誰を見る", expect_keys=("target",))
    )

    assert result.parse_failed is False
    assert result.data["target"] == "p2"
    assert "gemini-3.1-flash-lite" in posted["url"]
    assert posted["headers"]["x-goog-api-key"] == "test-key"
    assert posted["payload"]["generationConfig"]["responseMimeType"] == "application/json"


def test_empty_candidates_are_invalid_response(monkeypatch, v2_config):
    monkeypatch.setattr(
        httpx,
        "post",
        lambda *_a, **_k: FakeResponse(
            payload={"candidates": [], "promptFeedback": {"blockReason": "SAFETY"}}
        ),
    )
    brain = _brain(v2_config, monkeypatch)

    with pytest.raises(BrainError) as exc:
        brain.generate(Request(system="s", user="u", expect_keys=("target",)))
    assert exc.value.kind == "invalid_response"
    assert "SAFETY" in exc.value.message
