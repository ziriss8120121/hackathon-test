"""脳のインターフェース（設計書5.1、5.4）。

ゲーム進行側が知るのはこのモジュールの形だけである。推論手段を追加するときに
触るのは brains/ 配下と設定の選択肢だけになる（要件F-15）。

責務の分け方は次のとおり。

    Brain  : 通信、応答形式（JSON）の検証、形式が崩れた場合のリトライ、待機時間の計測
    Agent  : 意味の検証（投票先が生存者かなど）と、その再要求

形式の失敗と意味の失敗を別の層で扱うため、どちらが起きたのかがログから区別できる。
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Sequence, Tuple

RETRYABLE_KINDS = ("unreachable", "rate_limited", "timeout")
ERROR_KINDS = ("unreachable", "rate_limited", "timeout", "invalid_response")


class BrainError(Exception):
    """推論の呼び出しが継続不能な形で失敗したことを表す。

    kind は要件NF-07が求める「原因が判別できる形」の分類である。
    rate_limited が出たら別の無料手段へ切り替える判断に直結する（要件NF-08）。
    """

    def __init__(self, kind: str, message: str) -> None:
        if kind not in ERROR_KINDS:
            kind = "invalid_response"
        super().__init__(message)
        self.kind = kind
        self.message = message

    def to_dict(self) -> Dict[str, str]:
        return {"kind": self.kind, "message": self.message}


@dataclass
class Request:
    """1回の推論要求。

    choices と tag は形式に関する補助情報であり、ゲームのルールではない。
      choices : expect_keys のうち選択肢が限られる項目の候補（投票先など）
      tag     : 呼び出しの識別ラベル。StubBrainの出力切り替えと調査に使う
    """

    system: str
    user: str
    expect_keys: Tuple[str, ...] = ()
    choices: Tuple[str, ...] = ()
    tag: str = ""


@dataclass
class BrainResponse:
    """1回の推論結果。"""

    text: str
    data: Optional[Dict[str, Any]]
    wait_seconds: float = 0.0
    retry_count: int = 0
    parse_failed: bool = False
    extra: Dict[str, Any] = field(default_factory=dict)


_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def extract_json(text: str) -> Optional[Dict[str, Any]]:
    """応答テキストからJSONオブジェクトを取り出す（設計書5.4の段階1と2）。

    小型モデルは前置きやコードブロックを付けることがあるため、素の json.loads に
    失敗したら囲みを外し、最初の { から最後の } までを切り出して再解析する。
    """
    if not text:
        return None

    candidates = [text.strip()]

    fenced = _FENCE_RE.search(text)
    if fenced:
        candidates.append(fenced.group(1).strip())

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start : end + 1])

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _has_keys(data: Optional[Dict[str, Any]], keys: Sequence[str]) -> bool:
    if data is None:
        return False
    return all(key in data and data[key] not in (None, "") for key in keys)


class BaseBrain:
    """HTTP経由の脳の共通処理。

    サブクラスは _complete() だけを実装する。JSONの解析、形式が崩れた場合の
    再送、通信失敗時の指数バックオフ、待機時間の計測はここで面倒を見る。
    """

    name = "base"
    endpoint_kind = "local"
    provider = "base"

    #: 通信失敗時の待機の基準秒数。テストから短くできるように属性で持つ。
    backoff_base_seconds = 1.0

    #: 形式が崩れたときにBrain内部で送り直す回数。None なら通信の再試行回数を流用する。
    #: v2.0では0にする。ルール文書v0.7が定める「回答機会は最大3回」はAgent側が数え、
    #: Brain内部の再送と二重に掛からないようにするためである（設計書5.4、6.4）。
    max_format_retries: Optional[int] = None

    def __init__(self, config) -> None:
        self.config = config
        self.brain_config = config.brain
        self.model = config.brain.model
        self._call_index = 0

    @property
    def _format_retries(self) -> int:
        if self.max_format_retries is not None:
            return max(0, self.max_format_retries)
        return max(0, self.brain_config.max_retries)

    # --- サブクラスが実装する部分 -------------------------------------------

    def _complete(self, system: str, user: str, temperature: float) -> str:
        raise NotImplementedError

    # --- 共通処理 -----------------------------------------------------------

    def describe(self) -> Dict[str, str]:
        """要件F-16のために run_log へ残す推論手段の識別情報。"""
        return {
            "provider": self.provider,
            "model": self.model,
            "endpoint_kind": self.endpoint_kind,
            "name": self.name,
        }

    def generate(self, request: Request) -> BrainResponse:
        max_retries = self._format_retries
        wait_seconds = 0.0
        text = ""
        data: Optional[Dict[str, Any]] = None

        for attempt in range(max_retries + 1):
            # 形式が崩れたときは温度を下げ、形式指定を強めて送り直す（設計書5.4の段階3）。
            temperature = max(0.0, self.brain_config.temperature - 0.3 * attempt)
            user = request.user if attempt == 0 else self._reinforce_format(request)

            started = time.perf_counter()
            try:
                text = self._call_with_backoff(request.system, user, temperature)
            finally:
                wait_seconds += time.perf_counter() - started

            data = extract_json(text)
            if _has_keys(data, request.expect_keys):
                return BrainResponse(
                    text=text,
                    data=data,
                    wait_seconds=wait_seconds,
                    retry_count=attempt,
                    parse_failed=False,
                )

        return BrainResponse(
            text=text,
            data=data,
            wait_seconds=wait_seconds,
            retry_count=max_retries,
            parse_failed=True,
        )

    def _reinforce_format(self, request: Request) -> str:
        keys = "、".join('"{}"'.format(key) for key in request.expect_keys)
        example = json.dumps(
            {key: "..." for key in request.expect_keys}, ensure_ascii=False
        )
        lines = [
            request.user,
            "",
            "# 重要（形式の再指定）",
            "前回の応答は形式が正しくありませんでした。",
            "説明や前置きを一切書かず、JSONオブジェクトだけを出力してください。",
            "必ず {} のキーを含めてください。".format(keys),
            "例: {}".format(example),
        ]
        if request.choices:
            lines.append(
                "選べる値は {} のいずれかです。".format("、".join(request.choices))
            )
        return "\n".join(lines)

    def _call_with_backoff(self, system: str, user: str, temperature: float) -> str:
        """通信失敗を指数バックオフで再試行する（設計書3.4）。"""
        attempts = max(1, self.brain_config.max_retries)
        last_error: Optional[BrainError] = None

        for attempt in range(attempts):
            self._call_index += 1
            try:
                return self._complete(system, user, temperature)
            except BrainError as exc:
                last_error = exc
                if exc.kind not in RETRYABLE_KINDS or attempt == attempts - 1:
                    raise
                time.sleep(self.backoff_base_seconds * (2**attempt))

        raise last_error if last_error else BrainError("invalid_response", "応答を取得できませんでした。")
