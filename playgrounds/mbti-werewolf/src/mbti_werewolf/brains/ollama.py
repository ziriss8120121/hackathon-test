"""ローカル実行の脳（設計書5.5）。

既定の推論手段である。ローカルで動くため呼び出し回数の制限がなく、100試合以上の
実行はこの経路でしか成立しない（設計書1.2）。課金経路を構成に持ち込まない
という方針の中心にあたる。

Ollamaの起動が前提になる。
    brew install ollama && ollama serve
    ollama pull gemma3:4b
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from .base import BaseBrain, BrainError

DEFAULT_MODEL = "gemma3:4b"
DEFAULT_BASE_URL = "http://localhost:11434"
PROBE_TIMEOUT_SECONDS = 3.0


class OllamaBrain(BaseBrain):
    provider = "ollama"
    endpoint_kind = "local"

    def __init__(self, config) -> None:
        super().__init__(config)
        self.model = config.brain.model or DEFAULT_MODEL
        self.name = "ollama:{}".format(self.model)
        self.base_url = os.environ.get("OLLAMA_BASE_URL", DEFAULT_BASE_URL).rstrip("/")

    def probe(self) -> Dict[str, Any]:
        """実行前の接続確認（設計書5.6）。推論は呼ばない。"""

        try:
            httpx = _load_httpx()
        except BrainError as exc:
            return {
                "ok": False,
                "kind": exc.kind,
                "has_model": False,
                "models": [],
                "message": exc.message,
            }
        url = "{}/api/tags".format(self.base_url)
        try:
            response = httpx.get(url, timeout=PROBE_TIMEOUT_SECONDS)
        except httpx.ConnectError:
            return {
                "ok": False,
                "kind": "unreachable",
                "has_model": False,
                "models": [],
                "message": "Ollamaに接続できません（{}）。ollama serve が動いているか確認してください。".format(
                    url
                ),
            }
        except httpx.TimeoutException:
            return {
                "ok": False,
                "kind": "timeout",
                "has_model": False,
                "models": [],
                "message": "Ollamaの応答が {} 秒以内に返りませんでした。".format(
                    PROBE_TIMEOUT_SECONDS
                ),
            }
        except httpx.HTTPError as exc:
            return {
                "ok": False,
                "kind": "unreachable",
                "has_model": False,
                "models": [],
                "message": "Ollamaへの通信に失敗しました: {}".format(exc),
            }

        if response.status_code >= 400:
            return {
                "ok": False,
                "kind": "invalid_response",
                "has_model": False,
                "models": [],
                "message": "Ollamaが {} を返しました: {}".format(
                    response.status_code, response.text[:200]
                ),
            }

        try:
            body = response.json()
        except (json.JSONDecodeError, ValueError):
            return {
                "ok": False,
                "kind": "invalid_response",
                "has_model": False,
                "models": [],
                "message": "Ollamaの応答がJSONではありません。",
            }

        models = _model_names(body)
        has_model = _has_model(models, self.model)
        if not has_model:
            return {
                "ok": False,
                "kind": "invalid_response",
                "has_model": False,
                "models": models,
                "message": "モデル {} が見つかりません。ollama pull {} を実行してください。".format(
                    self.model, self.model
                ),
            }
        return {
            "ok": True,
            "kind": None,
            "has_model": True,
            "models": models,
            "message": "Ollamaに接続でき、モデル {} があります。".format(self.model),
        }

    def _complete(self, system: str, user: str, temperature: float) -> str:
        httpx = _load_httpx()
        payload: Dict[str, Any] = {
            "model": self.model,
            "system": system,
            "prompt": user,
            "stream": False,
            # Ollamaのjsonモード。応答をJSONに寄せることで解析失敗を減らす（設計書5.4）。
            "format": "json",
            # 1ケースは十数分かかる。既定の5分だと途中でモデルがアンロードされる。
            "keep_alive": "30m",
            "options": {
                "temperature": temperature,
                # 呼び出しごとに違う値を渡す。同じseedなら同じ並びになるため、
                # モデル側の揺れを除けば再現性を保てる（要件NF-05）。
                "seed": self.config.seed + self._call_index,
                "num_predict": max(128, self.brain_config.max_output_chars * 3),
            },
        }

        url = "{}/api/generate".format(self.base_url)
        try:
            response = httpx.post(
                url, json=payload, timeout=self.brain_config.timeout_seconds
            )
        except httpx.ConnectError:
            raise BrainError(
                "unreachable",
                "Ollamaに接続できません（{}）。ollama serve が動いているか確認してください。".format(
                    url
                ),
            )
        except httpx.TimeoutException:
            raise BrainError(
                "timeout",
                "Ollamaの応答が {} 秒以内に返りませんでした。".format(
                    self.brain_config.timeout_seconds
                ),
            )
        except httpx.HTTPError as exc:
            raise BrainError("unreachable", "Ollamaへの通信に失敗しました: {}".format(exc))

        if response.status_code == 429:
            raise BrainError("rate_limited", "Ollamaが要求を受け付けられない状態です。")
        if response.status_code == 404:
            raise BrainError(
                "invalid_response",
                "モデル {} が見つかりません。ollama pull {} を実行してください。".format(
                    self.model, self.model
                ),
            )
        if response.status_code >= 400:
            raise BrainError(
                "invalid_response",
                "Ollamaが {} を返しました: {}".format(
                    response.status_code, response.text[:200]
                ),
            )

        try:
            body = response.json()
        except (json.JSONDecodeError, ValueError):
            raise BrainError("invalid_response", "Ollamaの応答がJSONではありません。")

        text = body.get("response")
        if not isinstance(text, str) or not text.strip():
            raise BrainError("invalid_response", "Ollamaの応答に本文が含まれていません。")
        return text


def _load_httpx():
    try:
        import httpx
    except ImportError:
        raise BrainError(
            "unreachable",
            "httpx が入っていません。pip install -r requirements.txt を実行してください。",
        )
    return httpx


def _model_names(body: Dict[str, Any]) -> List[str]:
    names: List[str] = []
    for entry in body.get("models") or []:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name") or entry.get("model")
        if isinstance(name, str) and name.strip():
            names.append(name.strip())
    return names


def _has_model(names: List[str], model: str) -> bool:
    target = model.strip()
    if not target:
        return False
    for name in names:
        if name == target:
            return True
        # `gemma3:4b` と `gemma3:4b-instruct-q4_K_M` のようにタグが付く場合がある。
        if name.startswith(target + "-") or name.startswith(target + ":"):
            return True
    return False
