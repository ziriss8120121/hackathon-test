"""村人視点のプロンプトに他者の役職が出現しないことを確認する。

対応要件: F-11（役職による情報の非対称性）

他者の役職を判別できない実際の文字列を検査するために、検査対象のプレイヤー以外の
role を目印の文字列に置き換えてからプロンプトを組み立てる。プロンプトにその目印が
出れば、他者の役職が漏れていることになる。ルール説明に出てくる「人狼」「村人」と
いう語を誤検出しない方法として、この形を採っている。
"""

from __future__ import annotations

import random

from mbti_werewolf.agents.agent import Agent, PromptSet
from mbti_werewolf.brains.stub import StubBrain
from mbti_werewolf.config import PROMPT_VERSION
from mbti_werewolf.engine.roles import build_players
from mbti_werewolf.engine.view import PublicViewBuilder, Speech


def _prepare(config, viewer_role):
    players = build_players(config, random.Random(config.seed), PROMPT_VERSION)
    viewer = next(p for p in players if p.role == viewer_role)
    for player in players:
        if player.player_id != viewer.player_id:
            player.role = "ROLE_SENTINEL_{}".format(player.player_id)

    speeches = [
        Speech(turn=1, player_id=p.player_id, text="{} の発言です。".format(p.player_id))
        for p in players
    ]
    view = PublicViewBuilder(players).build(
        viewer_id=viewer.player_id,
        speeches=speeches,
        turn=2,
        turn_count=config.turn_count,
    )
    agent = Agent(
        player=viewer,
        config=config,
        brain=StubBrain(config),
        prompts=PromptSet(PROMPT_VERSION),
        rng=random.Random(0),
    )
    return players, viewer, view, agent


def test_villager_prompt_hides_other_roles(make_config):
    config = make_config()
    players, viewer, view, agent = _prepare(config, "villager")

    speak_system, speak_user = agent.build_speak_prompt(view)
    vote_system, vote_user = agent.build_vote_prompt(view)
    everything = "\n".join([speak_system, speak_user, vote_system, vote_user])

    for player in players:
        if player.player_id != viewer.player_id:
            assert player.role not in everything, "{} の役職がプロンプトに漏れている".format(
                player.player_id
            )


def test_villager_view_has_no_teammates(make_config):
    config = make_config()
    _players, _viewer, view, _agent = _prepare(config, "villager")
    assert view.teammates == []


def test_public_view_contains_only_ids_and_speeches(make_config):
    """公開ビューが役職を持ち運ばないこと（設計書5.3の構造側の担保）。"""
    config = make_config()
    _players, viewer, view, _agent = _prepare(config, "villager")

    payload = view.to_dict()
    assert payload["viewer_id"] == viewer.player_id
    assert payload["viewer_role"] == "villager"
    assert set(payload["alive_ids"]) == {"p1", "p2", "p3", "p4"}
    for speech in payload["speeches"]:
        assert set(speech) == {"turn", "player_id", "text"}


def test_werewolf_knows_own_role(make_config):
    """人狼は自分が人狼であることを知る（F-11の反対側）。"""
    config = make_config()
    _players, _viewer, view, agent = _prepare(config, "werewolf")

    system, _user = agent.build_speak_prompt(view)
    assert "あなたは人狼です" in system


def test_multiple_werewolves_see_teammates(make_config):
    """8人版で人狼が複数になった場合に仲間が見えること（設計書5.3）。"""
    config = make_config(
        player_count=8,
        functions=["Ne", "Ti", "Fe", "Si", "Ni", "Se", "Te", "Fi"],
        role_composition={"werewolf": 2, "villager": 6},
    )
    players = build_players(config, random.Random(config.seed), PROMPT_VERSION)
    wolves = [p for p in players if p.role == "werewolf"]
    assert len(wolves) == 2

    view = PublicViewBuilder(players).build(
        viewer_id=wolves[0].player_id, speeches=[], turn=1, turn_count=config.turn_count
    )
    assert view.teammates == [wolves[1].player_id]

    villager = next(p for p in players if p.role == "villager")
    villager_view = PublicViewBuilder(players).build(
        viewer_id=villager.player_id, speeches=[], turn=1, turn_count=config.turn_count
    )
    assert villager_view.teammates == []
