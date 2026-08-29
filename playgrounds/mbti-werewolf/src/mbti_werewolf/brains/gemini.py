"""無料枠APIの脳（設計書5.5、5.6）。

ローカルの小型モデルで議論が成立しない場合の品質比較用である。1試合あたりの
推論呼び出しは 発言12回 + 投票4回 = 16回 なので、無料枠の1日あたり上限に
すぐ届く。多試合実行はローカル経路で行う（設計書1.2）。

課金は有効化しない。有効化すると無料枠を外れるため、有効化しないこと自体を
運用ルールとする（設計書1.3）。APIキーは環境変数から読み、出力物には残さない
（要件NF-11）。
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Dict

from .base import BaseBrain, BrainError

DEFAULT_MODEL = "gemini-3.1-flash-lite"
API_BASE = "https://generativelanguage.googleapis.com/v1beta"
API_KEY_ENV = "GEMINI_API_KEY"
# 無料枠の分間上限に当たらないよう、呼び出し間隔を空ける。
_MIN_INTERVAL_SECONDS = 7.0


class GeminiBrain(BaseBrain):
    provider = "gemini"
    endpoint_kind = "free_api"

    def __init__(self, config) -> None:
        super().__init__(config)
        self.model = config.brain.model or DEFAULT_MODEL
        self.name = "gemini:{}".format(self.model)
        self._api_key = os.environ.get(API_KEY_ENV, "").strip()
        self._last_call_at = 0.0

    def probe(self) -> Dict[str, Any]:
        """実行前の確認。無料枠を消費しないよう、キーの有無だけを見る。"""

        if not self._api_key:
            return {
                "ok": False,
                "kind": "unreachable",
                "message": "環境変数 {} が設定されていません。".format(API_KEY_ENV),
            }
        return {
            "ok": True,
            "kind": None,
            "message": "Gemini の APIキーは設定されています。接続確認は初回呼び出しで行います。",
        }

    def _complete(self, system: str, user: str, temperature: float) -> str:
        if not self._api_key:
            raise BrainError(
                "unreachable",
                "環境変数 {} が設定されていません。".format(API_KEY_ENV),
            )
        self._wait_for_interval()

        try:
            import httpx
        except ImportError:
            raise BrainError(
                "unreachable",
                "httpx が入っていません。pip install -r requirements.txt を実行してください。",
            )

        payload: Dict[str, Any] = {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {
                "temperature": temperature,
                "responseMimeType": "application/json",
                "maxOutputTokens": max(256, self.brain_config.max_output_chars * 4),
            },
        }

        url = "{}/models/{}:generateContent".format(API_BASE, self.model)
        try:
            response = httpx.post(
                url,
                json=payload,
                headers={"x-goog-api-key": self._api_key},
                timeout=self.brain_config.timeout_seconds,
            )
        except httpx.ConnectError:
            raise BrainError("unreachable", "Gemini APIに接続できません。")
        except httpx.TimeoutException:
            raise BrainError(
                "timeout",
                "Gemini APIの応答が {} 秒以内に返りませんでした。".format(
                    self.brain_config.timeout_seconds
                ),
            )
        except httpx.HTTPError as exc:
            raise BrainError("unreachable", "Gemini APIへの通信に失敗しました: {}".format(exc))
        finally:
            self._last_call_at = time.monotonic()

        if response.status_code == 429:
            raise BrainError(
                "rate_limited",
                "Gemini APIの無料枠の上限に達しました。ローカル実行へ切り替えてください。",
            )
        if response.status_code in (401, 403):
            raise BrainError("unreachable", "Gemini APIの認証に失敗しました。APIキーを確認してください。")
        if response.status_code >= 400:
            raise BrainError(
                "invalid_response",
                "Gemini APIが {} を返しました: {}".format(
                    response.status_code, response.text[:200]
                ),
            )

        try:
            body = response.json()
        except (json.JSONDecodeError, ValueError):
            raise BrainError("invalid_response", "Gemini APIの応答がJSONではありません。")

        return _first_text(body)

    def _wait_for_interval(self) -> None:
        if self._last_call_at <= 0:
            return
        elapsed = time.monotonic() - self._last_call_at
        remaining = _MIN_INTERVAL_SECONDS - elapsed
        if remaining > 0:
            time.sleep(remaining)


def _first_text(body: Dict[str, Any]) -> str:
    candidates = body.get("candidates") or []
    if not candidates:
        reason = (body.get("promptFeedback") or {}).get("blockReason")
        raise BrainError(
            "invalid_response",
            "Gemini APIが候補を返しませんでした{}。".format(
                "（blockReason={}）".format(reason) if reason else ""
            ),
        )

    parts = ((candidates[0] or {}).get("content") or {}).get("parts") or []
    for part in parts:
        text = part.get("text")
        if isinstance(text, str) and text.strip():
            return text
    raise BrainError("invalid_response", "Gemini APIの応答に本文が含まれていません。")
