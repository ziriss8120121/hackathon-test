"""Judgeによる発言単位の事後評価（設計書3.4、5.5、6.8 / 要件F-40〜F-46、AC-06）。

推論は呼ばず、応答を組み立てる FakeJudgeBrain で検証する。
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Sequence

import pytest

from mbti_werewolf.brains.base import BrainResponse, Request
from mbti_werewolf.judge.judge import (
    CaseJudge,
    Criteria,
    ExperimentJudge,
    JudgeError,
    judge_file_name,
)

PLAYERS = [
    {
        "player_id": "p{0}".format(i),
        "person_id": "person-{0:03d}".format(i),
        "mbti": "ENTP",
        "age": 20 + i,
        "gender": "male" if i % 2 else "female",
        "initial_role": "werewolf" if i <= 2 else "villager",
        "final_role": "werewolf" if i <= 2 else "villager",
    }
    for i in range(1, 9)
]


class FakeJudgeBrain:
    """`subjects` を見て応答を作る脳。responder で応答の中身を差し替えられる。"""

    provider = "fake"
    name = "fake"
    endpoint_kind = "stub"

    def __init__(self, responder=None) -> None:
        self.responder = responder or default_judge_responder()
        self.requests: List[Request] = []

    def describe(self) -> Dict[str, str]:
        return {
            "provider": self.provider,
            "model": "fake",
            "endpoint_kind": self.endpoint_kind,
            "name": self.name,
        }

    def generate(self, request: Request) -> BrainResponse:
        self.requests.append(request)
        payload = self.responder(request, len(self.requests) - 1)
        if payload is None:
            return BrainResponse(text="…", data=None, parse_failed=True)
        return BrainResponse(
            text=json.dumps(payload, ensure_ascii=False), data=payload
        )

    @property
    def prompts(self) -> List[str]:
        return [r.system + "\n" + r.user for r in self.requests]


def default_judge_responder(
    labels: Sequence[str] = ("suspect",),
    target: str = "P4",
    direction: str = "suspect",
    strength: int = 2,
):
    def responder(request: Request, index: int) -> Dict[str, Any]:
        return {
            "evaluations": [
                {
                    "speech_id": speech_id,
                    "labels": list(labels),
                    "mentions": [target],
                    "stances": [
                        {"target": target, "direction": direction, "strength": strength}
                    ],
                }
                for speech_id in request.subjects
            ]
        }

    return responder


def build_case_log(
    speeches: Optional[Sequence[Dict[str, Any]]] = None,
    case_id: str = "e-20260101-000000-t001-c00",
) -> Dict[str, Any]:
    """評価に必要な部分だけを持つ `case_log.json`（設計書6.7）。"""

    speeches = speeches if speeches is not None else [(1, "p1"), (2, "p2"), (3, "p3")]
    events = []
    for order, item in enumerate(speeches, start=1):
        index, player_id = item
        events.append(
            {
                "order": order,
                "round": 1,
                "player_id": player_id,
                "spoke": True,
                "skipped": False,
                "speech_id": "{0}-s{1:03d}".format(case_id, index),
                "speech_text": "{0}の発言です。".format(player_id.upper()),
                "memo": "非公開のメモ。",
                "chars": 10,
            }
        )
    return {
        "schema_version": "2",
        "case_id": case_id,
        "trial_id": "e-20260101-000000-t001",
        "experiment_id": "e-20260101-000000",
        "status": "done",
        "players": [dict(p) for p in PLAYERS],
        "discussion": {"rounds": 1, "stop_reason": "max_rounds", "events": events},
        "votes": [{"voter": "p1", "target": "p4"}],
        "result": {"winner": "village", "valid": True, "executed": ["p4"]},
    }


@pytest.fixture
def judge():
    def build(brain=None, **kwargs: Any):
        return CaseJudge(brain or FakeJudgeBrain(), **kwargs)

    return build


# --- 評価基準 -----------------------------------------------------------------


def test_the_criteria_files_define_the_nine_labels_from_the_design():
    criteria = Criteria("v1")
    assert set(criteria.labels) == {
        "suspect",
        "defend",
        "claim",
        "question",
        "rebut",
        "agree",
        "hypothesis",
        "intent",
        "other",
    }


def test_the_stance_vocabulary_is_two_directions_and_three_strengths():
    criteria = Criteria("v1")
    assert criteria.directions == ("suspect", "defend")
    assert criteria.strengths == (1, 2, 3)


def test_the_system_prompt_carries_the_label_definitions_from_the_json():
    prompt = Criteria("v1").system_prompt()
    for label in Criteria("v1").labels:
        assert label in prompt
    assert "$label_definitions" not in prompt


def test_an_unknown_criteria_version_is_reported_instead_of_falling_back():
    with pytest.raises(JudgeError):
        Criteria("v99")


# --- 発言との対応 -------------------------------------------------------------


def test_every_speech_gets_exactly_one_evaluation(judge):
    log = build_case_log()
    result = judge().evaluate(log)

    assert [s["speech_id"] for s in result["speeches"]] == [
        e["speech_id"] for e in log["discussion"]["events"]
    ]


def test_passes_and_skips_are_not_evaluated_because_they_have_no_speech_id(judge):
    log = build_case_log()
    log["discussion"]["events"].append(
        {"order": 9, "round": 2, "player_id": "p5", "spoke": False, "skipped": False}
    )
    log["discussion"]["events"].append(
        {"order": 10, "round": 2, "player_id": "p6", "spoke": False, "skipped": True}
    )

    result = judge().evaluate(log)

    assert len(result["speeches"]) == 3


def test_an_evaluation_for_a_speech_id_that_does_not_exist_is_dropped(judge):
    """モデルがIDを作り出しても、存在しない発言の評価は混ざらない（AC-06）。"""

    def responder(request: Request, index: int) -> Dict[str, Any]:
        return {
            "evaluations": [
                {"speech_id": "でっちあげたID", "labels": ["claim"]},
                {"speech_id": request.subjects[0], "labels": ["agree"]},
            ]
        }

    result = judge(FakeJudgeBrain(responder)).evaluate(build_case_log())

    ids = [s["speech_id"] for s in result["speeches"]]
    assert "でっちあげたID" not in ids
    assert result["speeches"][0]["labels"] == ["agree"]


def test_a_speech_the_model_never_answered_is_marked_as_not_evaluated(judge):
    def responder(request: Request, index: int) -> Dict[str, Any]:
        return {
            "evaluations": [
                {"speech_id": request.subjects[0], "labels": ["claim"]},
            ]
        }

    result = judge(FakeJudgeBrain(responder)).evaluate(build_case_log())

    assert result["speeches"][0]["parse_failed"] is False
    assert [s["parse_failed"] for s in result["speeches"][1:]] == [True, True]
    assert result["speeches"][1]["labels"] == []


def test_missing_speeches_are_asked_again_and_what_arrives_late_is_kept(judge):
    """1回目で欠けた分だけを送り直す。取れた分は保持する（設計書5.5）。"""

    def responder(request: Request, index: int) -> Dict[str, Any]:
        wanted = request.subjects[:1] if index == 0 else request.subjects
        return {
            "evaluations": [
                {"speech_id": speech_id, "labels": ["claim"]} for speech_id in wanted
            ]
        }

    brain = FakeJudgeBrain(responder)
    result = judge(brain).evaluate(build_case_log())

    assert len(brain.requests) == 2
    assert all(s["parse_failed"] is False for s in result["speeches"])


def test_asking_again_stops_at_the_attempt_limit(judge):
    brain = FakeJudgeBrain(lambda request, index: None)
    result = judge(brain, batch_attempts=2).evaluate(build_case_log())

    assert len(brain.requests) == 2
    assert all(s["parse_failed"] is True for s in result["speeches"])
    assert result["timing"]["inference_calls"] == 2


def test_the_speeches_are_split_into_batches_of_the_configured_size(judge):
    log = build_case_log([(i, "p{0}".format((i % 8) + 1)) for i in range(1, 21)])
    brain = FakeJudgeBrain()

    judge(brain, batch_size=8).evaluate(log)

    assert [len(r.subjects) for r in brain.requests] == [8, 8, 4]


# --- 応答の正規化 -------------------------------------------------------------


def test_labels_outside_the_nine_are_dropped(judge):
    def responder(request: Request, index: int) -> Dict[str, Any]:
        return {
            "evaluations": [
                {"speech_id": s, "labels": ["suspect", "joke", "AGREE"]}
                for s in request.subjects
            ]
        }

    result = judge(FakeJudgeBrain(responder)).evaluate(build_case_log())

    assert result["speeches"][0]["labels"] == ["suspect", "agree"]


def test_a_speech_with_no_usable_label_falls_back_to_other(judge):
    def responder(request: Request, index: int) -> Dict[str, Any]:
        return {"evaluations": [{"speech_id": s, "labels": []} for s in request.subjects]}

    result = judge(FakeJudgeBrain(responder)).evaluate(build_case_log())

    assert result["speeches"][0]["labels"] == ["other"]


def test_player_ids_are_stored_in_the_internal_lowercase_form(judge):
    result = judge().evaluate(build_case_log())

    assert result["speeches"][0]["mentions"] == ["p4"]
    assert result["speeches"][0]["stances"][0]["target"] == "p4"


def test_a_mention_of_someone_who_is_not_playing_is_dropped(judge):
    def responder(request: Request, index: int) -> Dict[str, Any]:
        return {
            "evaluations": [
                {"speech_id": s, "labels": ["claim"], "mentions": ["P4", "P99", "全員"]}
                for s in request.subjects
            ]
        }

    result = judge(FakeJudgeBrain(responder)).evaluate(build_case_log())

    assert result["speeches"][0]["mentions"] == ["p4"]


@pytest.mark.parametrize(
    "stance",
    [
        {"target": None, "direction": "suspect", "strength": 2},
        {"target": "P99", "direction": "suspect", "strength": 2},
        {"target": "P4", "direction": "怪しい", "strength": 2},
        {"target": "P4", "direction": "suspect", "strength": 5},
        {"target": "P4", "direction": "suspect", "strength": "強い"},
    ],
)
def test_a_stance_that_cannot_be_counted_is_dropped(judge, stance):
    def responder(request: Request, index: int) -> Dict[str, Any]:
        return {
            "evaluations": [
                {"speech_id": s, "labels": ["suspect"], "stances": [stance]}
                for s in request.subjects
            ]
        }

    result = judge(FakeJudgeBrain(responder)).evaluate(build_case_log())

    assert result["speeches"][0]["stances"] == []


def test_a_stance_pointed_at_the_speaker_is_dropped(judge):
    """自分自身への疑いは各人1件の正規化に使えない（設計書5.5）。"""

    def responder(request: Request, index: int) -> Dict[str, Any]:
        return {
            "evaluations": [
                {
                    "speech_id": s,
                    "labels": ["suspect"],
                    "stances": [{"target": "P1", "direction": "suspect", "strength": 2}],
                }
                for s in request.subjects
            ]
        }

    result = judge(FakeJudgeBrain(responder)).evaluate(build_case_log())

    # s001 は p1 の発言、s002 は p2 の発言。
    assert result["speeches"][0]["stances"] == []
    assert result["speeches"][1]["stances"][0]["target"] == "p1"


# --- Judgeへ渡さない情報 -------------------------------------------------------


def test_the_judge_never_sees_roles_mbti_votes_or_the_winner(judge):
    """3.4、F-46。正解を知った評価にしない。"""

    brain = FakeJudgeBrain()
    judge(brain).evaluate(build_case_log())

    for prompt in brain.prompts:
        for forbidden in ("ENTP", "werewolf", "villager", "village", "person-001"):
            assert forbidden not in prompt


def test_the_judge_never_sees_the_private_memos(judge):
    brain = FakeJudgeBrain()
    judge(brain).evaluate(build_case_log())

    assert all("非公開のメモ。" not in prompt for prompt in brain.prompts)


def test_the_judge_sees_the_participants_ages_and_genders(judge):
    brain = FakeJudgeBrain()
    judge(brain).evaluate(build_case_log())

    prompt = brain.prompts[0]
    assert "P1: 21歳 / 男性" in prompt
    assert "P2: 22歳 / 女性" in prompt


def test_a_batch_sees_the_conversation_up_to_its_last_speech_but_no_further(judge):
    """あとの発言を見せない。評価が後知恵にならないようにする（設計書5.5）。"""

    log = build_case_log([(i, "p{0}".format((i % 8) + 1)) for i in range(1, 13)])
    brain = FakeJudgeBrain()

    judge(brain, batch_size=8).evaluate(log)

    first, second = brain.requests[0].user, brain.requests[1].user
    ninth = log["discussion"]["events"][8]["speech_id"]
    twelfth = log["discussion"]["events"][11]["speech_id"]
    assert ninth not in first and twelfth not in first
    assert ninth in second and twelfth in second


# --- 出力の形 -----------------------------------------------------------------


def test_the_output_carries_the_criteria_version_and_the_brain_used(judge):
    result = judge().evaluate(build_case_log())

    assert result["schema_version"] == "2"
    assert result["judge_criteria_version"] == "v1"
    assert result["judge_brain"]["provider"] == "fake"
    assert result["timing"]["inference_calls"] == 1


def test_the_stance_series_has_one_entry_per_speech(judge):
    result = judge().evaluate(build_case_log())

    assert [e["at_speech_id"] for e in result["stance_series"]] == [
        s["speech_id"] for s in result["speeches"]
    ]
    # p1・p2・p3 の3人が P4 を疑った状態。各人1件なので合計は3になる。
    assert result["stance_series"][-1]["suspicion_distribution"] == {"p4": 3}


def test_a_case_without_players_is_refused_instead_of_producing_an_empty_file(judge):
    log = build_case_log()
    log["players"] = []

    with pytest.raises(JudgeError):
        judge().evaluate(log)


# --- 実験の走査 ---------------------------------------------------------------


def write_case(root, trial: str, case: str, log: Dict[str, Any]):
    trial_dir = root / trial
    trial_dir.mkdir(parents=True, exist_ok=True)
    (trial_dir / "trial.json").write_text("{}", encoding="utf-8")
    case_dir = trial_dir / case
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "case_log.json").write_text(
        json.dumps(log, ensure_ascii=False), encoding="utf-8"
    )
    return case_dir


@pytest.fixture
def experiment_dir(tmp_path):
    exp_dir = tmp_path / "e-20260101-000000"
    write_case(exp_dir, "t001", "c00-mixed", build_case_log())
    write_case(
        exp_dir,
        "t001",
        "c01-ENTP",
        build_case_log(case_id="e-20260101-000000-t001-c01"),
    )
    return tmp_path, "e-20260101-000000"


def test_the_judge_writes_one_file_per_case_named_after_the_criteria_version(
    experiment_dir,
):
    runs_dir, experiment_id = experiment_dir
    summary = ExperimentJudge(runs_dir, FakeJudgeBrain).run(experiment_id)

    assert summary["done_count"] == 2
    written = sorted(p.name for p in (runs_dir / experiment_id).glob("t001/*/judge.*.json"))
    assert written == ["judge.v1.json", "judge.v1.json"]


def test_a_case_that_already_has_this_version_is_not_evaluated_again(experiment_dir):
    runs_dir, experiment_id = experiment_dir
    judge = ExperimentJudge(runs_dir, FakeJudgeBrain)
    judge.run(experiment_id)

    summary = judge.run(experiment_id)

    assert summary["done_count"] == 0
    assert summary["skipped_count"] == 2


def test_force_evaluates_the_cases_again(experiment_dir):
    runs_dir, experiment_id = experiment_dir
    judge = ExperimentJudge(runs_dir, FakeJudgeBrain)
    judge.run(experiment_id)

    summary = judge.run(experiment_id, force=True)

    assert summary["done_count"] == 2


def test_a_case_that_did_not_finish_is_left_alone(experiment_dir):
    runs_dir, experiment_id = experiment_dir
    failed = build_case_log(case_id="e-20260101-000000-t001-c02")
    failed["status"] = "failed"
    case_dir = write_case(runs_dir / experiment_id, "t001", "c02-INFP", failed)

    summary = ExperimentJudge(runs_dir, FakeJudgeBrain).run(experiment_id)

    assert summary["done_count"] == 2
    assert not (case_dir / judge_file_name("v1")).exists()


def test_one_broken_case_does_not_stop_the_others(experiment_dir):
    runs_dir, experiment_id = experiment_dir
    broken = runs_dir / experiment_id / "t001" / "c03-ISFJ"
    broken.mkdir(parents=True)
    (broken / "case_log.json").write_text("{ 壊れている", encoding="utf-8")

    summary = ExperimentJudge(runs_dir, FakeJudgeBrain).run(experiment_id)

    assert summary["done_count"] == 2
    assert summary["failed_count"] == 1
    assert summary["failures"][0]["case"] == "c03-ISFJ"


def test_an_experiment_that_does_not_exist_is_reported(tmp_path):
    with pytest.raises(JudgeError):
        ExperimentJudge(tmp_path, FakeJudgeBrain).run("e-99999999-999999")


def test_each_case_gets_a_fresh_brain_so_the_order_of_cases_does_not_leak(
    experiment_dir,
):
    runs_dir, experiment_id = experiment_dir
    created = []

    def factory():
        brain = FakeJudgeBrain()
        created.append(brain)
        return brain

    ExperimentJudge(runs_dir, factory).run(experiment_id)

    assert len(created) == 2
