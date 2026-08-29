"""夜の役職処理（設計書4.2、6.7／ルール文書v0.7 §2）。

順序は占い師 → 人狼の相互確認 → 怪盗の確認 → 怪盗の交換で固定する。この順序は
ルールセットの `night_phases` が持ち、ここでは並び替えない。

3回とも有効な回答が得られなかった場合は、その夜の能力を使用しなかったものとして
扱う。乱数で対象を埋めない（設計書5.4）。乱数で埋めた占い先を記録すると、性格構成
による確認先の選び方の分析に、本人が選んでいない値が混ざる。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..agents.agent import CaseAgent, clip_reason
from .rules import (
    PHASE_SEER_INSPECTION,
    PHASE_THIEF_INSPECTION,
    PHASE_THIEF_SWAP,
    PHASE_WEREWOLF_RECOGNITION,
    ROLE_SEER,
    ROLE_THIEF,
    ROLE_WEREWOLF,
    RuleSet,
)
from .roles import role_label
from .view import CaseViewBuilder, to_display_id, to_internal_id

SKIP_EXHAUSTED = "exhausted_attempts"


class NightResolver:
    """夜の処理を実行し、最終役職を確定させる。"""

    def __init__(
        self,
        players: List[Any],
        agents: Dict[str, CaseAgent],
        view_builder: CaseViewBuilder,
        rule_set: RuleSet,
    ) -> None:
        self._players = players
        self._agents = agents
        self._views = view_builder
        self._rules = rule_set
        self._by_id = {p.player_id: p for p in players}

    def resolve(self) -> List[Dict[str, Any]]:
        actions: List[Dict[str, Any]] = []
        #: 怪盗の確認結果を交換判断へ引き継ぐ。確認できなかった場合は交換も行わない。
        thief_target: Optional[str] = None

        for phase in self._rules.night_phases:
            if phase.phase == PHASE_SEER_INSPECTION:
                actions.extend(self._inspect(ROLE_SEER, PHASE_SEER_INSPECTION))
            elif phase.phase == PHASE_WEREWOLF_RECOGNITION:
                actions.extend(self._werewolf_recognition())
            elif phase.phase == PHASE_THIEF_INSPECTION:
                records = self._inspect(ROLE_THIEF, PHASE_THIEF_INSPECTION)
                actions.extend(records)
                for record in records:
                    if record.get("ability_used"):
                        thief_target = record["target"]
            elif phase.phase == PHASE_THIEF_SWAP:
                actions.extend(self._thief_swap(thief_target))

        return actions

    # --- 各処理 -------------------------------------------------------------

    def _actors_with_initial_role(self, role: str) -> List[Any]:
        return [p for p in self._players if p.initial_role == role]

    def _inspect(self, role: str, phase: str) -> List[Dict[str, Any]]:
        records: List[Dict[str, Any]] = []
        for actor in self._actors_with_initial_role(role):
            agent = self._agents[actor.player_id]
            view = self._views.build(actor.player_id, speeches=[])
            attempt = (
                agent.night_seer(view)
                if role == ROLE_SEER
                else agent.night_thief_inspect(view)
            )

            if not attempt.ok:
                records.append(
                    {
                        "phase": phase,
                        "actor": actor.player_id,
                        "target": None,
                        "revealed_initial_role": None,
                        "reason": "",
                        "ability_used": False,
                        "skip_reason": SKIP_EXHAUSTED,
                        "attempts": attempt.attempts,
                        "parse_failed": True,
                        "wait_seconds": round(attempt.wait_seconds, 3),
                    }
                )
                continue

            target_id = to_internal_id(attempt.data["target"])
            revealed = self._by_id[target_id].initial_role
            knowledge = self._views.knowledge_of(actor.player_id)
            if role == ROLE_SEER:
                knowledge.seer_target = target_id
                knowledge.seer_revealed_role = role_label(revealed)
            else:
                knowledge.thief_target = target_id
                knowledge.thief_revealed_role = role_label(revealed)

            records.append(
                {
                    "phase": phase,
                    "actor": actor.player_id,
                    "target": target_id,
                    "revealed_initial_role": revealed,
                    "reason": clip_reason(attempt.data.get("reason")),
                    "ability_used": True,
                    "skip_reason": None,
                    "attempts": attempt.attempts,
                    "parse_failed": False,
                    "wait_seconds": round(attempt.wait_seconds, 3),
                }
            )
        return records

    def _werewolf_recognition(self) -> List[Dict[str, Any]]:
        """人狼へ仲間を通知する。推論を呼ばないため呼び出し回数は増えない。"""

        wolves = [p.player_id for p in self._actors_with_initial_role(ROLE_WEREWOLF)]
        records: List[Dict[str, Any]] = []
        for wolf in wolves:
            partners = [other for other in wolves if other != wolf]
            self._views.knowledge_of(wolf).werewolf_partners = partners
            records.append(
                {
                    "phase": PHASE_WEREWOLF_RECOGNITION,
                    "actor": wolf,
                    "partners": partners,
                    "requires_inference": False,
                }
            )
        return records

    def _thief_swap(self, thief_target: Optional[str]) -> List[Dict[str, Any]]:
        records: List[Dict[str, Any]] = []
        for actor in self._actors_with_initial_role(ROLE_THIEF):
            if thief_target is None:
                # 確認ができなかったので交換も行わない。最終役職は怪盗のまま。
                records.append(
                    {
                        "phase": PHASE_THIEF_SWAP,
                        "actor": actor.player_id,
                        "target": None,
                        "swapped": False,
                        "actor_final_role": actor.final_role,
                        "target_final_role": None,
                        "target_notified": False,
                        "reason": "",
                        "ability_used": False,
                        "skip_reason": SKIP_EXHAUSTED,
                        "attempts": 0,
                        "parse_failed": False,
                        "wait_seconds": 0.0,
                    }
                )
                continue

            agent = self._agents[actor.player_id]
            view = self._views.build(actor.player_id, speeches=[])
            target = self._by_id[thief_target]
            attempt = agent.night_thief_swap(
                view, to_display_id(thief_target), role_label(target.initial_role)
            )

            knowledge = self._views.knowledge_of(actor.player_id)
            if not attempt.ok:
                knowledge.thief_swapped = False
                knowledge.thief_final_role = role_label(actor.final_role)
                records.append(
                    {
                        "phase": PHASE_THIEF_SWAP,
                        "actor": actor.player_id,
                        "target": thief_target,
                        "swapped": False,
                        "actor_final_role": actor.final_role,
                        "target_final_role": target.final_role,
                        "target_notified": False,
                        "reason": "",
                        "ability_used": False,
                        "skip_reason": SKIP_EXHAUSTED,
                        "attempts": attempt.attempts,
                        "parse_failed": True,
                        "wait_seconds": round(attempt.wait_seconds, 3),
                    }
                )
                continue

            swap = _as_bool(attempt.data.get("swap"))
            if swap:
                actor.final_role, target.final_role = target.final_role, actor.final_role
            knowledge.thief_swapped = swap
            knowledge.thief_final_role = role_label(actor.final_role)

            records.append(
                {
                    "phase": PHASE_THIEF_SWAP,
                    "actor": actor.player_id,
                    "target": thief_target,
                    "swapped": swap,
                    "actor_final_role": actor.final_role,
                    "target_final_role": target.final_role,
                    # 交換された側には交換も最終役職も通知しない（ルール文書v0.7 §1）。
                    "target_notified": False,
                    "reason": clip_reason(attempt.data.get("reason")),
                    "ability_used": True,
                    "skip_reason": None,
                    "attempts": attempt.attempts,
                    "parse_failed": False,
                    "wait_seconds": round(attempt.wait_seconds, 3),
                }
            )
        return records


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("true", "yes", "1")