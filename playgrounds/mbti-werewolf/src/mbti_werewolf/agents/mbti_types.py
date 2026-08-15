"""心理機能とMBTI16タイプの対応（要求定義書6.5）。

初回MVPは1エージェントにつき主機能を1つだけ持つ。主機能が同じタイプは
2つあるため、MBTIは1つに決まらず候補2タイプとして出す。
"""

from __future__ import annotations

from typing import Dict, List, Sequence, Tuple

# 要求定義書6.5の機能スタック。並びは 主 / 補助 / 第三 / 劣等。
TYPE_STACKS: Dict[str, Tuple[str, str, str, str]] = {
    "ISTJ": ("Si", "Te", "Fi", "Ne"),
    "ISFJ": ("Si", "Fe", "Ti", "Ne"),
    "INFJ": ("Ni", "Fe", "Ti", "Se"),
    "INTJ": ("Ni", "Te", "Fi", "Se"),
    "ISTP": ("Ti", "Se", "Ni", "Fe"),
    "ISFP": ("Fi", "Se", "Ni", "Te"),
    "INFP": ("Fi", "Ne", "Si", "Te"),
    "INTP": ("Ti", "Ne", "Si", "Fe"),
    "ESTP": ("Se", "Ti", "Fe", "Ni"),
    "ESFP": ("Se", "Fi", "Te", "Ni"),
    "ENFP": ("Ne", "Fi", "Te", "Si"),
    "ENTP": ("Ne", "Ti", "Fe", "Si"),
    "ESTJ": ("Te", "Si", "Ne", "Fi"),
    "ESFJ": ("Fe", "Si", "Ne", "Ti"),
    "ENFJ": ("Fe", "Ni", "Se", "Ti"),
    "ENTJ": ("Te", "Ni", "Se", "Fi"),
}

# 画面へ渡す用。主機能ごとの候補タイプ。TYPE_STACKSの出現順を保つ。
DOMINANT_TO_TYPES: Dict[str, List[str]] = {}
for _type_name, _stack in TYPE_STACKS.items():
    DOMINANT_TO_TYPES.setdefault(_stack[0], []).append(_type_name)


def types_for_dominant(function: str) -> List[str]:
    """主機能から、要求定義書6.5の候補タイプを返す。"""
    return list(DOMINANT_TO_TYPES.get(function, []))


def mbti_candidates_text(function: str) -> str:
    types = types_for_dominant(function)
    return " / ".join(types) if types else "—"


def player_mbti_text(player_id: str, function: str) -> str:
    return "{}（{}）→ {}".format(player_id, function, mbti_candidates_text(function))


def winning_mbti_text(players: Sequence[dict], winner: str) -> str:
    """勝った陣営のプレイヤーを、主機能からのMBTI候補つきで並べる。"""
    if winner not in ("village", "werewolf"):
        return "（決着していません）"
    wanted_role = "werewolf" if winner == "werewolf" else "villager"
    parts = [
        player_mbti_text(player.get("player_id", ""), player.get("function", ""))
        for player in players
        if player.get("role") == wanted_role
    ]
    return "、".join(parts) or "（記録なし）"
