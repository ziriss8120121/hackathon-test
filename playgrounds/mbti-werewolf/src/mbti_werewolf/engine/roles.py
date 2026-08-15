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
