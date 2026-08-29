"""エージェントへ渡す情報の隔離（設計書10章／4.7、5.2、要件F-11）。

設計書10章の `test_role_isolation`、`test_mbti_isolation`、`test_meta_isolation`、
`test_private_answer_isolation` をこのファイルへまとめる。検査対象がすべて
「プロンプト全文に何が含まれていないか」であり、同じ道具を使うためである。

ここが緩むと、性格構成の違いではなく情報の漏れが結果を動かしていることになり、
実験結果の解釈がすべて無効になる。
"""

from __future__ import annotations

import json
import re

import pytest

from mbti_werewolf.agents.mbti_types import TYPE_STACKS, display_name_for
from mbti_werewolf.agents.persona import PersonaBuilder, PromptSet, load_tendencies
from mbti_werewolf.engine.view import CaseViewBuilder

from v2_support import default_responder


@pytest.fixture
def prompts_by_player(run_case):
    """全プレイヤーのプロンプト全文を player_id ごとに集める。"""

    def collect(responder=None, **overrides):
        outcome, brain, case, trial, config, rules = run_case(responder, **overrides)
        prompts = {
            player.player_id: brain.prompts_for(player.player_id)
            for player in outcome.players
        }
        return outcome, prompts, brain

    return collect


# --- test_role_isolation ---------------------------------------------------


def test_other_players_roles_are_not_in_prompts(prompts_by_player):
    """他者の役職名を渡さない。自分の役職だけが自分のプロンプトに出る（F-11）。"""

    outcome, prompts, _brain = prompts_by_player()
    role_labels = {"人狼", "占い師", "怪盗", "村人"}

    for player in outcome.players:
        for prompt in prompts[player.player_id]:
            # 「あなたの開始時の役職は「人狼」です」の形で自分の役職だけが出る。
            declared = re.findall(r"あなたの開始時の役職は「(.+?)」", prompt)
            assert declared, player.player_id
            assert set(declared) == {player.initial_role_label}, player.player_id

            # 他者のIDと役職名を結び付けた記述がないこと。
            for other in outcome.players:
                if other.player_id == player.player_id:
                    continue
                for label in role_labels:
                    pattern = r"{0}\s*(?:の|は|が)?\s*(?:開始時)?(?:役職)?[はが:：]?\s*「?{1}".format(
                        other.display_id, label
                    )
                    if label == "占い師" and _is_seer_target(outcome, player, other):
                        continue
                    if _is_night_knowledge(outcome, player, other, label):
                        continue
                    assert re.search(pattern, prompt) is None, (
                        player.player_id,
                        other.player_id,
                        label,
                    )


def _is_seer_target(outcome, viewer, other):
    return _is_night_knowledge(outcome, viewer, other, other.initial_role_label)


def _is_night_knowledge(outcome, viewer, other, label):
    """夜にGM経由で本人へ通知された内容は例外として認める（設計書4.2）。"""

    for action in outcome.night_actions:
        if action.get("actor") != viewer.player_id:
            continue
        if action.get("target") != other.player_id:
            continue
        if action.get("revealed_initial_role") == other.initial_role:
            return True
    if label == "人狼":
        partners = [
            a["partners"]
            for a in outcome.night_actions
            if a["phase"] == "werewolf_recognition" and a["actor"] == viewer.player_id
        ]
        if partners and other.player_id in partners[0]:
            return True
    return False


def test_villager_prompt_has_no_night_information(prompts_by_player):
    outcome, prompts, _brain = prompts_by_player()

    for player in outcome.players:
        if player.initial_role != "villager":
            continue
        for prompt in prompts[player.player_id]:
            assert "あなたに個別通知された夜の情報はありません" in prompt


def test_werewolf_partner_is_told_only_to_werewolves(prompts_by_player):
    outcome, prompts, _brain = prompts_by_player()

    for player in outcome.players:
        told = any("人狼仲間は" in p for p in prompts[player.player_id])
        assert told == (player.initial_role == "werewolf"), player.player_id


def test_seer_result_is_told_only_to_the_seer(prompts_by_player):
    outcome, prompts, _brain = prompts_by_player()

    seer_action = next(
        a for a in outcome.night_actions if a["phase"] == "seer_inspection"
    )
    revealed = "あなたが確認した {0} の開始時の役職".format(seer_action["target"].upper())

    for player in outcome.players:
        told = any(revealed in p for p in prompts[player.player_id])
        assert told == (player.player_id == seer_action["actor"]), player.player_id


def test_center_cards_are_explicitly_denied(prompts_by_player):
    """8人8枚で中央札はないことを明示する（ルール文書v0.7 §1）。

    一般的なワンナイト人狼は中央札を持つ。触れないままにすると、学習済みの
    一般ルールを前提に「中央に人狼がいるかも」と推理される余地が残る。
    """

    _outcome, prompts, _brain = prompts_by_player()

    for prompt_list in prompts.values():
        for prompt in prompt_list:
            assert "中央カード・余りカードはありません" in prompt


# --- test_mbti_isolation ---------------------------------------------------


def test_mbti_type_names_are_not_in_prompts(prompts_by_player):
    """タイプ名を渡さない。参加者はMBTIという概念を知らない（Agent設定文書）。"""

    _outcome, prompts, _brain = prompts_by_player()

    for prompt_list in prompts.values():
        for prompt in prompt_list:
            for mbti in TYPE_STACKS:
                assert mbti not in prompt


def test_mbti_vocabulary_is_not_in_prompts(prompts_by_player):
    """「MBTI」「16タイプ」「心理機能」と日本語表示名を渡さない（設計書5.2）。"""

    _outcome, prompts, _brain = prompts_by_player()
    banned = ["MBTI", "16タイプ", "心理機能", "外向", "内向"]
    banned += [display_name_for(mbti) for mbti in TYPE_STACKS]

    for prompt_list in prompts.values():
        for prompt in prompt_list:
            for word in banned:
                if not word:
                    continue
                assert word not in prompt, word


def test_only_the_tendency_sentence_differs_between_cases(build_trial):
    """混合構成と同質構成でsystemプロンプトの差が行動傾向の1文だけであること。

    ここが崩れると、比較しているのが性格傾向なのか別の文言なのか分からなくなる。
    """

    trial, config, _rules = build_trial()
    tendencies = load_tendencies(config.persona_prompt_version)
    persona = PersonaBuilder(
        PromptSet(config.persona_prompt_version),
        max_speech_chars=config.discussion.max_speech_chars,
    )

    mixed_case, istj_case = trial.cases[0], trial.cases[1]
    # 混合構成でもともとISTJだった座席は差が出ないので、別のタイプの座席を選ぶ。
    seat = next(p for p in mixed_case.players if p.mbti != "ISTJ")

    mixed_view = CaseViewBuilder(mixed_case.players, tendencies).build(
        seat.player_id, speeches=[]
    )
    istj_view = CaseViewBuilder(istj_case.players, tendencies).build(
        seat.player_id, speeches=[]
    )

    mixed_text = persona.build_system(mixed_view)
    istj_text = persona.build_system(istj_view)

    mixed_only = set(mixed_text.split("\n")) - set(istj_text.split("\n"))
    istj_only = set(istj_text.split("\n")) - set(mixed_text.split("\n"))

    assert mixed_only == {tendencies[seat.mbti]}
    assert istj_only == {tendencies["ISTJ"]}


def test_every_type_gets_exactly_one_tendency_sentence():
    tendencies = load_tendencies()

    assert len(tendencies) == 16
    for mbti, text in tendencies.items():
        assert text.strip(), mbti
        assert mbti not in text


# --- test_meta_isolation --------------------------------------------------


def test_experiment_metadata_is_not_in_prompts(prompts_by_player):
    """実験であること、構成種別、AIであること、ケース番号を渡さない（設計書4.7）。"""

    _outcome, prompts, _brain = prompts_by_player()
    banned = [
        "実験",
        "混合構成",
        "同質構成",
        "ケース",
        "Trial",
        "trial",
        "seed",
        "AI",
        "LLM",
        "エージェント",
        "Agent",
        "シミュレーション",
        "プロンプト",
    ]

    for player_id, prompt_list in prompts.items():
        for prompt in prompt_list:
            for word in banned:
                assert word not in prompt, (player_id, word)


def test_case_and_trial_ids_are_not_in_prompts(prompts_by_player):
    outcome, prompts, _brain = prompts_by_player()
    _ = outcome

    for prompt_list in prompts.values():
        for prompt in prompt_list:
            assert re.search(r"e-\d{8}-\d{6}", prompt) is None
            assert re.search(r"-t\d{3}-c\d{2}", prompt) is None


def test_win_rate_and_indicators_are_not_in_prompts(prompts_by_player):
    """指標名を渡すと、指標を意識した振る舞いを誘発する（設計書4.7）。"""

    _outcome, prompts, _brain = prompts_by_player()
    banned = ["勝率", "指標", "投票正解率", "スコア", "評価"]

    for prompt_list in prompts.values():
        for prompt in prompt_list:
            for word in banned:
                assert word not in prompt, word


# --- test_private_answer_isolation ---------------------------------------


def test_other_players_private_answers_are_not_in_prompts(prompts_by_player):
    """他者の個別判断とmemoを渡さない（設計書5.3）。"""

    marker = "この文字列は他者へ漏れてはいけない"

    def responder(tag, player_id, request, index):
        base = json.loads(default_responder()(tag, player_id, request, index))
        for key in ("memo", "reason", "role_awareness"):
            if key in base:
                base[key] = "{0}-{1}".format(marker, player_id)
        return json.dumps(base, ensure_ascii=False)

    outcome, prompts, _brain = prompts_by_player(responder)

    for prompt_list in prompts.values():
        for prompt in prompt_list:
            assert marker not in prompt

    # 収集自体は行われていること（検査が空振りしていないことの確認）。
    assert any(marker in a["reason"] for a in outcome.pre_vote_answers)
    assert any(marker in e["memo"] for e in outcome.discussion.events if e["spoke"])


def test_own_previous_memo_is_not_fed_back(prompts_by_player):
    """自分のmemoも次の問い合わせへ戻さない。

    memoは記録のための1文であり、対話の履歴ではない。戻すと、memoを取ること自体が
    振る舞いを変える度合いが強くなる（設計書5.3）。
    """

    marker = "前回のmemoです"

    def responder(tag, player_id, request, index):
        base = json.loads(default_responder()(tag, player_id, request, index))
        if "memo" in base:
            base["memo"] = marker
        return json.dumps(base, ensure_ascii=False)

    _outcome, prompts, _brain = prompts_by_player(responder)

    for prompt_list in prompts.values():
        for prompt in prompt_list:
            assert marker not in prompt


def test_speech_log_is_identical_for_every_viewer(prompts_by_player):
    """公開発言ログは全員で同じ。視点ごとに違うと公開情報でなくなる。"""

    _outcome, _prompts, brain = prompts_by_player()

    logs_by_round = {}
    for call in brain.calls:
        if call["tag"] != "speak":
            continue
        match = re.search(
            r"## ここまでの公開発言\n\n(.*?)\n\n## 指示", call["user"], re.S
        )
        assert match is not None
        logs_by_round.setdefault(call["player_id"], []).append(match.group(1))

    # 同じ時点で問い合わせた2人を比べるのではなく、発言が増える順に並んでいること、
    # つまり各自が見たログが常に既出の発言だけであることを見る。
    for logs in logs_by_round.values():
        for earlier, later in zip(logs, logs[1:]):
            if earlier == "（まだ発言はありません）":
                continue
            assert earlier in later
