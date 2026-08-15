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

from .base import BrainResponse, Request

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
