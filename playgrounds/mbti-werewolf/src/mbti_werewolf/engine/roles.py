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
from typing import Dict, List

from ..agents.functions import function_label


@dataclass
class Player:
    player_id: str
    function: str
    role: str
    agent_prompt_version: str
    alive: bool = field(default=True, compare=False)

    @property
    def team(self) -> str:
        return "werewolf" if self.role == "werewolf" else "village"

    @property
    def function_label(self) -> str:
        return function_label(self.function)

    def to_dict(self) -> Dict[str, str]:
        return {
            "player_id": self.player_id,
            "function": self.function,
            "role": self.role,
            "agent_prompt_version": self.agent_prompt_version,
        }


def build_players(config, rng: random.Random, prompt_version: str) -> List[Player]:
    roles: List[str] = []
    for role, count in sorted(config.role_composition.items()):
        roles.extend([role] * count)
    rng.shuffle(roles)

    functions = list(config.functions)[: config.player_count]
    return [
        Player(
            player_id="p{}".format(index + 1),
            function=functions[index],
            role=roles[index],
            agent_prompt_version=prompt_version,
        )
        for index in range(config.player_count)
    ]


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
