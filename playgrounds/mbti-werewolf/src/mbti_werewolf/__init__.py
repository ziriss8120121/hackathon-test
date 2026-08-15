"""MBTI人狼シミュレーター（AI先行テスト用）。

心理機能を行動ルールとして持つAIエージェントに人狼をさせ、
行動ルールの差がログに現れるかを観察するためのシミュレーターである。

MBTIは実在人物の診断ではなく、エージェントの振る舞いを分けるための
フィクション設定として扱う（要件NF-12）。
"""

from .config import SCHEMA_VERSION, PROMPT_VERSION

__all__ = ["SCHEMA_VERSION", "PROMPT_VERSION"]
__version__ = "0.1.0"
