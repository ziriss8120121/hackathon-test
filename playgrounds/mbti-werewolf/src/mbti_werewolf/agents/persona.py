"""人格プロンプトの組み立て（設計書5.2、5.3）。

MBTIタイプ名、日本語表示名、「MBTI」「16タイプ」「心理機能」の語をプロンプトへ
書かない。Agent設定文書 §「MBTIに関する認識と管理条件」が、参加者はMBTIという
概念そのものを知らないと定めているためである。タイプ間で変わるのは行動傾向の
1文だけにし、ルール記述・前提部・出力形式は全タイプで揃える。
"""

from __future__ import annotations

import json
from pathlib import Path
from string import Template
from typing import Dict, List, Optional

from ..engine.view import CaseView

PROMPT_VERSION = "v2"

CONFIDENCE_SCALE: Dict[int, str] = {
    1: "まったく自信がない",
    2: "あまり自信がない",
    3: "どちらとも言えない",
    4: "やや自信がある",
    5: "強く自信がある",
}

CONFIDENCE_VALUES = tuple(str(v) for v in sorted(CONFIDENCE_SCALE))

SUSPECT_UNKNOWN = "unknown"

#: 役職ごとの行動指針。ルール文書v0.7 §3 の内容をそのまま渡す。
ROLE_GUIDES: Dict[str, str] = {
    "werewolf": (
        "あなたの目的は、最終役職が人狼の参加者を誰も追放させないことです。\n"
        "公開議論では自分や仲間を守るため、真実・推理・演技を使ってかまいません。"
        "ただし、仲間の名前は確定情報です。仲間を本当に人狼候補として推理してはいけません。\n"
        "GMから知らされていない役職・夜の結果を知っている前提で発言しないでください。"
    ),
    "seer": (
        "あなたの目的は、村人陣営が最終役職の人狼を追放できるようにすることです。\n"
        "確認した結果をそのまま話すか、伏せるか、別の主張をするか、発言を見送るかは自分で選べます。\n"
        "確認していない参加者の役職を確定情報として扱ってはいけません。"
        "怪盗の交換後の最終役職も、GMから通知されない限り知っている前提にしないでください。"
    ),
    "thief": (
        "あなたの目的は、交換後の自分の最終役職が属する陣営が勝つことです。\n"
        "確認した内容や交換したかどうかを話すか伏せるかは自分で選べます。\n"
        "GMから知らされていない役職・夜の結果を知っている前提で発言しないでください。"
    ),
    "villager": (
        "あなたの目的は、最終役職が人狼の参加者を少なくとも1人追放することです。\n"
        "夜に得られる情報はありません。公開情報と自分の推理だけで議論します。\n"
        "夜の行動結果や他者の役職を、GMから通知なしに知っている前提で発言しないでください。"
    ),
}


class PersonaError(Exception):
    """プロンプトの素材が揃っていない。"""


def prompts_dir(version: str = PROMPT_VERSION) -> Path:
    return Path(__file__).resolve().parent / "prompts" / version


def load_tendencies(version: str = PROMPT_VERSION) -> Dict[str, str]:
    """16タイプの行動傾向文を読む。コードから文面を分離している（設計書5.2）。"""

    path = prompts_dir(version) / "tendencies.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    tendencies = {
        mbti: str(entry["text"]) for mbti, entry in raw["tendencies"].items()
    }
    if len(tendencies) != 16:
        raise PersonaError(
            "行動傾向文が16タイプ揃っていない: {0}件".format(len(tendencies))
        )
    return tendencies


def tendency_sources(version: str = PROMPT_VERSION) -> Dict[str, str]:
    """タイプごとの文面の出自。先行実験の実績文か新規作成文かを区別する（設計書5.2）。"""

    path = prompts_dir(version) / "tendencies.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {mbti: str(entry["source"]) for mbti, entry in raw["tendencies"].items()}


def confidence_scale_text() -> str:
    return "\n".join(
        "- {0}: {1}".format(value, CONFIDENCE_SCALE[value])
        for value in sorted(CONFIDENCE_SCALE)
    )


class PromptSet:
    """`prompts/{version}/` のテンプレートを読み込んで保持する。"""

    def __init__(self, version: str = PROMPT_VERSION) -> None:
        self.version = version
        self._dir = prompts_dir(version)
        if not self._dir.is_dir():
            raise PersonaError("プロンプトのディレクトリがない: {0}".format(self._dir))
        self._cache: Dict[str, Template] = {}

    def template(self, name: str) -> Template:
        if name not in self._cache:
            path = self._dir / "{0}.md".format(name)
            if not path.is_file():
                raise PersonaError("プロンプトファイルがない: {0}".format(path))
            self._cache[name] = Template(path.read_text(encoding="utf-8"))
        return self._cache[name]

    def render(self, name: str, **values: object) -> str:
        return self.template(name).safe_substitute(**values)


class PersonaBuilder:
    """systemプロンプトを組み立てる。userプロンプトは各フェーズが作る。"""

    def __init__(
        self,
        prompt_set: Optional[PromptSet] = None,
        max_speech_chars: int = 200,
    ) -> None:
        self.prompts = prompt_set or PromptSet()
        self.max_speech_chars = max_speech_chars

    def build_system(self, view: CaseView) -> str:
        rules = self.prompts.render(
            "system_rules", max_speech_chars=self.max_speech_chars
        )
        context = self.prompts.render(
            "system_context",
            viewer_id=view.viewer_id,
            viewer_age=view.viewer_age,
            viewer_gender_label=view.viewer_gender_label,
            participants=view.participants_text(),
            tendency=view.tendency_text,
        )
        role = self.prompts.render(
            "system_role",
            initial_role_label=view.viewer_initial_role_label,
            role_guide=ROLE_GUIDES.get(view.viewer_initial_role, ""),
            night_info=view.night_info_text(),
        )
        return "\n\n".join(part.strip() for part in (rules, context, role) if part.strip())

    def candidates_text(self, candidates: List[str]) -> str:
        return "、".join(candidates)
