"""エージェントへ渡す公開情報の組み立て（設計書2.2、5.3）。

要件F-11（役職による情報の非対称性）を構造で守るための層である。エージェントは
ゲームの内部状態を直接受け取らず、必ずこのモジュールが作った PublicView だけを
入力にする。他者の役職は PublicView に載せない。

人が結果を読むための timeline.md には役職を書くが、それは record/ 側の仕事であり、
エージェント入力を組み立てるのはこのモジュールだけに限定する。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .roles import Player


@dataclass
class Speech:
    turn: int
    player_id: str
    text: str


@dataclass
class PublicView:
    """あるプレイヤーの視点から見えている情報。"""

    viewer_id: str
    viewer_function: str
    viewer_role: str
    #: 自分と同じ人狼陣営の他プレイヤー。村人視点では必ず空になる。
    teammates: List[str] = field(default_factory=list)
    alive_ids: List[str] = field(default_factory=list)
    all_ids: List[str] = field(default_factory=list)
    turn: int = 1
    turn_count: int = 1
    speeches: List[Speech] = field(default_factory=list)

    @property
    def vote_candidates(self) -> List[str]:
        return [pid for pid in self.alive_ids if pid != self.viewer_id]

    def speech_log_text(self, empty: str = "（まだ発言はありません）") -> str:
        if not self.speeches:
            return empty
        return "\n".join(
            "- ターン{} {}: {}".format(speech.turn, speech.player_id, speech.text)
            for speech in self.speeches
        )

    def to_dict(self) -> Dict[str, object]:
        return {
            "viewer_id": self.viewer_id,
            "viewer_function": self.viewer_function,
            "viewer_role": self.viewer_role,
            "teammates": list(self.teammates),
            "alive_ids": list(self.alive_ids),
            "turn": self.turn,
            "turn_count": self.turn_count,
            "speeches": [
                {"turn": s.turn, "player_id": s.player_id, "text": s.text}
                for s in self.speeches
            ],
        }


class PublicViewBuilder:
    """公開情報だけを組み立てる。ゲーム進行の状態は書き換えない。"""

    def __init__(self, players: List[Player]) -> None:
        self._players = players

    def build(
        self,
        viewer_id: str,
        speeches: List[Speech],
        turn: int,
        turn_count: int,
        alive_ids: Optional[List[str]] = None,
    ) -> PublicView:
        viewer = self._find(viewer_id)
        alive = (
            list(alive_ids)
            if alive_ids is not None
            else [p.player_id for p in self._players if p.alive]
        )

        teammates: List[str] = []
        if viewer.role == "werewolf":
            teammates = [
                p.player_id
                for p in self._players
                if p.role == "werewolf" and p.player_id != viewer_id and p.alive
            ]

        return PublicView(
            viewer_id=viewer.player_id,
            viewer_function=viewer.function,
            viewer_role=viewer.role,
            teammates=teammates,
            alive_ids=alive,
            all_ids=[p.player_id for p in self._players],
            turn=turn,
            turn_count=turn_count,
            speeches=list(speeches),
        )

    def _find(self, player_id: str) -> Player:
        for player in self._players:
            if player.player_id == player_id:
                return player
        raise KeyError("プレイヤーが見つかりません: {}".format(player_id))
