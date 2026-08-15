"""心理機能とMBTI16タイプの対応（要求定義書6.5）。

心理機能だけで主機能を割り当てる旧方式では、MBTIは1つに決まらず候補2タイプに
なる（`mbti_candidates_text` 系）。v1改善では4人MVPをMBTIタイプそのもので
定義できるようにし、タイプが確定しているプレイヤーはタイプ名と表示名で
一意に表示する（`player_identity_text` 系）。タイプが確定していない
プレイヤー（旧ログ、`--functions` 直接指定など）は従来どおり候補2タイプの
表示にフォールバックする。
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

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

# CLAUDE.mdの4人MVPロースター。討論者/擁護者/仲介者/幹部の順で
# E/I・N/S・T/F・P/Jが2:2になる組み合わせ。
DEFAULT_MBTI_TYPES: List[str] = ["ENTP", "ISFJ", "INFP", "ESTJ"]

DISPLAY_NAMES: Dict[str, str] = {
    "ENTP": "討論者",
    "ISFJ": "擁護者",
    "INFP": "仲介者",
    "ESTJ": "幹部",
}


def display_name_for(mbti_type: str) -> Optional[str]:
    """MBTIタイプの日本語表示名。未定義のタイプはNoneを返す。"""
    return DISPLAY_NAMES.get(mbti_type)


def function_stack_for(mbti_type: str) -> Optional[Tuple[str, str, str, str]]:
    """MBTIタイプの4機能スタック（主/補助/第三/劣等）。未知のタイプはNoneを返す。"""
    return TYPE_STACKS.get(mbti_type)


def types_for_dominant(function: str) -> List[str]:
    """主機能から、要求定義書6.5の候補タイプを返す。"""
    return list(DOMINANT_TO_TYPES.get(function, []))


def mbti_candidates_text(function: str) -> str:
    types = types_for_dominant(function)
    return " / ".join(types) if types else "—"


def player_mbti_text(player_id: str, function: str) -> str:
    return "{}（{}）→ {}".format(player_id, function, mbti_candidates_text(function))


def mbti_type_label(mbti_type: str, display_name: Optional[str] = None) -> str:
    """確定したMBTIタイプの短い表示文字列（例: ENTP（討論者））。"""
    name = display_name if display_name is not None else display_name_for(mbti_type)
    return "{}（{}）".format(mbti_type, name) if name else mbti_type


def player_identity_text(
    player_id: str,
    function: str,
    mbti_type: Optional[str] = None,
    display_name: Optional[str] = None,
) -> str:
    """プレイヤーの表示用テキストを作る。

    mbti_type が確定していればそれを使い、無ければ主機能からの候補2タイプ
    （旧仕様）にフォールバックする。
    """
    if mbti_type:
        return "{}（{}）→ {}".format(player_id, function, mbti_type_label(mbti_type, display_name))
    return player_mbti_text(player_id, function)


def winning_mbti_text(players: Sequence[dict], winner: str) -> str:
    """勝った陣営のプレイヤーを、MBTI表示つきで並べる。"""
    if winner not in ("village", "werewolf"):
        return "（決着していません）"
    wanted_role = "werewolf" if winner == "werewolf" else "villager"
    parts = [
        player_identity_text(
            player.get("player_id", ""),
            player.get("function", ""),
            player.get("mbti_type"),
            player.get("display_name"),
        )
        for player in players
        if player.get("role") == wanted_role
    ]
    return "、".join(parts) or "（記録なし）"
