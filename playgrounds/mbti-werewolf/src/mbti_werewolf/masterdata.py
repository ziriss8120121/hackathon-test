"""マスタデータの生成と読み込み（設計書6.3）。

人物プールと8人パターンは実行結果ではなく実験条件の一部なので、`data/` 配下の
JSONとして保存し、リポジトリへcommitする。生成はseedで決めるため、同じseedなら
同じプールとパターンが復元できる（F-57）。
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

JST = timezone(timedelta(hours=9))

POOL_COUNT = 100
PLAYERS_PER_PATTERN = 8

# 要求定義書8.2（v2.2-draft）が定めた配分。合計100人。
MBTI_COMPOSITION: Dict[str, int] = {
    "ISTJ": 8,
    "ISFJ": 8,
    "INFJ": 2,
    "INTJ": 2,
    "ISTP": 4,
    "ISFP": 5,
    "INFP": 5,
    "INTP": 4,
    "ESTP": 6,
    "ESFP": 7,
    "ENFP": 10,
    "ENTP": 8,
    "ESTJ": 12,
    "ESFJ": 12,
    "ENFJ": 4,
    "ENTJ": 3,
}

# 年代の幅は一定ではない（15-19と60-64が5歳幅、他が10歳幅）。
# コード側で年代を計算せず、この表のキーをそのまま使う（設計書6.3）。
AGE_GENDER_COMPOSITION: Dict[str, Dict[str, int]] = {
    "15-19": {"male": 4, "female": 4},
    "20-29": {"male": 8, "female": 8},
    "30-39": {"male": 9, "female": 9},
    "40-49": {"male": 11, "female": 11},
    "50-59": {"male": 13, "female": 13},
    "60-64": {"male": 5, "female": 5},
}

COMPOSITION_SOURCE = {
    "mbti": "日本版MBTIマニュアルの標準サンプル比率",
    "age_gender": "総務省統計局の日本人人口（15〜64歳）",
}

DEFAULT_POOL_ID = "pool-001"
DEFAULT_POOL_SEED = 1001
DEFAULT_PATTERN_SET_ID = "pattern-set-001"
DEFAULT_PATTERN_SEED = 2001

SELECTION_MODE_RANDOM = "seeded_random_without_replacement"
SELECTION_MODE_FIXED = "fixed"


class PoolError(Exception):
    """人物プールの構成が定義と一致しない。"""


class PatternError(Exception):
    """パターンセットの構成が定義と一致しない。"""


@dataclass(frozen=True)
class Person:
    person_id: str
    mbti: str
    age: int
    gender: str

    def to_dict(self) -> Dict[str, object]:
        return {
            "person_id": self.person_id,
            "mbti": self.mbti,
            "age": self.age,
            "gender": self.gender,
        }


@dataclass(frozen=True)
class PersonPool:
    pool_id: str
    count: int
    seed: int
    assignment_mode: str
    persons: Tuple[Person, ...]
    composition: Dict[str, object]
    composition_source: Dict[str, str]
    generated_at: str

    def get(self, person_id: str) -> Person:
        for person in self.persons:
            if person.person_id == person_id:
                return person
        raise PoolError("人物が見つからない: {0}".format(person_id))

    def to_dict(self) -> Dict[str, object]:
        return {
            "pool_id": self.pool_id,
            "count": self.count,
            "generated_at": self.generated_at,
            "composition": self.composition,
            "composition_source": self.composition_source,
            "assignment_mode": self.assignment_mode,
            "seed": self.seed,
            "persons": [p.to_dict() for p in self.persons],
        }


@dataclass(frozen=True)
class Pattern:
    pattern_id: str
    person_ids: Tuple[str, ...]

    def to_dict(self) -> Dict[str, object]:
        return {"pattern_id": self.pattern_id, "person_ids": list(self.person_ids)}


@dataclass(frozen=True)
class PatternSet:
    pattern_set_id: str
    pool_id: str
    selection_mode: str
    seed: int
    patterns: Tuple[Pattern, ...]

    def get(self, pattern_id: str) -> Pattern:
        for pattern in self.patterns:
            if pattern.pattern_id == pattern_id:
                return pattern
        raise PatternError("パターンが見つからない: {0}".format(pattern_id))

    def to_dict(self) -> Dict[str, object]:
        return {
            "pattern_set_id": self.pattern_set_id,
            "pool_id": self.pool_id,
            "selection_mode": self.selection_mode,
            "seed": self.seed,
            "patterns": [p.to_dict() for p in self.patterns],
        }


def _age_band_range(band: str) -> Tuple[int, int]:
    low, high = band.split("-")
    return int(low), int(high)


def _validate_composition(count: int) -> None:
    mbti_total = sum(MBTI_COMPOSITION.values())
    if mbti_total != count:
        raise PoolError(
            "MBTI配分の合計が人数と一致しない: 配分{0}人 / count{1}人".format(mbti_total, count)
        )
    age_total = sum(
        sum(genders.values()) for genders in AGE_GENDER_COMPOSITION.values()
    )
    if age_total != count:
        raise PoolError(
            "年代・性別配分の合計が人数と一致しない: 配分{0}人 / count{1}人".format(age_total, count)
        )


def build_person_pool(
    pool_id: str = DEFAULT_POOL_ID,
    seed: int = DEFAULT_POOL_SEED,
    count: int = POOL_COUNT,
    generated_at: Optional[str] = None,
) -> PersonPool:
    """配分を満たす100人を生成する。

    MBTIの人数構成と年齢・性別の人数構成をそれぞれ満たしたうえで、両者を独立に
    ランダムに対応付ける（`seeded_random_independent`）。要求定義書8.2の「MBTIと
    年齢・性別の間に根拠のない関係を持たせない」を実装で表している。
    """

    _validate_composition(count)
    rng = random.Random(seed)

    mbti_slots: List[str] = []
    for mbti in sorted(MBTI_COMPOSITION):
        mbti_slots.extend([mbti] * MBTI_COMPOSITION[mbti])
    rng.shuffle(mbti_slots)

    demo_slots: List[Tuple[str, str]] = []
    for band in sorted(AGE_GENDER_COMPOSITION):
        for gender in sorted(AGE_GENDER_COMPOSITION[band]):
            demo_slots.extend([(band, gender)] * AGE_GENDER_COMPOSITION[band][gender])
    rng.shuffle(demo_slots)

    persons: List[Person] = []
    for index, (mbti, (band, gender)) in enumerate(zip(mbti_slots, demo_slots), start=1):
        low, high = _age_band_range(band)
        persons.append(
            Person(
                person_id="pe{0:03d}".format(index),
                mbti=mbti,
                age=rng.randint(low, high),
                gender=gender,
            )
        )

    composition = {
        "mbti": dict(MBTI_COMPOSITION),
        "age_gender": {
            band: dict(genders) for band, genders in AGE_GENDER_COMPOSITION.items()
        },
    }
    return PersonPool(
        pool_id=pool_id,
        count=count,
        seed=seed,
        assignment_mode="seeded_random_independent",
        persons=tuple(persons),
        composition=composition,
        composition_source=dict(COMPOSITION_SOURCE),
        generated_at=generated_at or datetime.now(JST).isoformat(timespec="seconds"),
    )


def build_pattern_set(
    pool: PersonPool,
    pattern_count: int,
    pattern_set_id: str = DEFAULT_PATTERN_SET_ID,
    seed: int = DEFAULT_PATTERN_SEED,
) -> PatternSet:
    """8人パターンを `pattern_count` 個生成する。

    復元なしは1パターン内の話であり、同じ人物が別のパターンへ現れることは許す。
    100人から8人ずつ重複なしに取ると12パターンしか作れず、100 Trialに足りない。
    """

    if pattern_count < 1:
        raise PatternError("パターン数は1以上にする: {0}".format(pattern_count))
    if len(pool.persons) < PLAYERS_PER_PATTERN:
        raise PatternError(
            "プールの人数がパターンの人数に足りない: プール{0}人".format(len(pool.persons))
        )

    rng = random.Random(seed)
    person_ids = [p.person_id for p in pool.persons]
    patterns: List[Pattern] = []
    for index in range(1, pattern_count + 1):
        chosen = rng.sample(person_ids, PLAYERS_PER_PATTERN)
        patterns.append(
            Pattern(
                pattern_id="pt{0:03d}".format(index),
                person_ids=tuple(chosen),
            )
        )
    return PatternSet(
        pattern_set_id=pattern_set_id,
        pool_id=pool.pool_id,
        selection_mode=SELECTION_MODE_RANDOM,
        seed=seed,
        patterns=tuple(patterns),
    )


def _observed_composition(persons: Sequence[Person]) -> Tuple[Dict[str, int], Dict[str, Dict[str, int]]]:
    mbti: Dict[str, int] = {}
    age_gender: Dict[str, Dict[str, int]] = {}
    for person in persons:
        mbti[person.mbti] = mbti.get(person.mbti, 0) + 1
        band = _band_of_age(person.age)
        age_gender.setdefault(band, {})
        age_gender[band][person.gender] = age_gender[band].get(person.gender, 0) + 1
    return mbti, age_gender


def _band_of_age(age: int) -> str:
    for band in AGE_GENDER_COMPOSITION:
        low, high = _age_band_range(band)
        if low <= age <= high:
            return band
    raise PoolError("年代の範囲外の年齢: {0}".format(age))


def load_person_pool(path: Path) -> PersonPool:
    """人物プールを読み込み、宣言された配分と実データの一致を検査する。"""

    raw = json.loads(path.read_text(encoding="utf-8"))
    persons = tuple(
        Person(
            person_id=str(item["person_id"]),
            mbti=str(item["mbti"]),
            age=int(item["age"]),
            gender=str(item["gender"]),
        )
        for item in raw["persons"]
    )
    count = int(raw["count"])
    if len(persons) != count:
        raise PoolError(
            "人物の件数がcountと一致しない: {0}件 / count{1}".format(len(persons), count)
        )
    if len({p.person_id for p in persons}) != len(persons):
        raise PoolError("person_idが重複している")

    declared = raw["composition"]
    observed_mbti, observed_age_gender = _observed_composition(persons)
    if observed_mbti != declared["mbti"]:
        raise PoolError("MBTI配分が宣言と一致しない")
    if observed_age_gender != declared["age_gender"]:
        raise PoolError("年代・性別配分が宣言と一致しない")
    if sum(declared["mbti"].values()) != count:
        raise PoolError("宣言されたMBTI配分の合計がcountと一致しない")
    if sum(sum(g.values()) for g in declared["age_gender"].values()) != count:
        raise PoolError("宣言された年代・性別配分の合計がcountと一致しない")

    return PersonPool(
        pool_id=str(raw["pool_id"]),
        count=count,
        seed=int(raw["seed"]),
        assignment_mode=str(raw["assignment_mode"]),
        persons=persons,
        composition=declared,
        composition_source=raw.get("composition_source", {}),
        generated_at=str(raw.get("generated_at", "")),
    )


def load_pattern_set(path: Path, pool: Optional[PersonPool] = None) -> PatternSet:
    """パターンセットを読み込み、人数と重複、プールとの整合を検査する。"""

    raw = json.loads(path.read_text(encoding="utf-8"))
    selection_mode = str(raw["selection_mode"])
    if selection_mode not in (SELECTION_MODE_RANDOM, SELECTION_MODE_FIXED):
        raise PatternError("未知の選定方式: {0}".format(selection_mode))

    patterns: List[Pattern] = []
    known_ids = {p.person_id for p in pool.persons} if pool is not None else None
    for item in raw["patterns"]:
        person_ids = tuple(str(v) for v in item["person_ids"])
        pattern_id = str(item["pattern_id"])
        if len(person_ids) != PLAYERS_PER_PATTERN:
            raise PatternError(
                "{0}の人数が{1}人でない: {2}人".format(
                    pattern_id, PLAYERS_PER_PATTERN, len(person_ids)
                )
            )
        if len(set(person_ids)) != len(person_ids):
            raise PatternError("{0}に同じ人物が重複している".format(pattern_id))
        if known_ids is not None:
            unknown = [pid for pid in person_ids if pid not in known_ids]
            if unknown:
                raise PatternError(
                    "{0}がプールにない人物を含む: {1}".format(pattern_id, ", ".join(unknown))
                )
        patterns.append(Pattern(pattern_id=pattern_id, person_ids=person_ids))

    if len({p.pattern_id for p in patterns}) != len(patterns):
        raise PatternError("pattern_idが重複している")

    pattern_set = PatternSet(
        pattern_set_id=str(raw["pattern_set_id"]),
        pool_id=str(raw["pool_id"]),
        selection_mode=selection_mode,
        seed=int(raw["seed"]),
        patterns=tuple(patterns),
    )
    if pool is not None and pattern_set.pool_id != pool.pool_id:
        raise PatternError(
            "パターンセットのpool_idがプールと一致しない: {0} / {1}".format(
                pattern_set.pool_id, pool.pool_id
            )
        )
    return pattern_set


def write_json(path: Path, payload: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
