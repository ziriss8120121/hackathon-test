"""ルールセットの読み込みと検証（設計書4.1、4.2）。

ルールをコードへ埋め込まず `data/rules/{rule_set_id}.json` から読む。ルール文書を
改訂したときにコードを触らず差し替えられる状態にするため（NF-11）。未実装の
フェーズや役職があれば実行前に停止する。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

ROLE_WEREWOLF = "werewolf"
ROLE_SEER = "seer"
ROLE_THIEF = "thief"
ROLE_VILLAGER = "villager"

KNOWN_ROLES = (ROLE_WEREWOLF, ROLE_SEER, ROLE_THIEF, ROLE_VILLAGER)

PHASE_SEER_INSPECTION = "seer_inspection"
PHASE_WEREWOLF_RECOGNITION = "werewolf_recognition"
PHASE_THIEF_INSPECTION = "thief_inspection"
PHASE_THIEF_SWAP = "thief_swap"

KNOWN_NIGHT_PHASES = (
    PHASE_SEER_INSPECTION,
    PHASE_WEREWOLF_RECOGNITION,
    PHASE_THIEF_INSPECTION,
    PHASE_THIEF_SWAP,
)

DAY_PRE_DISCUSSION = "pre_discussion_answer"
DAY_FREE_DISCUSSION = "free_discussion"
DAY_PRE_VOTE = "pre_vote_answer"
DAY_VOTE = "vote"

KNOWN_DAY_PHASES = (DAY_PRE_DISCUSSION, DAY_FREE_DISCUSSION, DAY_PRE_VOTE, DAY_VOTE)

EXECUTE_ALL_TOP_VOTED = "all_top_voted"
INVALID_GAME_NO_VALID_VOTES = "no_valid_votes"

ON_EXHAUSTED_SKIP_ABILITY = "skip_ability"
ON_EXHAUSTED_ABSTAIN = "abstain"

VILLAGE_WINS_IF_ANY_WEREWOLF_EXECUTED = "any_executed_final_role_is_werewolf"
WIN_BASIS_FINAL_ROLE = "final_role"

DEFAULT_RULE_SET_ID = "onenight-8p-v0.7"


class RuleSetError(Exception):
    """ルールセットが不正、または未実装の値を含む。"""


@dataclass(frozen=True)
class NightPhase:
    phase: str
    actor_role: str
    requires_inference: bool
    target: Optional[str] = None
    reveals: Optional[str] = None
    choices: Tuple[str, ...] = ()
    effect: Optional[str] = None
    notify_actor_final_role: bool = False
    notify_target: bool = False
    on_exhausted_attempts: Optional[str] = None


@dataclass(frozen=True)
class VoteRules:
    rounds: int
    self_vote: bool
    revote: bool
    on_exhausted_attempts: str
    execute: str
    min_votes_to_execute: int
    invalid_game_if: str


@dataclass(frozen=True)
class WinCondition:
    basis: str
    village_wins_if: str


@dataclass(frozen=True)
class RuleSet:
    rule_set_id: str
    rule_set_version: str
    source_document: str
    player_count: int
    center_cards: int
    role_composition: Dict[str, int]
    max_response_attempts: int
    night_phases: Tuple[NightPhase, ...]
    day_phases: Tuple[str, ...]
    discussion_mode: str
    vote: VoteRules
    win_condition: WinCondition
    raw: Dict[str, Any]

    def role_deck(self) -> Tuple[str, ...]:
        """役職の並び。`[人狼, 人狼, 占い師, 怪盗, 村人, 村人, 村人, 村人]` を作る。

        並びを役職名の辞書順ではなく `KNOWN_ROLES` の順で固定する。同じルールJSONから
        常に同じ並びが作られないと、`trial_seed` を揃えても役職割当が一致しない。
        """

        deck = []
        for role in KNOWN_ROLES:
            deck.extend([role] * self.role_composition.get(role, 0))
        return tuple(deck)

    def to_dict(self) -> Dict[str, Any]:
        return dict(self.raw)


def _require(raw: Dict[str, Any], key: str) -> Any:
    if key not in raw:
        raise RuleSetError("ルールセットに {0} がない".format(key))
    return raw[key]


def _parse_night_phase(raw: Dict[str, Any]) -> NightPhase:
    phase = str(_require(raw, "phase"))
    if phase not in KNOWN_NIGHT_PHASES:
        raise RuleSetError(
            "未実装の夜フェーズ: {0}（実装済み: {1}）".format(phase, " / ".join(KNOWN_NIGHT_PHASES))
        )
    actor_role = str(_require(raw, "actor_role"))
    if actor_role not in KNOWN_ROLES:
        raise RuleSetError("未知の役職: {0}".format(actor_role))
    on_exhausted = raw.get("on_exhausted_attempts")
    if on_exhausted is not None and on_exhausted != ON_EXHAUSTED_SKIP_ABILITY:
        raise RuleSetError(
            "夜フェーズ {0} の on_exhausted_attempts が未実装: {1}".format(phase, on_exhausted)
        )
    return NightPhase(
        phase=phase,
        actor_role=actor_role,
        requires_inference=bool(_require(raw, "requires_inference")),
        target=raw.get("target"),
        reveals=raw.get("reveals"),
        choices=tuple(str(c) for c in raw.get("choices", ())),
        effect=raw.get("effect"),
        notify_actor_final_role=bool(raw.get("notify_actor_final_role", False)),
        notify_target=bool(raw.get("notify_target", False)),
        on_exhausted_attempts=on_exhausted,
    )


def parse_rule_set(raw: Dict[str, Any]) -> RuleSet:
    player_count = int(_require(raw, "player_count"))
    composition_raw = _require(raw, "role_composition")
    if not isinstance(composition_raw, dict):
        raise RuleSetError("role_composition はオブジェクトにする")

    composition: Dict[str, int] = {}
    for role, count in composition_raw.items():
        if role not in KNOWN_ROLES:
            raise RuleSetError(
                "未実装の役職: {0}（実装済み: {1}）".format(role, " / ".join(KNOWN_ROLES))
            )
        composition[str(role)] = int(count)

    total = sum(composition.values())
    center_cards = int(raw.get("center_cards", 0))
    if total + center_cards != player_count:
        raise RuleSetError(
            "役職構成の合計が参加人数と一致しない: 役職{0} + 中央{1} != {2}".format(
                total, center_cards, player_count
            )
        )

    night_phases = tuple(_parse_night_phase(item) for item in _require(raw, "night_phases"))

    day_phases = tuple(str(p) for p in _require(raw, "day_phases"))
    unknown_day = [p for p in day_phases if p not in KNOWN_DAY_PHASES]
    if unknown_day:
        raise RuleSetError("未実装の昼フェーズ: {0}".format(", ".join(unknown_day)))

    discussion = _require(raw, "discussion")
    discussion_mode = str(_require(discussion, "mode"))
    if discussion_mode != "free":
        raise RuleSetError(
            "未実装の議論方式: {0}（実装済み: free）".format(discussion_mode)
        )

    vote_raw = _require(raw, "vote")
    execute = str(_require(vote_raw, "execute"))
    if execute != EXECUTE_ALL_TOP_VOTED:
        raise RuleSetError("未実装の追放判定: {0}".format(execute))
    on_exhausted_vote = str(_require(vote_raw, "on_exhausted_attempts"))
    if on_exhausted_vote != ON_EXHAUSTED_ABSTAIN:
        raise RuleSetError("未実装の投票失敗時の扱い: {0}".format(on_exhausted_vote))
    invalid_game_if = str(_require(vote_raw, "invalid_game_if"))
    if invalid_game_if != INVALID_GAME_NO_VALID_VOTES:
        raise RuleSetError("未実装の無効試合条件: {0}".format(invalid_game_if))
    if bool(vote_raw.get("revote", False)):
        raise RuleSetError("再投票は未実装（ルール文書v0.7は再投票を持たない）")
    if bool(vote_raw.get("self_vote", False)):
        raise RuleSetError("自分への投票は認めない（ルール文書v0.7 §1）")

    vote = VoteRules(
        rounds=int(vote_raw.get("rounds", 1)),
        self_vote=False,
        revote=False,
        on_exhausted_attempts=on_exhausted_vote,
        execute=execute,
        min_votes_to_execute=int(vote_raw.get("min_votes_to_execute", 2)),
        invalid_game_if=invalid_game_if,
    )

    win_raw = _require(raw, "win_condition")
    basis = str(_require(win_raw, "basis"))
    if basis != WIN_BASIS_FINAL_ROLE:
        raise RuleSetError("未実装の勝敗判定基準: {0}".format(basis))
    village_wins_if = str(_require(win_raw, "village_wins_if"))
    if village_wins_if != VILLAGE_WINS_IF_ANY_WEREWOLF_EXECUTED:
        raise RuleSetError("未実装の勝敗条件: {0}".format(village_wins_if))

    max_attempts = int(_require(raw, "max_response_attempts"))
    if max_attempts < 1:
        raise RuleSetError("max_response_attempts は1以上にする: {0}".format(max_attempts))

    return RuleSet(
        rule_set_id=str(_require(raw, "rule_set_id")),
        rule_set_version=str(_require(raw, "rule_set_version")),
        source_document=str(raw.get("source_document", "")),
        player_count=player_count,
        center_cards=center_cards,
        role_composition=composition,
        max_response_attempts=max_attempts,
        night_phases=night_phases,
        day_phases=day_phases,
        discussion_mode=discussion_mode,
        vote=vote,
        win_condition=WinCondition(basis=basis, village_wins_if=village_wins_if),
        raw=dict(raw),
    )


def load_rule_set(path: Path) -> RuleSet:
    return parse_rule_set(json.loads(Path(path).read_text(encoding="utf-8")))


def rule_set_path(data_dir: Path, rule_set_id: str) -> Path:
    return Path(data_dir) / "rules" / "{0}.json".format(rule_set_id)
