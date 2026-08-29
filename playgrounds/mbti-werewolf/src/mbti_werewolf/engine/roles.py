"""プレイヤーの生成と役職の割り当て（設計書4.3、4.4）。

心理機能は設定の並び順どおりに割り当てる（p1 が functions[0]）。役職は
seed付きランダムで割り当てる。この組み合わせにより、seedを変えるだけで
「同じ心理機能が村人のときと人狼のときで発言がどう変わるか」を比較できる。

発言順もseedで決めて記録する。順番を固定すると先頭の機能だけが常に
文脈なしで話すことになり、機能ごとの発言量の比較に偏りが入るためである。
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from ..agents.functions import function_label
from ..agents.mbti_types import TYPE_STACKS, display_name_for


@dataclass
class Player:
    player_id: str
    function: str
    role: str
    agent_prompt_version: str
    alive: bool = field(default=True, compare=False)
    #: MBTIタイプそのものでプレイヤーを定義した場合だけ入る（v1改善）。
    #: functions のみで割り当てた旧来のプレイヤーは None のままになる。
    mbti_type: Optional[str] = None
    display_name: Optional[str] = None
    function_stack: Optional[Tuple[str, str, str, str]] = None

    @property
    def team(self) -> str:
        return "werewolf" if self.role == "werewolf" else "village"

    @property
    def function_label(self) -> str:
        return function_label(self.function)

    def to_dict(self) -> Dict[str, object]:
        data: Dict[str, object] = {
            "player_id": self.player_id,
            "function": self.function,
            "role": self.role,
            "agent_prompt_version": self.agent_prompt_version,
        }
        # 旧ログの形（4キーのみ）を壊さないため、確定していないときはキー自体を付けない。
        if self.mbti_type is not None:
            data["mbti_type"] = self.mbti_type
            data["display_name"] = self.display_name
            data["function_stack"] = list(self.function_stack) if self.function_stack else None
        return data


def build_players(config, rng: random.Random, prompt_version: str) -> List[Player]:
    roles: List[str] = []
    for role, count in sorted(config.role_composition.items()):
        roles.extend([role] * count)
    rng.shuffle(roles)

    functions = list(config.functions)[: config.player_count]
    mbti_types = list(config.mbti_types)[: config.player_count] if config.mbti_types else []

    players = []
    for index in range(config.player_count):
        function = functions[index]
        mbti_type: Optional[str] = None
        display_name: Optional[str] = None
        function_stack: Optional[Tuple[str, str, str, str]] = None

        if index < len(mbti_types):
            candidate = mbti_types[index]
            stack = TYPE_STACKS.get(candidate)
            # 主機能が functions の割当と食い違う場合は紐付けない。
            # （--functions 直書きなど、旧来の使い方をそのまま通すため。）
            if stack is not None and stack[0] == function:
                mbti_type = candidate
                display_name = display_name_for(candidate)
                function_stack = stack

        players.append(
            Player(
                player_id="p{}".format(index + 1),
                function=function,
                role=roles[index],
                agent_prompt_version=prompt_version,
                mbti_type=mbti_type,
                display_name=display_name,
                function_stack=function_stack,
            )
        )
    return players


def build_speaking_order(players: List[Player], rng: random.Random) -> List[str]:
    order = [player.player_id for player in players]
    rng.shuffle(order)
    return order


def role_composition_text(role_composition: Dict[str, int]) -> str:
    labels = {"werewolf": "人狼", "villager": "村人"}
    parts = [
        "{}{}人".format(labels.get(role, role), count)
        for role, count in sorted(role_composition.items())
        if count
    ]
    return "、".join(parts)


# --- ここから下はv2.0（8人ワンナイト）用 ---------------------------------
# v1の関数は上に残してある。M3でv1を削除するとき、上をまとめて消す（設計書0.4）。

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
