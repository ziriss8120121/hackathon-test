"""v2.0のエージェント（設計書5.3、5.4）。

ルール文書v0.7 §1 が定める「最初の指示を含めて回答機会は最大3回」をここで数える。
形式の失敗（JSONにならない）と意味の失敗（自分自身の指定、候補外の値）を同じ
「無効な回答」として扱い、どちらも再送の対象にする。3回とも無効だった場合の
扱いはフェーズごとに違うため、呼び出し側へ結果を返して判断させる。

`agents/agent.py` はv1の4人版が使っているので触らない。M3でv1を削除するときに、
このファイルを `agent.py` へ統合する（設計書0.4）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from ..brains.base import Request
from ..engine.view import CaseView, to_internal_id
from .persona import (
    CONFIDENCE_SCALE,
    CONFIDENCE_VALUES,
    SUSPECT_UNKNOWN,
    PersonaBuilder,
    confidence_scale_text,
)

MEMO_MAX_CHARS = 60
REASON_MAX_CHARS = 60


@dataclass
class Attempted:
    """1回のフェーズの結果。回答機会を何回使ったかを必ず持つ。"""

    data: Optional[Dict[str, Any]]
    attempts: int
    parse_failed: bool
    wait_seconds: float
    raw_text: str = ""
    invalid_reasons: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.data is not None and not self.parse_failed


def _clip(value: object, limit: int) -> str:
    text = "" if value is None else str(value).strip()
    text = " ".join(text.split())
    return text[:limit]


class CaseAgent:
    """1人の参加者。夜の行動、個別判断、発言、投票を担う。"""

    def __init__(
        self,
        player,
        brain,
        persona: PersonaBuilder,
        max_response_attempts: int = 3,
        max_speech_chars: int = 200,
    ) -> None:
        self.player = player
        self.brain = brain
        self.persona = persona
        self.max_response_attempts = max_response_attempts
        self.max_speech_chars = max_speech_chars

    # --- 共通の呼び出し ------------------------------------------------------

    def _ask(
        self,
        view: CaseView,
        template_name: str,
        tag: str,
        expect_keys: Sequence[str],
        choices: Sequence[str] = (),
        validate=None,
        **values: object,
    ) -> Attempted:
        """有効な回答が得られるまで最大 `max_response_attempts` 回問い合わせる。

        `validate` は意味の検証を行い、不正なら理由の文字列を返す。返した時点で
        その回答は無効とみなし、同じ指示を送り直す（ルール文書v0.7 §2-2、§2-4、§2-6）。
        """

        system = self.persona.build_system(view)
        user = self.persona.prompts.render(template_name, **values)
        request = Request(
            system=system,
            user=user,
            expect_keys=tuple(expect_keys),
            choices=tuple(choices),
            tag="{0}:{1}".format(tag, self.player.player_id),
        )

        wait_total = 0.0
        reasons: List[str] = []
        last_text = ""
        for attempt in range(1, self.max_response_attempts + 1):
            response = self.brain.generate(request)
            wait_total += response.wait_seconds
            last_text = response.text

            if response.parse_failed or response.data is None:
                reasons.append("解析できない応答")
                continue

            problem = validate(response.data) if validate else None
            if problem:
                reasons.append(problem)
                continue

            return Attempted(
                data=response.data,
                attempts=attempt,
                parse_failed=False,
                wait_seconds=wait_total,
                raw_text=last_text,
                invalid_reasons=reasons,
            )

        return Attempted(
            data=None,
            attempts=self.max_response_attempts,
            parse_failed=True,
            wait_seconds=wait_total,
            raw_text=last_text,
            invalid_reasons=reasons,
        )

    def _target_validator(self, candidates: Sequence[str], key: str = "target"):
        """候補外・自分自身の指定を無効な回答として扱う（ルール文書v0.7 §2-2、§2-6）。

        大文字と小文字のどちらで返ってきても内部表記へ揃えて比較する。プロンプトへは
        `P1` の形で渡しているが、モデルが `p1` を返すことは形式の誤りとは扱わない。
        """

        allowed = {to_internal_id(c) for c in candidates}

        def validate(data: Dict[str, Any]) -> Optional[str]:
            value = data.get(key)
            if not isinstance(value, str):
                return "{0} が文字列でない".format(key)
            normalized = to_internal_id(value)
            if normalized == self.player.player_id:
                return "自分自身を指定している"
            if normalized not in allowed:
                return "候補外の指定: {0}".format(value)
            return None

        return validate

    # --- 夜 -----------------------------------------------------------------

    def night_seer(self, view: CaseView) -> Attempted:
        shown = view.vote_candidates_display
        return self._ask(
            view,
            "user_night_seer",
            "night_seer",
            expect_keys=("target",),
            choices=shown,
            validate=self._target_validator(shown),
            candidates=self.persona.candidates_text(shown),
        )

    def night_thief_inspect(self, view: CaseView) -> Attempted:
        shown = view.vote_candidates_display
        return self._ask(
            view,
            "user_night_thief_inspect",
            "night_thief_inspect",
            expect_keys=("target",),
            choices=shown,
            validate=self._target_validator(shown),
            candidates=self.persona.candidates_text(shown),
        )

    def night_thief_swap(
        self, view: CaseView, target: str, revealed_role_label: str
    ) -> Attempted:
        def validate(data: Dict[str, Any]) -> Optional[str]:
            value = data.get("swap")
            if isinstance(value, bool):
                return None
            if isinstance(value, str) and value.lower() in ("true", "false"):
                return None
            return "swap が真偽値でない"

        # `swap: false` は正当な回答だが expect_keys の空値判定に落ちるため、
        # キーの存在だけを見る expect_keys を渡さず validate 側で確かめる。
        return self._ask(
            view,
            "user_night_thief_swap",
            "night_thief_swap",
            expect_keys=(),
            choices=("true", "false"),
            validate=validate,
            target=target,
            revealed_role_label=revealed_role_label,
        )

    # --- 個別判断 ------------------------------------------------------------

    def pre_discussion(self, view: CaseView) -> Attempted:
        shown = view.vote_candidates_display
        allowed = {to_internal_id(c) for c in shown} | {SUSPECT_UNKNOWN}

        def validate(data: Dict[str, Any]) -> Optional[str]:
            suspect = to_internal_id(data.get("suspect", ""))
            if suspect not in allowed:
                return "suspect が候補外: {0}".format(data.get("suspect"))
            if _parse_confidence(data.get("confidence")) is None:
                return "confidence が1〜5でない"
            return None

        return self._ask(
            view,
            "user_pre_discussion",
            "pre_discussion",
            expect_keys=("role_awareness", "suspect"),
            choices=tuple(shown) + (SUSPECT_UNKNOWN,),
            validate=validate,
            candidates=self.persona.candidates_text(shown),
            confidence_scale=confidence_scale_text(),
        )

    def pre_vote(self, view: CaseView) -> Attempted:
        shown = view.vote_candidates_display
        allowed = {to_internal_id(c) for c in shown}

        def validate(data: Dict[str, Any]) -> Optional[str]:
            # 投票直前では unknown を認めない（設計書5.3）。
            for key in ("suspect", "planned_vote"):
                value = to_internal_id(data.get(key, ""))
                if value == self.player.player_id:
                    return "{0} に自分自身を指定している".format(key)
                if value not in allowed:
                    return "{0} が候補外: {1}".format(key, data.get(key))
            if _parse_confidence(data.get("confidence")) is None:
                return "confidence が1〜5でない"
            return None

        return self._ask(
            view,
            "user_pre_vote",
            "pre_vote",
            expect_keys=("suspect", "planned_vote"),
            choices=shown,
            validate=validate,
            candidates=self.persona.candidates_text(shown),
            confidence_scale=confidence_scale_text(),
            speech_log=view.speech_log_text(),
        )

    # --- 議論 -----------------------------------------------------------------

    def speak(self, view: CaseView, round_no: int) -> Attempted:
        def validate(data: Dict[str, Any]) -> Optional[str]:
            spoke = _parse_bool(data.get("speak"))
            if spoke is None:
                return "speak が真偽値でない"
            if spoke and not str(data.get("speech", "")).strip():
                # 空回答は正常な発言として数えない（ルール文書v0.7 §2-5）。
                return "speak が true なのに speech が空"
            return None

        return self._ask(
            view,
            "user_speak",
            "speak",
            expect_keys=(),
            choices=view.vote_candidates_display,
            validate=validate,
            round_no=round_no,
            speech_log=view.speech_log_text(),
            max_speech_chars=self.max_speech_chars,
        )

    # --- 投票 -----------------------------------------------------------------

    def vote(self, view: CaseView) -> Attempted:
        shown = view.vote_candidates_display
        return self._ask(
            view,
            "user_vote",
            "vote",
            expect_keys=("target",),
            choices=shown,
            validate=self._target_validator(shown),
            candidates=self.persona.candidates_text(shown),
            speech_log=view.speech_log_text(),
        )


def _parse_bool(value: object) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("true", "yes", "1"):
            return True
        if lowered in ("false", "no", "0"):
            return False
    return None


def _parse_confidence(value: object) -> Optional[int]:
    """1〜5の整数だけを受ける（設計書5.3）。"""

    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number if number in CONFIDENCE_SCALE else None


def clip_memo(value: object) -> str:
    return _clip(value, MEMO_MAX_CHARS)


def clip_reason(value: object) -> str:
    return _clip(value, REASON_MAX_CHARS)


def parse_confidence(value: object) -> Optional[int]:
    return _parse_confidence(value)


def parse_bool(value: object) -> Optional[bool]:
    return _parse_bool(value)
