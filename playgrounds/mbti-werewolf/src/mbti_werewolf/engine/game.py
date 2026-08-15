"""ゲームの進行（設計書3.2、3.3、4.1）。

フェーズ進行、投票集計、同数の決着、勝敗判定を担う。プロンプトの文面もHTTP通信も
ここには持たない。脳の具体実装を知らないため、推論手段を差し替えても
このモジュールは変わらない（要件F-15）。

失敗しても途中までの記録は保持する。BrainError を送出したあとでも
partial_record() でそれまでの発言と投票を取り出せる（要件F-37）。
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from ..agents.agent import Agent, PromptSet
from .roles import Player, build_players, build_speaking_order
from .tiebreak import break_tie
from .view import PublicViewBuilder, Speech

ProgressHook = Callable[[str, int], None]


@dataclass
class GameRecord:
    """1試合の中身。run_log.json はこの内容から組み立てる。"""

    players: List[Player] = field(default_factory=list)
    speaking_order: List[str] = field(default_factory=list)
    turns: List[Dict[str, Any]] = field(default_factory=list)
    votes: List[Dict[str, Any]] = field(default_factory=list)
    result: Optional[Dict[str, Any]] = None
    phase: str = "setup"
    ai_wait_seconds: float = 0.0


class GameEngine:
    def __init__(
        self,
        config,
        brain,
        prompt_version: str,
        on_progress: Optional[ProgressHook] = None,
    ) -> None:
        self.config = config
        self.brain = brain
        self.prompt_version = prompt_version
        self._on_progress = on_progress
        self.record = GameRecord()

        # 割当・発言順・フォールバックで使う乱数はすべてこのseedから導く。
        # 同じseedなら同じ結果になる（要件F-21、F-22）。
        self._setup_rng = random.Random(config.seed)
        self._fallback_rng = random.Random(config.seed + 1)

        self._speeches: List[Speech] = []
        self._agents: Dict[str, Agent] = {}
        self._view_builder: Optional[PublicViewBuilder] = None

    # --- 公開API -----------------------------------------------------------

    def run(self) -> GameRecord:
        self._setup()
        self._discuss()
        votes = self._collect_votes()
        self._judge(votes)
        self._set_phase("finished")
        return self.record

    def partial_record(self) -> GameRecord:
        return self.record

    # --- フェーズ -----------------------------------------------------------

    def _setup(self) -> None:
        self._set_phase("setup", turn=0)
        players = build_players(self.config, self._setup_rng, self.prompt_version)
        order = build_speaking_order(players, self._setup_rng)

        self.record.players = players
        self.record.speaking_order = order
        self._view_builder = PublicViewBuilder(players)

        prompts = PromptSet(self.prompt_version)
        self._agents = {
            player.player_id: Agent(
                player=player,
                config=self.config,
                brain=self.brain,
                prompts=prompts,
                rng=self._fallback_rng,
            )
            for player in players
        }

    def _discuss(self) -> None:
        for turn in range(1, self.config.turn_count + 1):
            self._set_phase("day_discussion", turn=turn)
            for player_id in self._alive_speaking_order():
                view = self._build_view(player_id, turn)
                result = self._agents[player_id].speak(view)

                self._speeches.append(
                    Speech(turn=turn, player_id=player_id, text=result.text)
                )
                self.record.turns.append(
                    {
                        "turn": turn,
                        "player_id": player_id,
                        "speech_text": result.text,
                        # 過去ログ参照（要件F-18）は未実装のため常に空。
                        "referenced_history_ids": [],
                        "parse_failed": result.parse_failed,
                        "retry_count": result.retry_count,
                        "wait_seconds": round(result.wait_seconds, 3),
                    }
                )
                self.record.ai_wait_seconds += result.wait_seconds

    def _collect_votes(self) -> List[Dict[str, Any]]:
        self._set_phase("vote", turn=self.config.turn_count)
        votes: List[Dict[str, Any]] = []

        for player_id in self._alive_speaking_order():
            view = self._build_view(player_id, self.config.turn_count)
            result = self._agents[player_id].vote(view)

            vote = {
                "voter": player_id,
                "target": result.target,
                "reason": result.reason,
                "invalid_retry_count": result.invalid_retry_count,
                "fallback": result.fallback,
                "parse_failed": result.parse_failed,
                "wait_seconds": round(result.wait_seconds, 3),
            }
            votes.append(vote)
            self.record.votes.append(vote)
            self.record.ai_wait_seconds += result.wait_seconds

        return votes

    def _judge(self, votes: List[Dict[str, Any]]) -> None:
        counts: Dict[str, int] = {}
        for vote in votes:
            counts[vote["target"]] = counts.get(vote["target"], 0) + 1

        top = max(counts.values()) if counts else 0
        leaders = sorted(pid for pid, count in counts.items() if count == top)

        tie_break: Optional[Dict[str, Any]] = None
        if len(leaders) > 1:
            self._set_phase("tie_break", turn=self.config.turn_count)
            executed, tie_break = break_tie(
                leaders, self.config.seed, self.config.turn_count
            )
        else:
            executed = leaders[0]

        self._set_phase("judge", turn=self.config.turn_count)
        executed_player = self._player(executed)
        executed_player.alive = False

        winner = "village" if executed_player.role == "werewolf" else "werewolf"
        self.record.result = {
            "executed": executed,
            "executed_role": executed_player.role,
            "executed_function": executed_player.function,
            "executed_mbti_type": executed_player.mbti_type,
            "executed_display_name": executed_player.display_name,
            "winner": winner,
            "vote_counts": {pid: counts.get(pid, 0) for pid in sorted(counts)},
            "tie_break": tie_break,
        }

    # --- 内部 ---------------------------------------------------------------

    def _alive_speaking_order(self) -> List[str]:
        alive = {p.player_id for p in self.record.players if p.alive}
        return [pid for pid in self.record.speaking_order if pid in alive]

    def _build_view(self, player_id: str, turn: int):
        assert self._view_builder is not None
        return self._view_builder.build(
            viewer_id=player_id,
            speeches=self._speeches,
            turn=turn,
            turn_count=self.config.turn_count,
        )

    def _player(self, player_id: str) -> Player:
        for player in self.record.players:
            if player.player_id == player_id:
                return player
        raise KeyError("プレイヤーが見つかりません: {}".format(player_id))

    def _set_phase(self, phase: str, turn: Optional[int] = None) -> None:
        self.record.phase = phase
        if self._on_progress is not None:
            self._on_progress(phase, 0 if turn is None else turn)
