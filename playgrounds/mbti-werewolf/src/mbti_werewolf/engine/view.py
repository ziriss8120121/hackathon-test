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


# --- ここから下はv2.0（8人ワンナイト）用 ---------------------------------
# v1のPublicViewは上に残してある。M3でv1を削除するとき、上をまとめて消す（設計書0.4）。


def to_display_id(player_id: str) -> str:
    """プロンプトと人が読む出力での表記（設計書6.10）。

    内部の `player_id` は `p1`〜`p8` の小文字、外向きは `P1`〜`P8` の大文字にする。
    先行実験の結果文書が大文字を使っているため、エージェントの発言に自然に大文字が
    現れるようプロンプト側も大文字で統一する。
    """

    return player_id.upper()


def to_internal_id(value: str) -> str:
    """エージェントの応答を内部の表記へ戻す。大文字・小文字のどちらでも受ける。"""

    return str(value).strip().lower()


@dataclass
class CaseSpeech:
    """公開された発言。見送りとスキップはここへ入れない（設計書4.7）。

    他者が見送ったかどうかをエージェントへ渡さない。見送りが公開情報になると
    「黙っていること」が場に見える行動になり、ルールに定めのない情報を議論へ
    持ち込むことになる。
    """

    order: int
    round: int
    player_id: str
    text: str

    @property
    def display_id(self) -> str:
        return to_display_id(self.player_id)


@dataclass
class NightKnowledge:
    """夜にGMから個別通知された確定情報。本人にしか渡さない。"""

    #: 人狼が知る仲間の player_id。占い師・怪盗・村人では空になる。
    werewolf_partners: List[str] = field(default_factory=list)
    #: 占い師が確認した相手と、その開始時役職。
    seer_target: Optional[str] = None
    seer_revealed_role: Optional[str] = None
    #: 怪盗が確認した相手と、その開始時役職。
    thief_target: Optional[str] = None
    thief_revealed_role: Optional[str] = None
    #: 怪盗が交換したか。交換した場合だけ本人へ最終役職を通知する。
    thief_swapped: Optional[bool] = None
    thief_final_role: Optional[str] = None

    def to_dict(self) -> Dict[str, object]:
        return {
            "werewolf_partners": list(self.werewolf_partners),
            "seer_target": self.seer_target,
            "seer_revealed_role": self.seer_revealed_role,
            "thief_target": self.thief_target,
            "thief_revealed_role": self.thief_revealed_role,
            "thief_swapped": self.thief_swapped,
            "thief_final_role": self.thief_final_role,
        }


@dataclass
class CaseView:
    """あるプレイヤーの視点で見えている情報のすべて（設計書4.7）。

    MBTIタイプ、他者の役職、他者の個別判断、構成種別、実験であること自体は
    ここへ載せない。載せていないことを10章のテストで検証する。
    """

    viewer_id: str
    viewer_age: int
    viewer_gender_label: str
    viewer_initial_role: str
    viewer_initial_role_label: str
    tendency_text: str
    others: List[Dict[str, object]] = field(default_factory=list)
    all_ids: List[str] = field(default_factory=list)
    night: NightKnowledge = field(default_factory=NightKnowledge)
    speeches: List[CaseSpeech] = field(default_factory=list)
    round: int = 1

    @property
    def viewer_display_id(self) -> str:
        return to_display_id(self.viewer_id)

    @property
    def vote_candidates(self) -> List[str]:
        """自分以外の7人（内部表記）。自分への投票は認めない（ルール文書v0.7 §1）。"""

        return [pid for pid in self.all_ids if pid != self.viewer_id]

    @property
    def vote_candidates_display(self) -> List[str]:
        """プロンプトへ渡す候補。大文字にする。"""

        return [to_display_id(pid) for pid in self.vote_candidates]

    def participants_text(self) -> str:
        lines = [
            "- {0}（あなた）: {1}歳 / {2}".format(
                self.viewer_display_id, self.viewer_age, self.viewer_gender_label
            )
        ]
        for other in self.others:
            lines.append(
                "- {0}: {1}歳 / {2}".format(
                    to_display_id(str(other["player_id"])),
                    other["age"],
                    other["gender_label"],
                )
            )
        return "\n".join(lines)

    def speech_log_text(self, empty: str = "（まだ発言はありません）") -> str:
        if not self.speeches:
            return empty
        return "\n".join(
            "{0}. {1}: {2}".format(s.order, s.display_id, s.text) for s in self.speeches
        )

    def night_info_text(self, empty: str = "（あなたに個別通知された夜の情報はありません）") -> str:
        lines: List[str] = []
        night = self.night
        if night.werewolf_partners:
            lines.append(
                "あなたの開始時の人狼仲間は {0} です。これは確定情報です。".format(
                    "、".join(to_display_id(p) for p in night.werewolf_partners)
                )
            )
        if night.seer_target is not None:
            lines.append(
                "あなたが確認した {0} の開始時の役職は「{1}」でした。".format(
                    to_display_id(night.seer_target), night.seer_revealed_role
                )
            )
        if night.thief_target is not None:
            lines.append(
                "あなたが確認した {0} の開始時の役職は「{1}」でした。".format(
                    to_display_id(night.thief_target), night.thief_revealed_role
                )
            )
        if night.thief_swapped is True:
            lines.append(
                "交換を実行しました。あなたの最終役職は「{0}」です。".format(night.thief_final_role)
            )
        elif night.thief_swapped is False:
            lines.append("交換は実行されませんでした。あなたの最終役職は「怪盗」です。")
        return "\n".join(lines) if lines else empty

    def to_dict(self) -> Dict[str, object]:
        return {
            "viewer_id": self.viewer_id,
            "viewer_age": self.viewer_age,
            "viewer_initial_role": self.viewer_initial_role,
            "others": [dict(o) for o in self.others],
            "night": self.night.to_dict(),
            "round": self.round,
            "speeches": [
                {"order": s.order, "round": s.round, "player_id": s.player_id, "text": s.text}
                for s in self.speeches
            ],
        }


class CaseViewBuilder:
    """v2.0のエージェント入力を組み立てる唯一の場所（設計書4.7）。

    ここを通らない入力経路を作らないことで、情報の非対称性を1か所へ閉じる。
    """

    def __init__(self, players, tendencies: Dict[str, str]) -> None:
        self._players = list(players)
        self._tendencies = dict(tendencies)
        self._night: Dict[str, NightKnowledge] = {
            p.player_id: NightKnowledge() for p in self._players
        }

    def knowledge_of(self, player_id: str) -> NightKnowledge:
        return self._night[player_id]

    def build(
        self,
        viewer_id: str,
        speeches: List[CaseSpeech],
        round_no: int = 1,
    ) -> CaseView:
        viewer = self._find(viewer_id)
        others = [
            {
                "player_id": p.player_id,
                "age": p.age,
                "gender_label": p.gender_label,
            }
            for p in self._players
            if p.player_id != viewer_id
        ]
        return CaseView(
            viewer_id=viewer.player_id,
            viewer_age=viewer.age,
            viewer_gender_label=viewer.gender_label,
            viewer_initial_role=viewer.initial_role,
            viewer_initial_role_label=viewer.initial_role_label,
            tendency_text=self._tendencies.get(viewer.mbti, ""),
            others=others,
            all_ids=[p.player_id for p in self._players],
            night=self._night[viewer_id],
            speeches=list(speeches),
            round=round_no,
        )

    def _find(self, player_id: str):
        for player in self._players:
            if player.player_id == player_id:
                return player
        raise KeyError("プレイヤーが見つかりません: {}".format(player_id))
