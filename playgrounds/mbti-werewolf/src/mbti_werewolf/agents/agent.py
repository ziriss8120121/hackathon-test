"""エージェント（設計書5.2、5.4）。

心理機能と役職からプロンプトを組み立て、脳の応答を解釈する。HTTP通信と
形式リトライは Brain 側の責務なので、ここでは扱わない。

ここが扱うのは意味の検証である。投票先が生存者を指しているかを確かめ、
指していなければ再要求する。形式の失敗（parse_failed）と意味の失敗
（invalid_retry_count、fallback）を別に記録するため、後から
「この結果は何が崩れた結果なのか」を判別できる（要件F-17、NF-05）。
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass
from pathlib import Path
from string import Template
from typing import Dict, List, Tuple

from ..brains.base import Request
from ..engine.roles import Player, role_composition_text
from ..engine.view import PublicView
from .functions import function_label, function_rule

_PROMPT_DIR = Path(__file__).resolve().parent / "prompts"
_PLAYER_ID_RE = re.compile(r"p\d+")

_ROLE_DESCRIPTIONS = {
    "villager": (
        "村人。あなたは村人です。他の参加者の役職は分かっていません。"
        "誰が人狼かを推理し、投票で当てることが目的です。"
    ),
    "werewolf": (
        "人狼。あなたは人狼です。他の参加者はあなたが人狼であることを知りません。"
        "処刑されないように振る舞い、村人に別の人を処刑させることが目的です。"
    ),
}


@dataclass
class SpeechResult:
    text: str
    parse_failed: bool
    wait_seconds: float
    retry_count: int


@dataclass
class VoteResult:
    target: str
    reason: str
    invalid_retry_count: int
    fallback: bool
    parse_failed: bool
    wait_seconds: float


class PromptSet:
    """プロンプトの文面を版ごとに読み込む（要件F-14）。

    文面を変えるときは prompts/v2/ を作って古い版を残す。過去の実行結果と
    比較するときに、どの文面で得た結果かを特定できる状態にする。
    """

    def __init__(self, version: str) -> None:
        self.version = version
        self._dir = _PROMPT_DIR / version
        if not self._dir.is_dir():
            raise FileNotFoundError(
                "プロンプトの版が見つかりません: {}".format(self._dir)
            )
        self._cache: Dict[str, Template] = {}

    def render(self, name: str, values: Dict[str, object]) -> str:
        if name not in self._cache:
            path = self._dir / "{}.md".format(name)
            self._cache[name] = Template(path.read_text(encoding="utf-8"))
        return self._cache[name].safe_substitute(values)


class Agent:
    def __init__(
        self,
        player: Player,
        config,
        brain,
        prompts: PromptSet,
        rng: random.Random,
    ) -> None:
        self.player = player
        self.config = config
        self.brain = brain
        self.prompts = prompts
        self._rng = rng

    # --- プロンプト ---------------------------------------------------------

    def _base_values(self, view: PublicView) -> Dict[str, object]:
        role_description = _ROLE_DESCRIPTIONS.get(self.player.role, self.player.role)
        if view.teammates:
            role_description += "あなたの仲間の人狼は {} です。".format(
                "、".join(view.teammates)
            )

        return {
            "player_count": self.config.player_count,
            "role_composition": role_composition_text(self.config.role_composition),
            "turn_count": view.turn_count,
            "turn": view.turn,
            "player_id": self.player.player_id,
            "role_description": role_description,
            "function": self.player.function,
            "function_label": function_label(self.player.function),
            "function_rule": function_rule(self.player.function),
            "max_output_chars": self.config.brain.max_output_chars,
            "alive_ids": "、".join(view.alive_ids),
            "vote_candidates": "、".join(view.vote_candidates),
            "speech_log": view.speech_log_text(),
        }

    def build_speak_prompt(self, view: PublicView) -> Tuple[str, str]:
        values = self._base_values(view)
        return (
            self.prompts.render("system_speak", values),
            self.prompts.render("user_speak", values),
        )

    def build_vote_prompt(self, view: PublicView) -> Tuple[str, str]:
        values = self._base_values(view)
        return (
            self.prompts.render("system_vote", values),
            self.prompts.render("user_vote", values),
        )

    # --- 発言 ---------------------------------------------------------------

    def speak(self, view: PublicView) -> SpeechResult:
        system, user = self.build_speak_prompt(view)
        response = self.brain.generate(
            Request(
                system=system,
                user=user,
                expect_keys=("speech",),
                tag=self._tag("speak"),
            )
        )

        text = ""
        if response.data:
            raw = response.data.get("speech")
            if isinstance(raw, str):
                text = raw.strip()

        parse_failed = response.parse_failed or not text
        if not text:
            # 形式が崩れたままでも試合は止めない（要件F-17）。
            # 生テキストを発言として扱い、崩れた事実は parse_failed に残す。
            text = _clean(response.text) or "（発言を生成できませんでした）"

        return SpeechResult(
            text=_truncate(text, self.config.brain.max_output_chars),
            parse_failed=parse_failed,
            wait_seconds=response.wait_seconds,
            retry_count=response.retry_count,
        )

    # --- 投票 ---------------------------------------------------------------

    def vote(self, view: PublicView) -> VoteResult:
        candidates = view.vote_candidates
        system, user = self.build_vote_prompt(view)
        max_retries = max(0, self.config.brain.max_retries)

        wait_seconds = 0.0
        invalid_retry_count = 0
        parse_failed = False
        reason = ""

        for attempt in range(max_retries + 1):
            response = self.brain.generate(
                Request(
                    system=system,
                    user=user if attempt == 0 else self._reask(user, candidates),
                    expect_keys=("target", "reason"),
                    choices=tuple(candidates),
                    tag=self._tag("vote"),
                )
            )
            wait_seconds += response.wait_seconds
            parse_failed = parse_failed or response.parse_failed

            target = _normalize_target(
                (response.data or {}).get("target"), candidates
            )
            raw_reason = (response.data or {}).get("reason")
            if isinstance(raw_reason, str) and raw_reason.strip():
                reason = _truncate(
                    raw_reason.strip(), self.config.brain.max_output_chars
                )

            if target:
                return VoteResult(
                    target=target,
                    reason=reason or "（理由なし）",
                    invalid_retry_count=attempt,
                    fallback=False,
                    parse_failed=parse_failed,
                    wait_seconds=wait_seconds,
                )
            invalid_retry_count = attempt + 1

        # 最後まで生存者を指せなかった場合もseed付き乱数で必ず1票にする。
        # 要件F-06の「常に1試合が終了する状態」をここで担保している。
        fallback_target = sorted(candidates)[self._rng.randrange(len(candidates))]
        return VoteResult(
            target=fallback_target,
            reason="脳の応答から投票先を特定できなかったため、seed付き乱数で決定した。",
            invalid_retry_count=invalid_retry_count,
            fallback=True,
            parse_failed=parse_failed,
            wait_seconds=wait_seconds,
        )

    # --- 内部 ---------------------------------------------------------------

    def _tag(self, action: str) -> str:
        return "{}:{}:{}:{}".format(
            action, self.player.function, self.player.role, self.player.player_id
        )

    def _reask(self, user: str, candidates: List[str]) -> str:
        return "\n".join(
            [
                user,
                "",
                "# 重要（投票先の再指定）",
                "前回の応答の target は生存者ではありませんでした。",
                "target は {} のいずれか1つにしてください。".format(
                    "、".join(candidates)
                ),
            ]
        )


def _normalize_target(value: object, candidates: List[str]) -> str:
    """脳が返した投票先を候補のIDに寄せる。

    小型モデルは "p2さん" や "プレイヤーp2" のように余分な語を付けることがある。
    IDとして解釈できるものだけを受け入れ、それ以外は不正として扱う。
    """
    if not isinstance(value, str):
        return ""
    text = value.strip()
    if text in candidates:
        return text
    found = _PLAYER_ID_RE.findall(text.lower())
    for candidate in found:
        if candidate in candidates:
            return candidate
    return ""


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _truncate(text: str, limit: int) -> str:
    cleaned = _clean(text)
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: max(1, limit - 1)] + "…"
