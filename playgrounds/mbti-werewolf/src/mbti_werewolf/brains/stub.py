"""LLMを呼ばない脳（設計書5.5）。

進行、出力ファイル、画面、テストを推論なしで検証するために使う。追加インストール
も課金も通信も発生しないため、受入基準AC-01〜AC-05の確認はこの脳で行える。

議論としては無意味である。心理機能ごとに文の型を変えているのは、指標集計
（設計書9章）が機能差を拾えているかを確かめられるようにするためであって、
発言の中身に意味を持たせるためではない。
"""

from __future__ import annotations

import json
import random
import re
from typing import Dict, List, Tuple

from .base import BrainError, BrainResponse, Request

_PLAYER_ID_RE = re.compile(r"\bp\d+\b")

# 心理機能ごとの発言テンプレート。$other は他の参加者のIDに置き換える。
_SPEECH_TEMPLATES: Dict[str, List[str]] = {
    "Ne": [
        "まだ判断材料が少ないので可能性を並べます。$other が人狼かもしれないですし、"
        "あえて静かにしている人が人狼という可能性もあると思います。",
        "考えられる筋は複数あります。$other が誘導しているのかもしれませんし、"
        "逆に $other は素直に話しているだけかもしれません。断定はまだできません。",
        "仮説を広げておきます。$other が怪しいという線と、投票が割れるのを待っている人がいる線です。",
    ],
    "Ti": [
        "$other の発言は前半と後半で結論が変わっていて矛盾しています。"
        "根拠が薄いと思いますが、なぜそう判断したのですか。",
        "$other の話は前提が示されていません。理由の部分が抜けているので、"
        "そのままでは疑う材料として使えません。",
        "整理します。$other の主張は他の発言と両立しません。どちらかが誤りです。",
    ],
    "Fe": [
        "$other の意見に同意します。確かにその見方は納得できました。"
        "全員で落ち着いて整理していきましょう。",
        "$other の言うことはわかります。責める言い方にならないように、"
        "みんなで確認しながら進めたいです。",
        "賛成です。$other の受け取り方も自然だと思いますし、まだ決め付けたくありません。",
    ],
    "Si": [
        "先ほど $other が言っていた内容と、今の発言でずれがあります。"
        "最初に出た話に戻って確認したいです。",
        "$other は最初のターンで別のことを言っていました。そこが引っかかっています。",
        "これまでに出た発言を振り返ると、$other の説明だけが後から変わっています。",
    ],
    "Ni": [
        "流れを見ると構図は決まっていると思います。$other が中心にいるという見立てです。",
        "見えている筋は一つです。$other の位置がこの試合の鍵になります。",
    ],
    "Se": [
        "今の $other の反応が気になりました。",
        "$other の言い方が引っかかります。",
    ],
    "Te": [
        "時間を使いすぎています。$other に絞って投票しませんか。",
        "結論を出しましょう。今の情報なら $other が候補です。",
    ],
    "Fi": [
        "私は納得できていません。$other の言い方に誠実さを感じませんでした。",
        "多数に合わせるつもりはありません。$other の話は自分の基準では受け入れられません。",
    ],
}

_FALLBACK_TEMPLATES = [
    "今のところ強く疑える相手はいません。$other の様子を見ています。",
]

_VOTE_REASONS = [
    "発言の根拠が薄いと感じたため。",
    "話の筋が途中で変わっていたため。",
    "他の候補よりも疑う材料が多いと判断したため。",
    "議論を誘導しようとしているように見えたため。",
]


class StubBrain:
    """固定文テンプレートとseed付き乱数だけで応答を返す脳。"""

    provider = "stub"
    name = "stub"
    endpoint_kind = "stub"

    def __init__(self, config) -> None:
        self.config = config
        self.brain_config = config.brain
        self.model = config.brain.model or "stub"
        # 呼び出し順が同じなら同じ出力になる。要件F-22の再現性テストはこれに依存する。
        self._rng = random.Random(config.seed)
        self._last_template: Dict[str, int] = {}

    def describe(self) -> Dict[str, str]:
        return {
            "provider": self.provider,
            "model": self.model,
            "endpoint_kind": self.endpoint_kind,
            "name": self.name,
        }

    def generate(self, request: Request) -> BrainResponse:
        action, function, _role, player_id = _parse_tag(request.tag)

        if "target" in request.expect_keys:
            payload = self._vote(request, player_id)
        else:
            payload = {"speech": self._speech(request, function, player_id)}

        text = json.dumps(payload, ensure_ascii=False)
        return BrainResponse(text=text, data=payload, wait_seconds=0.0)

    # --- 内部 ---------------------------------------------------------------

    def _speech(self, request: Request, function: str, player_id: str) -> str:
        others = _other_ids(request.user, player_id)
        templates = _SPEECH_TEMPLATES.get(function) or _FALLBACK_TEMPLATES

        # 同じプレイヤーが直前と同じ文を繰り返すとタイムラインが読めなくなるため、
        # 前回と違うテンプレートを選ぶ。
        index = self._rng.randrange(len(templates))
        if len(templates) > 1 and index == self._last_template.get(player_id):
            index = (index + 1) % len(templates)
        self._last_template[player_id] = index
        template = templates[index]

        if others:
            other = others[self._rng.randrange(len(others))]
        else:
            other = "他の参加者"

        speech = template.replace("$other", other)
        return speech[: self.brain_config.max_output_chars]

    def _vote(self, request: Request, player_id: str) -> Dict[str, str]:
        candidates: Tuple[str, ...] = request.choices or tuple(
            _other_ids(request.user, player_id)
        )
        if not candidates:
            candidates = (player_id,)
        target = sorted(candidates)[self._rng.randrange(len(candidates))]
        reason = _VOTE_REASONS[self._rng.randrange(len(_VOTE_REASONS))]
        return {"target": target, "reason": reason}


def _parse_tag(tag: str) -> Tuple[str, str, str, str]:
    parts = (tag or "").split(":")
    parts += [""] * (4 - len(parts))
    return parts[0], parts[1], parts[2], parts[3]


def _other_ids(user_prompt: str, player_id: str) -> List[str]:
    """プロンプトに出てくる参加者IDのうち自分以外を、出現順の重複なしで返す。"""
    seen: List[str] = []
    for found in _PLAYER_ID_RE.findall(user_prompt):
        if found != player_id and found not in seen:
            seen.append(found)
    return seen


# --- ここから下はv2.0（8人ワンナイト）用 ---------------------------------
# v1のStubBrainは上に残してある。M3でv1を削除するとき、上をまとめて消す（設計書0.4）。

_V2_SPEECHES = [
    "$other の話は根拠が示されていないと思います。もう少し具体的に説明してもらえますか。",
    "私の情報だけでは判断できません。$other の主張と他の発言を照らして考えたいです。",
    "$other の説明は途中で内容が変わっているように見えます。そこが気になっています。",
    "現時点では $other を優先して疑う根拠がありません。他の情報を待ちたいです。",
    "役職について話せる人から先に情報を出してほしいです。$other はどう考えていますか。",
]

_V2_MEMOS = [
    "公開情報だけでは判断材料が足りないため。",
    "相手の説明の具体性を確かめたいため。",
    "自分の確定情報と矛盾しないか見たいため。",
    "投票先を決めるには根拠が不足しているため。",
]

_V2_PASS_MEMOS = [
    "情報が少ないので他の発言を待つ。",
    "今は自分から出せる材料がない。",
    "先に他の人の主張を聞きたい。",
]

_V2_ROLE_AWARENESS = "自分に通知された情報だけを持っている。"


class CaseStubBrain:
    """v2.0の応答形式を返す脳。LLMを呼ばない。

    夜の役職行動、議論前後の個別判断、発言か見送りの選択、投票の5種類を、
    設計書5.4の期待形どおりに返す。議論としては無意味だが、17ケースの生成、
    条件固定の検査、`case_log.json` と `transcript.md` の形式検証には足りる。
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
            "role_awareness": _V2_ROLE_AWARENESS,
            "suspect": "unknown",
            "confidence": 1 + self._rng.randrange(2),
            "reason": "まだ発言がないため。",
        }

    def _speak(self, request: Request) -> Dict[str, object]:
        self._speak_calls += 1
        if self._speak_calls % self.pass_every == 0:
            return {
                "speak": False,
                "memo": _V2_PASS_MEMOS[self._rng.randrange(len(_V2_PASS_MEMOS))],
            }
        others = list(request.choices) or ["他の参加者"]
        other = others[self._rng.randrange(len(others))]
        template = _V2_SPEECHES[self._rng.randrange(len(_V2_SPEECHES))]
        return {
            "speak": True,
            "speech": template.replace("$other", other),
            "memo": _V2_MEMOS[self._rng.randrange(len(_V2_MEMOS))],
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
            "memo": _V2_MEMOS[self._rng.randrange(len(_V2_MEMOS))],
        }
