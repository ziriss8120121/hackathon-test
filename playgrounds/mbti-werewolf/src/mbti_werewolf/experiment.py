"""人物選定、役職割当、Trialと17ケースの生成、条件固定の検査（設計書3.1、6.6）。

17ケースはMBTI構成だけが違い、他はすべて同じでなければならない。ここが崩れると
比較の前提が失われ、実行にかけた時間が無駄になる。そのため生成の直後に検査し、
MBTI以外に差があれば実行前に停止する（NF-06、AC-02）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .agents.mbti_types import TYPE_STACKS
from .engine import roles as roles_module
from .engine.rules import RuleSet
from .config import ExperimentConfig
from .masterdata import PatternSet, PersonPool

SCHEMA_VERSION = "2"

COMPOSITION_MIXED = "mixed"
COMPOSITION_HOMOGENEOUS = "homogeneous"

#: 同質構成のケースはMBTI16タイプで16件。混合構成の1件と合わせて17ケースになる。
#: 順序は `TYPE_STACKS` の定義順に固定する（設計書6.2）。ここへ書き写すと定義が
#: 二重になり、片方を直したときにケース番号とタイプの対応がずれる。
HOMOGENEOUS_TYPES: Tuple[str, ...] = tuple(TYPE_STACKS)

CASES_PER_TRIAL = 1 + len(HOMOGENEOUS_TYPES)

STATUS_PENDING = "pending"


class ConditionFixationError(Exception):
    """Trial内の17ケースでMBTI以外の条件が変わっている。"""


class ExperimentError(Exception):
    """実験の生成に必要な条件が揃っていない。"""


@dataclass
class CasePlan:
    """1ケースの生成計画。実行はまだしていない。"""

    case_id: str
    trial_id: str
    experiment_id: str
    case_index: int
    composition: str
    homogeneous_type: Optional[str]
    players: List[roles_module.CasePlayer]
    status: str = STATUS_PENDING

    @property
    def dir_name(self) -> str:
        """`c00-mixed` や `c01-ISTJ` の形。ディレクトリ名だけで構成が読める（設計書6.1）。"""

        if self.composition == COMPOSITION_MIXED:
            return "c{0:02d}-mixed".format(self.case_index)
        return "c{0:02d}-{1}".format(self.case_index, self.homogeneous_type)

    def summary_dict(self) -> Dict[str, Any]:
        return {
            "case_id": self.case_id,
            "composition": self.composition,
            "homogeneous_type": self.homogeneous_type,
            "status": self.status,
        }


@dataclass
class TrialPlan:
    trial_id: str
    experiment_id: str
    trial_index: int
    trial_seed: int
    pattern_id: str
    persons: List[Dict[str, Any]]
    initial_roles: Tuple[str, ...]
    cases: List[CasePlan]
    rule_set: RuleSet
    config: ExperimentConfig
    condition_check: Dict[str, Any] = field(default_factory=dict)

    @property
    def dir_name(self) -> str:
        return "t{0:03d}".format(self.trial_index)

    def seats(self) -> List[Dict[str, Any]]:
        return [
            {
                "player_id": "p{0}".format(index + 1),
                "person_id": str(person["person_id"]),
                "age": int(person["age"]),
                "gender": str(person["gender"]),
                "pool_mbti": str(person["mbti"]),
                "initial_role": self.initial_roles[index],
            }
            for index, person in enumerate(self.persons)
        ]

    def to_dict(self) -> Dict[str, Any]:
        cfg = self.config
        return {
            "schema_version": SCHEMA_VERSION,
            "trial_id": self.trial_id,
            "experiment_id": self.experiment_id,
            "trial_index": self.trial_index,
            "trial_seed": self.trial_seed,
            "pool_id": cfg.pool_id,
            "pattern_set_id": cfg.pattern_set_id,
            "pattern_id": self.pattern_id,
            "rule_set_id": self.rule_set.rule_set_id,
            "rule_set_version": self.rule_set.rule_set_version,
            "fixed_conditions": {
                "seats": self.seats(),
                "role_assignment_mode": "seeded_random",
                "discussion": cfg.discussion.to_dict(),
                "persona_prompt_version": cfg.persona_prompt_version,
                "judge_criteria_version": cfg.judge_criteria_version,
                "brain": {
                    "provider": cfg.brain.provider,
                    "model": cfg.brain.model,
                },
                "judge_brain": {
                    "provider": cfg.judge_brain.provider,
                    "model": cfg.judge_brain.model,
                },
            },
            "cases": [case.summary_dict() for case in self.cases],
            "complete": all(case.status == "done" for case in self.cases),
            "condition_check": self.condition_check,
        }


@dataclass
class ExperimentPlan:
    experiment_id: str
    config: ExperimentConfig
    rule_set: RuleSet
    trials: List[TrialPlan]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "experiment_id": self.experiment_id,
            "config": self.config.to_dict(),
            "rule_set_id": self.rule_set.rule_set_id,
            "rule_set_version": self.rule_set.rule_set_version,
            "trial_ids": [trial.trial_id for trial in self.trials],
            "case_count": sum(len(trial.cases) for trial in self.trials),
        }


def make_experiment_id(now: Optional[datetime] = None) -> str:
    stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
    return "e-{0}".format(stamp)


def make_trial_id(experiment_id: str, trial_index: int) -> str:
    return "{0}-t{1:03d}".format(experiment_id, trial_index)


def make_case_id(trial_id: str, case_index: int) -> str:
    return "{0}-c{1:02d}".format(trial_id, case_index)


def _persons_for_pattern(pool: PersonPool, person_ids: Sequence[str]) -> List[Dict[str, Any]]:
    return [pool.get(person_id).to_dict() for person_id in person_ids]


def check_condition_fixation(cases: Sequence[CasePlan]) -> Dict[str, Any]:
    """17ケースでMBTIだけが変わっていることを確かめる（設計書6.6）。

    座席ごとに、MBTI以外の項目（人物、年齢、性別、開始時役職）がケース間で
    一致するかを見る。差があった項目名を集め、`{"mbti"}` と一致しなければ失敗にする。
    MBTIに差がないのも失敗である。同質構成16件が混合構成と同じMBTIになっている
    ことは起こりえないため、差がないなら生成が壊れている。
    """

    if len(cases) < 2:
        raise ConditionFixationError(
            "検査には2件以上のケースが必要: {0}件".format(len(cases))
        )

    seat_counts = {len(case.players) for case in cases}
    if len(seat_counts) != 1:
        raise ConditionFixationError("ケース間で人数が違う: {0}".format(sorted(seat_counts)))

    tracked = ("person_id", "age", "gender", "initial_role", "mbti")
    varying: set = set()
    baseline = cases[0]
    for case in cases[1:]:
        for seat_index, (base_player, player) in enumerate(zip(baseline.players, case.players)):
            if base_player.player_id != player.player_id:
                raise ConditionFixationError(
                    "座席{0}のplayer_idが違う: {1} / {2}".format(
                        seat_index, base_player.player_id, player.player_id
                    )
                )
            for key in tracked:
                if getattr(base_player, key) != getattr(player, key):
                    varying.add(key)

    varying_keys = sorted(varying)
    if varying_keys != ["mbti"]:
        raise ConditionFixationError(
            "MBTI以外の条件が変わっている、またはMBTIが変わっていない: 変動={0}".format(
                varying_keys or "なし"
            )
        )

    return {
        "passed": True,
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "varying_keys": varying_keys,
    }


def build_trial(
    experiment_id: str,
    trial_index: int,
    config: ExperimentConfig,
    rule_set: RuleSet,
    pool: PersonPool,
    pattern_set: PatternSet,
) -> TrialPlan:
    """1 Trialと、そこに属する17ケースを生成する。"""

    if trial_index > len(pattern_set.patterns):
        raise ExperimentError(
            "Trial {0} に対応するパターンがない: パターン{1}件".format(
                trial_index, len(pattern_set.patterns)
            )
        )

    pattern = pattern_set.patterns[trial_index - 1]
    persons = _persons_for_pattern(pool, pattern.person_ids)
    if len(persons) != rule_set.player_count:
        raise ExperimentError(
            "パターンの人数がルールの参加人数と一致しない: {0}人 / {1}人".format(
                len(persons), rule_set.player_count
            )
        )

    trial_seed = config.trial_seed(trial_index)
    initial_roles = roles_module.assign_initial_roles(rule_set.role_deck(), trial_seed)
    trial_id = make_trial_id(experiment_id, trial_index)

    cases: List[CasePlan] = [
        CasePlan(
            case_id=make_case_id(trial_id, 0),
            trial_id=trial_id,
            experiment_id=experiment_id,
            case_index=0,
            composition=COMPOSITION_MIXED,
            homogeneous_type=None,
            players=roles_module.build_case_players(persons, initial_roles),
        )
    ]
    for offset, mbti in enumerate(HOMOGENEOUS_TYPES, start=1):
        cases.append(
            CasePlan(
                case_id=make_case_id(trial_id, offset),
                trial_id=trial_id,
                experiment_id=experiment_id,
                case_index=offset,
                composition=COMPOSITION_HOMOGENEOUS,
                homogeneous_type=mbti,
                players=roles_module.build_case_players(
                    persons, initial_roles, homogeneous_type=mbti
                ),
            )
        )

    trial = TrialPlan(
        trial_id=trial_id,
        experiment_id=experiment_id,
        trial_index=trial_index,
        trial_seed=trial_seed,
        pattern_id=pattern.pattern_id,
        persons=persons,
        initial_roles=initial_roles,
        cases=cases,
        rule_set=rule_set,
        config=config,
    )
    trial.condition_check = check_condition_fixation(cases)
    return trial


def restore_trial(
    raw: Dict[str, Any], config: ExperimentConfig, rule_set: RuleSet
) -> TrialPlan:
    """`trial.json` からTrialを復元する（設計書3.5、6.6）。

    再開のたびにパターン選定と役職割当をやり直さない。やり直すと、同じTrialの中で
    座席と役職が変わり、17ケースの対応あり比較が崩れる（F-53、AC-12）。座席と役職は
    生成時に1度だけ決めてファイルへ書き、以後は読むだけにする。

    ケースの参加者はここで作り直すが、材料は `fixed_conditions.seats` なので結果は
    生成時と同じになる。プールとパターンセットを読み直す必要もない。
    """

    fixed = raw["fixed_conditions"]
    seats = fixed["seats"]
    if len(seats) != rule_set.player_count:
        raise ExperimentError(
            "trial.json の座席数がルールの参加人数と一致しない: {0}人 / {1}人".format(
                len(seats), rule_set.player_count
            )
        )

    persons = [
        {
            "person_id": str(seat["person_id"]),
            "mbti": str(seat["pool_mbti"]),
            "age": int(seat["age"]),
            "gender": str(seat["gender"]),
        }
        for seat in seats
    ]
    initial_roles = tuple(str(seat["initial_role"]) for seat in seats)
    # 役職の枚数がルールの構成と合っているかを見る。17ケースを見比べる
    # `check_condition_fixation` は、全ケースへ同じ座席を配るこの経路では
    # 役職の誤りを検出できない（どのケースも同じように誤るため）。
    if sorted(initial_roles) != sorted(rule_set.role_deck()):
        raise ExperimentError(
            "trial.json の役職構成がルールセットと一致しない: 記録 {0} / ルール {1}".format(
                sorted(initial_roles), sorted(rule_set.role_deck())
            )
        )

    trial_id = str(raw["trial_id"])
    saved_status = {
        str(entry["case_id"]): str(entry.get("status", STATUS_PENDING))
        for entry in raw.get("cases", [])
    }

    cases: List[CasePlan] = []
    for case_index in range(CASES_PER_TRIAL):
        mbti = None if case_index == 0 else HOMOGENEOUS_TYPES[case_index - 1]
        case_id = make_case_id(trial_id, case_index)
        cases.append(
            CasePlan(
                case_id=case_id,
                trial_id=trial_id,
                experiment_id=str(raw["experiment_id"]),
                case_index=case_index,
                composition=COMPOSITION_MIXED if mbti is None else COMPOSITION_HOMOGENEOUS,
                homogeneous_type=mbti,
                players=roles_module.build_case_players(
                    persons, initial_roles, homogeneous_type=mbti
                ),
                status=saved_status.get(case_id, STATUS_PENDING),
            )
        )

    trial = TrialPlan(
        trial_id=trial_id,
        experiment_id=str(raw["experiment_id"]),
        trial_index=int(raw["trial_index"]),
        trial_seed=int(raw["trial_seed"]),
        pattern_id=str(raw["pattern_id"]),
        persons=persons,
        initial_roles=initial_roles,
        cases=cases,
        rule_set=rule_set,
        config=config,
    )
    # 復元後も検査する。手でtrial.jsonを編集した場合にここで止まる。
    trial.condition_check = check_condition_fixation(cases)
    return trial


def build_experiment(
    config: ExperimentConfig,
    rule_set: RuleSet,
    pool: PersonPool,
    pattern_set: PatternSet,
    experiment_id: Optional[str] = None,
    now: Optional[datetime] = None,
) -> ExperimentPlan:
    if pool.pool_id != config.pool_id:
        raise ExperimentError(
            "プールのIDが設定と一致しない: {0} / {1}".format(pool.pool_id, config.pool_id)
        )
    if pattern_set.pattern_set_id != config.pattern_set_id:
        raise ExperimentError(
            "パターンセットのIDが設定と一致しない: {0} / {1}".format(
                pattern_set.pattern_set_id, config.pattern_set_id
            )
        )
    if rule_set.rule_set_id != config.rule_set_id:
        raise ExperimentError(
            "ルールセットのIDが設定と一致しない: {0} / {1}".format(
                rule_set.rule_set_id, config.rule_set_id
            )
        )

    exp_id = experiment_id or make_experiment_id(now)
    trials = [
        build_trial(exp_id, index, config, rule_set, pool, pattern_set)
        for index in config.trial_indices()
    ]
    return ExperimentPlan(
        experiment_id=exp_id, config=config, rule_set=rule_set, trials=trials
    )


def default_data_dir() -> Path:
    """`data/` の場所。パッケージから2つ上がプロジェクト直下になる。"""

    return Path(__file__).resolve().parents[2] / "data"
