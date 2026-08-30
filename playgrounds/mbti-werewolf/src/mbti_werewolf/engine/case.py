"""1ケースのフェーズ進行（設計書4.3）。

setup → night → pre_discussion_answer → free_discussion → pre_vote_answer → vote →
judge_result（または invalid_game）→ finished の順に進む。

`judge_result` は勝敗判定のフェーズであり、会話の事後評価（Judge）とは別のもので
ある。記録上は勝敗判定を `judge_result`、事後評価を `judge_review` として区別する。
"""

from __future__ import annotations

import copy
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..agents.agent import CaseAgent, clip_reason, parse_confidence
from ..agents.persona import PersonaBuilder, PromptSet, SUSPECT_UNKNOWN, load_tendencies
from .discussion import DiscussionRunner, DiscussionResult
from .night import NightResolver
from .rules import RuleSet
from .view import CaseViewBuilder, to_internal_id
from .vote import VoteResolver

PHASE_SETUP = "setup"
PHASE_NIGHT = "night"
PHASE_PRE_DISCUSSION = "pre_discussion_answer"
PHASE_FREE_DISCUSSION = "free_discussion"
PHASE_PRE_VOTE = "pre_vote_answer"
PHASE_VOTE = "vote"
PHASE_JUDGE_RESULT = "judge_result"
PHASE_INVALID_GAME = "invalid_game"
PHASE_FINISHED = "finished"


@dataclass
class CaseOutcome:
    """1ケースの実行結果。`record/case_log.py` がこれを読んで正本を書く。"""

    players: List[Any]
    night_actions: List[Dict[str, Any]] = field(default_factory=list)
    pre_discussion_answers: List[Dict[str, Any]] = field(default_factory=list)
    discussion: Optional[DiscussionResult] = None
    pre_vote_answers: List[Dict[str, Any]] = field(default_factory=list)
    votes: List[Dict[str, Any]] = field(default_factory=list)
    result: Dict[str, Any] = field(default_factory=dict)
    phase: str = PHASE_SETUP
    started_at: str = ""
    ended_at: str = ""
    elapsed_seconds: float = 0.0
    ai_wait_seconds: float = 0.0
    inference_calls: int = 0


class CaseEngine:
    """1ケースを完走させる。出力ファイルの書き込みは行わない。"""

    def __init__(
        self,
        case_plan,
        rule_set: RuleSet,
        config,
        brain,
        trial_seed: int,
        prompt_set: Optional[PromptSet] = None,
        tendencies: Optional[Dict[str, str]] = None,
    ) -> None:
        self.plan = case_plan
        self.rules = rule_set
        self.config = config
        self.brain = brain
        self.trial_seed = trial_seed
        # ケースごとに役職が変わるため、Trialの座席をそのまま使わず複製する。
        # 怪盗の交換で final_role を書き換えるので、共有すると他ケースへ漏れる。
        self.players = copy.deepcopy(list(case_plan.players))
        self._prompt_set = prompt_set or PromptSet(config.persona_prompt_version)
        self._tendencies = tendencies or load_tendencies(config.persona_prompt_version)

    def run(self) -> CaseOutcome:
        started = time.perf_counter()
        outcome = CaseOutcome(
            players=self.players,
            started_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        )

        views = CaseViewBuilder(self.players, self._tendencies)
        persona = PersonaBuilder(
            self._prompt_set, max_speech_chars=self.config.discussion.max_speech_chars
        )
        agents = {
            player.player_id: CaseAgent(
                player,
                self.brain,
                persona,
                max_response_attempts=self.rules.max_response_attempts,
                max_speech_chars=self.config.discussion.max_speech_chars,
            )
            for player in self.players
        }

        outcome.phase = PHASE_NIGHT
        outcome.night_actions = NightResolver(
            self.players, agents, views, self.rules
        ).resolve()

        outcome.phase = PHASE_PRE_DISCUSSION
        outcome.pre_discussion_answers = self._collect_pre_discussion(agents, views)

        outcome.phase = PHASE_FREE_DISCUSSION
        outcome.discussion = DiscussionRunner(
            self.players,
            agents,
            views,
            self.config.discussion,
            self.plan.case_id,
            self.trial_seed,
        ).run()

        outcome.phase = PHASE_PRE_VOTE
        outcome.pre_vote_answers = self._collect_pre_vote(
            agents, views, outcome.discussion
        )

        outcome.phase = PHASE_VOTE
        resolver = VoteResolver(
            self.players, agents, views, self.rules.vote.min_votes_to_execute
        )
        outcome.votes = resolver.collect(outcome.discussion.speeches)
        outcome.result = resolver.resolve(outcome.votes)

        outcome.phase = (
            PHASE_JUDGE_RESULT if outcome.result["valid"] else PHASE_INVALID_GAME
        )

        outcome.elapsed_seconds = round(time.perf_counter() - started, 3)
        outcome.ended_at = datetime.now().astimezone().isoformat(timespec="seconds")
        outcome.ai_wait_seconds = round(self._sum_wait(outcome), 3)
        outcome.inference_calls = self._sum_calls(outcome)
        outcome.phase = PHASE_FINISHED
        return outcome

    # --- 個別判断 ------------------------------------------------------------

    def _collect_pre_discussion(self, agents, views) -> List[Dict[str, Any]]:
        answers: List[Dict[str, Any]] = []
        for player in self.players:
            view = views.build(player.player_id, speeches=[])
            attempt = agents[player.player_id].pre_discussion(view)

            if not attempt.ok:
                answers.append(
                    {
                        "player_id": player.player_id,
                        "role_awareness": "",
                        "suspect": SUSPECT_UNKNOWN,
                        "confidence": None,
                        "reason": "",
                        "parse_failed": True,
                        "attempts": attempt.attempts,
                        "wait_seconds": round(attempt.wait_seconds, 3),
                    }
                )
                continue

            answers.append(
                {
                    "player_id": player.player_id,
                    "role_awareness": clip_reason(attempt.data.get("role_awareness")),
                    "suspect": to_internal_id(attempt.data["suspect"]),
                    "confidence": parse_confidence(attempt.data.get("confidence")),
                    "reason": clip_reason(attempt.data.get("reason")),
                    "parse_failed": False,
                    "attempts": attempt.attempts,
                    "wait_seconds": round(attempt.wait_seconds, 3),
                }
            )
        return answers

    def _collect_pre_vote(self, agents, views, discussion) -> List[Dict[str, Any]]:
        answers: List[Dict[str, Any]] = []
        for player in self.players:
            view = views.build(player.player_id, speeches=discussion.speeches)
            attempt = agents[player.player_id].pre_vote(view)

            if not attempt.ok:
                answers.append(
                    {
                        "player_id": player.player_id,
                        "suspect": None,
                        "confidence": None,
                        "reason": "",
                        "planned_vote": None,
                        "parse_failed": True,
                        "attempts": attempt.attempts,
                        "wait_seconds": round(attempt.wait_seconds, 3),
                    }
                )
                continue

            answers.append(
                {
                    "player_id": player.player_id,
                    "suspect": to_internal_id(attempt.data["suspect"]),
                    "confidence": parse_confidence(attempt.data.get("confidence")),
                    "reason": clip_reason(attempt.data.get("reason")),
                    "planned_vote": to_internal_id(attempt.data["planned_vote"]),
                    "parse_failed": False,
                    "attempts": attempt.attempts,
                    "wait_seconds": round(attempt.wait_seconds, 3),
                }
            )
        return answers

    # --- 集計 ---------------------------------------------------------------

    def _sum_wait(self, outcome: CaseOutcome) -> float:
        total = sum(a.get("wait_seconds", 0.0) for a in outcome.night_actions)
        total += sum(a.get("wait_seconds", 0.0) for a in outcome.pre_discussion_answers)
        total += sum(a.get("wait_seconds", 0.0) for a in outcome.pre_vote_answers)
        total += sum(v.get("wait_seconds", 0.0) for v in outcome.votes)
        if outcome.discussion:
            total += outcome.discussion.wait_seconds
        return total

    def _sum_calls(self, outcome: CaseOutcome) -> int:
        total = sum(a.get("attempts", 0) for a in outcome.night_actions)
        total += sum(a.get("attempts", 0) for a in outcome.pre_discussion_answers)
        total += sum(a.get("attempts", 0) for a in outcome.pre_vote_answers)
        total += sum(v.get("attempts", 0) for v in outcome.votes)
        if outcome.discussion:
            total += outcome.discussion.inference_calls
        return total
