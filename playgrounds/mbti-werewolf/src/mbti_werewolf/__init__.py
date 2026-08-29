"""MBTI人狼シミュレーター（AI先行テスト用）。

MBTIタイプごとの行動傾向を持つAIエージェントに8人ワンナイト人狼をさせ、
性格傾向の差が推理と議論に現れるかを観察するためのシミュレーターである。

MBTIは実在人物の診断ではなく、エージェントの振る舞いを分けるための
フィクション設定として扱う（要件NF-12）。
"""

from .config import INDICATOR_VERSION, JUDGE_CRITERIA_VERSION, PERSONA_PROMPT_VERSION

__all__ = ["PERSONA_PROMPT_VERSION", "JUDGE_CRITERIA_VERSION", "INDICATOR_VERSION"]
__version__ = "0.2.0"
