"""v2.0の応答の受け取りと回答機会の数え方（設計書10章 test_brain_parse／5.4、6.4）。

ルール文書v0.7 §1 の「最初の指示を含めて回答機会は最大3回」を守るには、Brainの
内部再送とAgentの再送が二重に掛からないことが必要である。二重になると、記録上の
`attempts` と実際の呼び出し回数がずれ、所要時間の見積もりも合わなくなる。
"""

from __future__ import annotations

import json

import pytest

from mbti_werewolf.agents.case_agent import CaseAgent
from mbti_werewolf.agents.persona import PersonaBuilder, PromptSet, load_tendencies
from mbti_werewolf.brains.base import BrainResponse, Request, extract_json
from mbti_werewolf.brains.factory import create_case_brain
from mbti_werewolf.brains.stub import CaseStubBrain
from mbti_werewolf.engine.view import CaseViewBuilder


@pytest.fixture
def agent_for(build_trial):
    """1人のエージェントと、その視点のビューを返す。"""

    def build(brain, player_index: int = 0):
        trial, config, rules = build_trial()
        players = trial.cases[0].players
        tendencies = load_tendencies(config.persona_prompt_version)
        views = CaseViewBuilder(players, tendencies)
        player = players[player_index]
        agent = CaseAgent(
            player,
            brain,
            PersonaBuilder(
                PromptSet(config.persona_prompt_version),
                max_speech_chars=config.discussion.max_speech_chars,
            ),
            max_response_attempts=rules.max_response_attempts,
            max_speech_chars=config.discussion.max_speech_chars,
        )
        return agent, views.build(player.player_id, speeches=[]), player

    return build


class CountingBrain:
    """応答テキストを順に返し、呼び出し回数を数える。"""

    def __init__(self, texts):
        self.texts = list(texts)
        self.calls = 0

    def generate(self, request: Request) -> BrainResponse:
        self.calls += 1
        text = self.texts[min(self.calls - 1, len(self.texts) - 1)]
        data = extract_json(text)
        if data is None:
            return BrainResponse(text=text, data=None, parse_failed=True)
        missing = [k for k in request.expect_keys if not data.get(k)]
        if missing:
            return BrainResponse(text=text, data=None, parse_failed=True)
        return BrainResponse(text=text, data=data)


def test_valid_answer_uses_one_attempt(agent_for):
    brain = CountingBrain([json.dumps({"target": "P2", "reason": "確かめる。"})])
    agent, view, _player = agent_for(brain, player_index=0)

    result = agent.vote(view)

    assert result.ok is True
    assert result.attempts == 1
    assert brain.calls == 1


def test_format_failure_then_success_uses_two_attempts(agent_for):
    brain = CountingBrain(
        ["前置きだけの応答", json.dumps({"target": "P2", "reason": "確かめる。"})]
    )
    agent, view, _player = agent_for(brain)

    result = agent.vote(view)

    assert result.ok is True
    assert result.attempts == 2
    assert brain.calls == 2
    assert result.invalid_reasons == ["解析できない応答"]


def test_three_failures_stop_at_three_calls(agent_for):
    """4回目を呼ばない。呼ぶとルールの回答機会を超える。"""

    brain = CountingBrain(["だめな応答"])
    agent, view, _player = agent_for(brain)

    result = agent.vote(view)

    assert result.ok is False
    assert result.attempts == 3
    assert brain.calls == 3
    assert result.invalid_reasons == ["解析できない応答"] * 3


def test_semantic_failure_counts_as_an_attempt(agent_for):
    """候補外の指定も形式の失敗と同じく回答機会を消費する（設計書5.4）。"""

    brain = CountingBrain([json.dumps({"target": "P9", "reason": "存在しない。"})])
    agent, view, _player = agent_for(brain)

    result = agent.vote(view)

    assert result.ok is False
    assert brain.calls == 3
    assert result.invalid_reasons == ["候補外の指定: P9"] * 3


def test_json_in_a_code_fence_is_accepted(agent_for):
    """小型モデルがコードブロックを付けても形式の失敗としない（設計書5.4）。"""

    fenced = '```json\n{"target": "P2", "reason": "確かめる。"}\n```'
    brain = CountingBrain([fenced])
    agent, view, _player = agent_for(brain)

    result = agent.vote(view)

    assert result.ok is True
    assert result.attempts == 1


def test_json_with_a_preamble_is_accepted(agent_for):
    brain = CountingBrain(['考えました。{"target": "P2", "reason": "確かめる。"}'])
    agent, view, _player = agent_for(brain)

    result = agent.vote(view)

    assert result.ok is True
    assert result.attempts == 1


def test_swap_false_is_a_valid_answer(agent_for):
    """`swap: false` を空値と誤判定しないこと（設計書5.4）。"""

    brain = CountingBrain([json.dumps({"swap": False, "reason": "交換しない。"})])
    agent, view, _player = agent_for(brain)

    result = agent.night_thief_swap(view, "P2", "村人")

    assert result.ok is True
    assert result.attempts == 1
    assert result.data["swap"] is False


def test_speak_false_is_a_valid_answer(agent_for):
    brain = CountingBrain([json.dumps({"speak": False, "memo": "今は待つ。"})])
    agent, view, _player = agent_for(brain)

    result = agent.speak(view, 1)

    assert result.ok is True
    assert result.attempts == 1
    assert result.data["speak"] is False


def test_wait_seconds_accumulate_over_attempts(agent_for):
    class SlowBrain(CountingBrain):
        def generate(self, request):
            response = super().generate(request)
            response.wait_seconds = 0.5
            return response

    brain = SlowBrain(["だめな応答"])
    agent, view, _player = agent_for(brain)

    result = agent.vote(view)

    assert result.wait_seconds == pytest.approx(1.5)


def test_prompt_is_identical_on_every_attempt(agent_for):
    """同じ指示を送り直す。指示を変えると条件が途中で変わる（設計書5.4）。"""

    class RecordingBrain(CountingBrain):
        def __init__(self, texts):
            super().__init__(texts)
            self.users = []

        def generate(self, request):
            self.users.append(request.user)
            return super().generate(request)

    brain = RecordingBrain(["だめな応答"])
    agent, view, _player = agent_for(brain)

    agent.vote(view)

    assert len(set(brain.users)) == 1


# --- factory --------------------------------------------------------------


def test_stub_provider_returns_the_case_stub(v2_config):
    config = v2_config()

    brain = create_case_brain(config, seed=42)

    assert isinstance(brain, CaseStubBrain)


def test_real_brain_does_not_retry_format_internally(v2_config):
    """Brain内部の再送を0にする。Agentの3回と二重に掛からないようにする（設計書6.4）。"""

    config = v2_config(brain={"provider": "ollama", "model": "qwen2.5:3b"})

    brain = create_case_brain(config, seed=42)

    assert brain.max_format_retries == 0
    assert brain._format_retries == 0


def test_transport_retries_are_kept_separate(v2_config):
    """通信の再試行は残す。ルールの回答機会とは別物である（設計書6.4）。"""

    config = v2_config(
        brain={
            "provider": "ollama",
            "model": "qwen2.5:3b",
            "max_transport_retries": 5,
        }
    )

    brain = create_case_brain(config, seed=42)

    assert brain.brain_config.max_retries == 5


def test_judge_brain_is_built_from_the_judge_settings(v2_config):
    config = v2_config(
        brain={"provider": "ollama", "model": "qwen2.5:3b"},
        judge_brain={"provider": "ollama", "model": "qwen2.5:7b"},
    )

    agent_brain = create_case_brain(config, seed=42)
    judge_brain = create_case_brain(config, seed=42, judge=True)

    assert agent_brain.model == "qwen2.5:3b"
    assert judge_brain.model == "qwen2.5:7b"
    assert judge_brain.brain_config.temperature == 0.2


def test_case_stub_answers_every_phase(v2_config, build_trial):
    """スタブでフェーズを一巡できること。実機なしで回帰を回すために必要である。"""

    trial, config, rules = build_trial()
    brain = create_case_brain(config, seed=trial.trial_seed)
    players = trial.cases[0].players
    views = CaseViewBuilder(players, load_tendencies(config.persona_prompt_version))
    persona = PersonaBuilder(
        PromptSet(config.persona_prompt_version),
        max_speech_chars=config.discussion.max_speech_chars,
    )
    agent = CaseAgent(
        players[0],
        brain,
        persona,
        max_response_attempts=rules.max_response_attempts,
        max_speech_chars=config.discussion.max_speech_chars,
    )
    view = views.build(players[0].player_id, speeches=[])

    assert agent.night_seer(view).ok is True
    assert agent.night_thief_inspect(view).ok is True
    assert agent.night_thief_swap(view, "P2", "村人").ok is True
    assert agent.pre_discussion(view).ok is True
    assert agent.pre_vote(view).ok is True
    assert agent.speak(view, 1).ok is True
    assert agent.vote(view).ok is True
