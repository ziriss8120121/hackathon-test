"""v2.0（8人ワンナイト）のテスト共通の道具（設計書10章）。

v1の `conftest.py` は4人版の設定と応答形式を前提にしているため、v2.0用は別に置く。
fixtureは `conftest.py` から取り込む。M3でv1を削除するときに統合する（設計書0.4）。
"""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Optional

import pytest

from mbti_werewolf import experiment as experiment_module
from mbti_werewolf import experiment_config as ec
from mbti_werewolf import masterdata as md
from mbti_werewolf.brains.base import BrainResponse, Request
from mbti_werewolf.engine import rules as rules_module
from mbti_werewolf.engine.case import CaseEngine


class ScriptedBrain:
    """tagごとに応答テキストを決められる脳。

    `responder(tag, player_id, request, call_index)` が文字列を返せばそれが応答に
    なる。JSONにならない文字列を返せば、Agent側の再送と3回失敗の経路を通せる。
    """

    provider = "scripted"
    name = "scripted"
    endpoint_kind = "stub"

    def __init__(self, responder: Callable[..., str]) -> None:
        self.responder = responder
        self.calls: List[Dict[str, Any]] = []

    def describe(self) -> Dict[str, str]:
        return {
            "provider": self.provider,
            "model": "scripted",
            "endpoint_kind": self.endpoint_kind,
            "name": self.name,
        }

    def generate(self, request: Request) -> BrainResponse:
        tag, _, player_id = (request.tag or "").partition(":")
        index = len(self.calls)
        self.calls.append(
            {
                "tag": tag,
                "player_id": player_id,
                "system": request.system,
                "user": request.user,
                "choices": request.choices,
            }
        )
        text = self.responder(tag, player_id, request, index)
        try:
            data = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            return BrainResponse(text=text, data=None, parse_failed=True)
        if not isinstance(data, dict):
            return BrainResponse(text=text, data=None, parse_failed=True)
        return BrainResponse(text=text, data=data)

    def prompts_for(self, player_id: str) -> List[str]:
        """あるプレイヤーへ渡した system と user の全文。情報漏れの検査に使う。"""

        return [
            call["system"] + "\n" + call["user"]
            for call in self.calls
            if call["player_id"] == player_id
        ]

    def prompts_excluding(self, player_id: str) -> List[str]:
        return [
            call["system"] + "\n" + call["user"]
            for call in self.calls
            if call["player_id"] != player_id
        ]


def default_responder(
    speak: bool = True,
    speech: str = "現時点では判断材料が足りないと思います。",
) -> Callable[..., str]:
    """全フェーズで有効な応答を返す responder。"""

    def responder(tag: str, player_id: str, request: Request, index: int) -> str:
        first = request.choices[0] if request.choices else "p1"
        if tag in ("night_seer", "night_thief_inspect", "vote"):
            payload: Dict[str, Any] = {"target": first, "reason": "理由。", "memo": "memo。"}
        elif tag == "night_thief_swap":
            payload = {"swap": False, "reason": "理由。"}
        elif tag == "pre_discussion":
            payload = {
                "role_awareness": "自分の情報だけを持っている。",
                "suspect": "unknown",
                "confidence": 2,
                "reason": "まだ発言がない。",
            }
        elif tag == "pre_vote":
            payload = {
                "suspect": first,
                "confidence": 4,
                "reason": "説明が足りない。",
                "planned_vote": first,
            }
        elif tag == "speak":
            payload = (
                {"speak": True, "speech": speech, "memo": "確かめたい。"}
                if speak
                else {"speak": False, "memo": "今は待つ。"}
            )
        else:
            raise AssertionError("未知のtag: {0}".format(tag))
        return json.dumps(payload, ensure_ascii=False)

    return responder


@pytest.fixture
def v2_data_dir():
    return experiment_module.default_data_dir()


@pytest.fixture
def v2_inputs(v2_data_dir):
    """プール、パターン、ルールセットを読み込んで返す。"""

    pool = md.load_person_pool(v2_data_dir / "persons" / "pool-001.json")
    pattern_set = md.load_pattern_set(
        v2_data_dir / "patterns" / "pattern-set-001.json", pool
    )
    rule_set = rules_module.load_rule_set(
        rules_module.rule_set_path(v2_data_dir, "onenight-8p-v0.7")
    )
    return pool, pattern_set, rule_set


@pytest.fixture
def v2_config():
    def build(**overrides: Any) -> ec.ExperimentConfig:
        overrides.setdefault("machine_name", "test")
        return ec.load_config(overrides=overrides)

    return build


@pytest.fixture
def build_trial(v2_inputs, v2_config):
    def build(trial_index: int = 1, **config_overrides: Any):
        pool, pattern_set, rule_set = v2_inputs
        config = v2_config(**config_overrides)
        plan = experiment_module.build_experiment(
            config, rule_set, pool, pattern_set, experiment_id="e-20260101-000000"
        )
        return plan.trials[trial_index - 1], config, rule_set

    return build


@pytest.fixture
def case_log(run_case):
    """1ケースを実行して `case_log.json` の中身を返す。出力形式の検査に使う。"""

    from mbti_werewolf.record.case_log import build_case_log

    def build(responder: Optional[Callable[..., str]] = None, **kwargs: Any):
        outcome, brain, case, trial, config, rule_set = run_case(responder, **kwargs)
        log = build_case_log(
            case, outcome, config, rule_set, brain.describe(), trial
        )
        return log, outcome, brain

    return build


@pytest.fixture
def run_case(build_trial):
    """1ケースを実行して (case_log用の素材, brain) を返す。"""

    def run(
        responder: Optional[Callable[..., str]] = None,
        case_index: int = 0,
        **config_overrides: Any,
    ):
        trial, config, rule_set = build_trial(**config_overrides)
        case = trial.cases[case_index]
        brain = ScriptedBrain(responder or default_responder())
        engine = CaseEngine(case, rule_set, config, brain, trial.trial_seed)
        outcome = engine.run()
        return outcome, brain, case, trial, config, rule_set

    return run
