"""LLMを呼ばない脳（設計書5.5）。

進行、出力ファイル、テストを推論なしで検証するために使う。追加インストールも課金も
通信も発生しないため、受入基準AC-01〜AC-05の確認はこの脳で行える。

議論としては無意味である。17ケースの生成、条件固定の検査、`case_log.json` や
`transcript.md` の形式検証に足りるだけの応答を返す。
"""

from __future__ import annotations

import json
import random
from typing import Dict

from .base import BrainError, BrainResponse, Request

_SPEECHES = [
    "$other の話は根拠が示されていないと思います。もう少し具体的に説明してもらえますか。",
    "私の情報だけでは判断できません。$other の主張と他の発言を照らして考えたいです。",
    "$other の説明は途中で内容が変わっているように見えます。そこが気になっています。",
    "現時点では $other を優先して疑う根拠がありません。他の情報を待ちたいです。",
    "役職について話せる人から先に情報を出してほしいです。$other はどう考えていますか。",
]

_MEMOS = [
    "公開情報だけでは判断材料が足りないため。",
    "相手の説明の具体性を確かめたいため。",
    "自分の確定情報と矛盾しないか見たいため。",
    "投票先を決めるには根拠が不足しているため。",
]

_PASS_MEMOS = [
    "情報が少ないので他の発言を待つ。",
    "今は自分から出せる材料がない。",
    "先に他の人の主張を聞きたい。",
]

_ROLE_AWARENESS = "自分に通知された情報だけを持っている。"


class CaseStubBrain:
    """v2.0の応答形式を返す脳。LLMを呼ばない。

    夜の役職行動、議論前後の個別判断、発言か見送りの選択、投票の5種類を、
    設計書5.4の期待形どおりに返す。
    """

    provider = "stub"
    name = "stub"
    endpoint_kind = "stub"

    def __init__(self, config, seed: int = 0) -> None:
        self.config = config
        self.brain_config = config.brain
        self.model = config.brain.model or "stub"
        self._rng = random.Random(seed)
        #: 見送りを何回に1回返すか。沈黙が起きる経路をStubでも通すために入れている。
        self.pass_every = 4
        self._speak_calls = 0

    def describe(self) -> Dict[str, str]:
        return {
            "provider": self.provider,
            "model": self.model,
            "endpoint_kind": self.endpoint_kind,
            "name": self.name,
        }

    def generate(self, request: Request) -> BrainResponse:
        tag = (request.tag or "").split(":")[0]
        handler = {
            "night_seer": self._pick_target,
            "night_thief_inspect": self._pick_target,
            "night_thief_swap": self._swap,
            "pre_discussion": self._pre_discussion,
            "speak": self._speak,
            "pre_vote": self._pre_vote,
            "vote": self._vote,
        }.get(tag)
        if handler is None:
            raise BrainError("invalid_response", "未知のtag: {0}".format(request.tag))

        payload = handler(request)
        return BrainResponse(
            text=json.dumps(payload, ensure_ascii=False), data=payload, wait_seconds=0.0
        )

    # --- 内部 ---------------------------------------------------------------

    def _choice(self, request: Request) -> str:
        candidates = list(request.choices) or ["p1"]
        return candidates[self._rng.randrange(len(candidates))]

    def _pick_target(self, request: Request) -> Dict[str, object]:
        return {"target": self._choice(request), "reason": "確認できる相手を選んだ。"}

    def _swap(self, request: Request) -> Dict[str, object]:
        swap = self._rng.random() < 0.5
        return {"swap": swap, "reason": "最終役職を有利にしたいと考えた。"}

    def _pre_discussion(self, request: Request) -> Dict[str, object]:
        return {
            "role_awareness": _ROLE_AWARENESS,
            "suspect": "unknown",
            "confidence": 1 + self._rng.randrange(2),
            "reason": "まだ発言がないため。",
        }

    def _speak(self, request: Request) -> Dict[str, object]:
        self._speak_calls += 1
        if self._speak_calls % self.pass_every == 0:
            return {
                "speak": False,
                "memo": _PASS_MEMOS[self._rng.randrange(len(_PASS_MEMOS))],
            }
        others = list(request.choices) or ["他の参加者"]
        other = others[self._rng.randrange(len(others))]
        template = _SPEECHES[self._rng.randrange(len(_SPEECHES))]
        return {
            "speak": True,
            "speech": template.replace("$other", other),
            "memo": _MEMOS[self._rng.randrange(len(_MEMOS))],
        }

    def _pre_vote(self, request: Request) -> Dict[str, object]:
        suspect = self._choice(request)
        return {
            "suspect": suspect,
            "confidence": 2 + self._rng.randrange(3),
            "reason": "説明の具体性が足りないと感じたため。",
            "planned_vote": suspect,
        }

    def _vote(self, request: Request) -> Dict[str, object]:
        return {
            "target": self._choice(request),
            "memo": _MEMOS[self._rng.randrange(len(_MEMOS))],
        }
