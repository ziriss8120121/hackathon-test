"""MBTI16タイプと機能スタックの対応（要求定義書6.5、設計書0.4）。

v2.0ではプレイヤーのMBTIタイプが人物プールで必ず確定するため、主機能から候補
2タイプを推定する経路は持たない。ここが持つのは、タイプ順の正本（17ケースの並び
順が `TYPE_STACKS` の定義順に従う）と、プロンプトへ入れてはいけない語の一覧
（日本語表示名）である。
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple

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

#: 日本語表示名。人が読む出力には使わず、プロンプトへ混入していないかの検査に使う。
#: エージェントへ自分のタイプを悟らせないため、16タイプすべてを列挙する（設計書5.2）。
DISPLAY_NAMES: Dict[str, str] = {
    "ISTJ": "管理者",
    "ISFJ": "擁護者",
    "INFJ": "提唱者",
    "INTJ": "建築家",
    "ISTP": "巨匠",
    "ISFP": "冒険家",
    "INFP": "仲介者",
    "INTP": "論理学者",
    "ESTP": "起業家",
    "ESFP": "エンターテイナー",
    "ENFP": "運動家",
    "ENTP": "討論者",
    "ESTJ": "幹部",
    "ESFJ": "領事",
    "ENFJ": "主人公",
    "ENTJ": "指揮官",
}


def display_name_for(mbti_type: str) -> Optional[str]:
    """MBTIタイプの日本語表示名。未定義のタイプはNoneを返す。"""
    return DISPLAY_NAMES.get(mbti_type)


def function_stack_for(mbti_type: str) -> Optional[Tuple[str, str, str, str]]:
    """MBTIタイプの4機能スタック（主/補助/第三/劣等）。未知のタイプはNoneを返す。"""
    return TYPE_STACKS.get(mbti_type)
