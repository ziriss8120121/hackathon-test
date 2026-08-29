"""プレイヤーの生成と役職の割り当て（設計書4.3、6.3、6.6）。

役職は `trial_seed` で1回だけ配り、Trial内の17ケースはその結果を読むだけにする。
MBTI以外の条件をケース間で完全に一致させるためであり、これが条件固定の実体である。
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

ROLE_LABELS: Dict[str, str] = {
    "werewolf": "人狼",
    "seer": "占い師",
    "thief": "怪盗",
    "villager": "村人",
}

#: 最終役職が人狼なら人狼陣営。怪盗は最終役職の陣営に属する（ルール文書v0.7 §1）。
TEAM_WEREWOLF = "werewolf"
TEAM_VILLAGE = "village"


def role_label(role: str) -> str:
    return ROLE_LABELS.get(role, role)


def team_of(role: str) -> str:
    return TEAM_WEREWOLF if role == "werewolf" else TEAM_VILLAGE


@dataclass
class CasePlayer:
    """1ケースの参加者。人物属性はTrial内の17ケースで共通、役職もTrial内で固定する。

    `final_role` は怪盗の交換で変わりうるケースごとの結果なので、初期値は
    `initial_role` と同じにしておき、夜の処理で上書きする。
    """

    player_id: str
    person_id: str
    mbti: str
    age: int
    gender: str
    initial_role: str
    final_role: str

    @property
    def initial_role_label(self) -> str:
        return role_label(self.initial_role)

    @property
    def final_role_label(self) -> str:
        return role_label(self.final_role)

    @property
    def final_team(self) -> str:
        return team_of(self.final_role)

    @property
    def display_id(self) -> str:
        """人が読む出力での表記。先行実験の結果文書に合わせて大文字にする（設計書6.10）。"""

        return self.player_id.upper()

    @property
    def gender_label(self) -> str:
        return {"male": "男性", "female": "女性"}.get(self.gender, self.gender)

    def to_dict(self) -> Dict[str, object]:
        return {
            "player_id": self.player_id,
            "person_id": self.person_id,
            "mbti": self.mbti,
            "age": self.age,
            "gender": self.gender,
            "initial_role": self.initial_role,
            "final_role": self.final_role,
        }


def assign_initial_roles(role_deck: Tuple[str, ...], trial_seed: int) -> Tuple[str, ...]:
    """役職を `trial_seed` で配る（設計書6.3）。

    ルール文書v0.7 §1 の「8枚を無作為に1枚ずつ配る」に合わせ、役職の並びを
    シャッフルして `p1` から順に配る。Trialごとに1回だけ決め、17ケースは
    この結果を読むだけで再計算しない。
    """

    deck = list(role_deck)
    random.Random(trial_seed).shuffle(deck)
    return tuple(deck)


def build_case_players(
    persons: List[Dict[str, object]],
    initial_roles: Tuple[str, ...],
    homogeneous_type: Optional[str] = None,
) -> List[CasePlayer]:
    """ケースの参加者を作る。

    `homogeneous_type` を渡すと、選んだ8人のMBTIだけをそのタイプへ置き換える
    （設計書6.6）。人物・年齢・性別・役職は混合構成のケースと同じままにする。
    これが17ケースの条件固定の実体である。
    """

    if len(persons) != len(initial_roles):
        raise ValueError(
            "人数と役職の数が一致しない: 人物{0}人 / 役職{1}枚".format(
                len(persons), len(initial_roles)
            )
        )

    players: List[CasePlayer] = []
    for index, person in enumerate(persons):
        role = initial_roles[index]
        players.append(
            CasePlayer(
                player_id="p{0}".format(index + 1),
                person_id=str(person["person_id"]),
                mbti=homogeneous_type or str(person["mbti"]),
                age=int(person["age"]),
                gender=str(person["gender"]),
                initial_role=role,
                final_role=role,
            )
        )
    return players
