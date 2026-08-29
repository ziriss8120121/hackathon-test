"""投票の収集と追放判定（設計書4.6／ルール文書v0.7 §1、§2-6）。

同率最多者は全員追放する。最多得票が1票のみなら誰も追放しない。有効票が0票なら
無効試合として終了し、勝敗を付けない。

3回とも有効な投票が得られなかった参加者は棄権とし、その票を集計に含めない。
乱数で投票先を埋めない（設計書5.4）。本人が決めていない値を投票先として記録すると、
9.1の投票正解率に偽の値が混ざる。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..agents.agent import CaseAgent, clip_memo
from .roles import team_of
from .view import CaseSpeech, CaseViewBuilder, to_internal_id

INVALID_NO_VALID_VOTES = "no_valid_votes"
NO_EXECUTION_TOP_IS_ONE = "top_vote_count_is_one"

WINNER_VILLAGE = "village"
WINNER_WEREWOLF = "werewolf"


@dataclass
class VoteOutcome:
    votes: List[Dict[str, Any]] = field(default_factory=list)
    result: Dict[str, Any] = field(default_factory=dict)

    @property
    def wait_seconds(self) -> float:
        return sum(v.get("wait_seconds", 0.0) for v in self.votes)

    @property
    def inference_calls(self) -> int:
        return sum(v.get("attempts", 0) for v in self.votes)


class VoteResolver:
    def __init__(
        self,
        players: List[Any],
        agents: Dict[str, CaseAgent],
        view_builder: CaseViewBuilder,
        min_votes_to_execute: int = 2,
    ) -> None:
        self._players = players
        self._agents = agents
        self._views = view_builder
        self._min_votes = min_votes_to_execute

    def collect(self, speeches: List[CaseSpeech]) -> List[Dict[str, Any]]:
        votes: List[Dict[str, Any]] = []
        for player in self._players:
            agent = self._agents[player.player_id]
            view = self._views.build(player.player_id, speeches=speeches)
            attempt = agent.vote(view)

            if not attempt.ok:
                votes.append(
                    {
                        "voter": player.player_id,
                        "target": None,
                        "memo": "",
                        "abstained": True,
                        "attempts": attempt.attempts,
                        "parse_failed": True,
                        "wait_seconds": round(attempt.wait_seconds, 3),
                    }
                )
                continue

            votes.append(
                {
                    "voter": player.player_id,
                    "target": to_internal_id(attempt.data["target"]),
                    "memo": clip_memo(attempt.data.get("memo")),
                    "abstained": False,
                    "attempts": attempt.attempts,
                    "parse_failed": False,
                    "wait_seconds": round(attempt.wait_seconds, 3),
                }
            )
        return votes

    def resolve(self, votes: List[Dict[str, Any]]) -> Dict[str, Any]:
        tally: Dict[str, int] = {}
        for vote in votes:
            if vote["abstained"]:
                continue
            tally[vote["target"]] = tally.get(vote["target"], 0) + 1

        valid_vote_count = sum(1 for v in votes if not v["abstained"])
        abstain_count = len(votes) - valid_vote_count

        if valid_vote_count == 0:
            # 有効票が1票もない。追放判定・勝敗判定を行わない（ルール文書v0.7 §1）。
            return {
                "vote_tally": {},
                "valid_vote_count": 0,
                "abstain_count": abstain_count,
                "top_vote_count": 0,
                "executed": [],
                "executed_count": 0,
                "executed_roles": [],
                "no_execution_reason": None,
                "winner": None,
                "valid": False,
                "invalid_reason": INVALID_NO_VALID_VOTES,
            }

        top_vote_count = max(tally.values())
        if top_vote_count < self._min_votes:
            executed: List[str] = []
            no_execution_reason: Optional[str] = NO_EXECUTION_TOP_IS_ONE
        else:
            executed = sorted(pid for pid, count in tally.items() if count == top_vote_count)
            no_execution_reason = None

        by_id = {p.player_id: p for p in self._players}
        executed_roles = [
            {
                "player_id": pid,
                "initial_role": by_id[pid].initial_role,
                "final_role": by_id[pid].final_role,
            }
            for pid in executed
        ]

        # 追放者の中に最終役職が人狼の参加者が1人以上いれば村人陣営の勝ち。
        # 人数によらず同じ判定式になる（設計書4.6）。
        village_wins = any(
            team_of(entry["final_role"]) == WINNER_WEREWOLF for entry in executed_roles
        )

        return {
            "vote_tally": dict(sorted(tally.items())),
            "valid_vote_count": valid_vote_count,
            "abstain_count": abstain_count,
            "top_vote_count": top_vote_count,
            "executed": executed,
            "executed_count": len(executed),
            "executed_roles": executed_roles,
            "no_execution_reason": no_execution_reason,
            "winner": WINNER_VILLAGE if village_wins else WINNER_WEREWOLF,
            "valid": True,
            "invalid_reason": None,
        }
