"""公開スタンス系列の導出（設計書5.5、9.2）。

Judgeの出力から機械的に作る。推論を呼ばないので、算出方法を変えたいときに
Judgeを回し直す必要がない。

要件F-44への対応がここにある。発言のたびに疑いを数え上げると、疑念分布が
発言量に引きずられる。各人の「現在の公開スタンス」を1件だけ保持する形に
正規化することで、分布の合計は常に参加人数以下になる。
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence

DIRECTION_SUSPECT = "suspect"
DIRECTION_DEFEND = "defend"
DIRECTIONS = (DIRECTION_SUSPECT, DIRECTION_DEFEND)
STRENGTHS = (1, 2, 3)


def pick_stance(stances: Sequence[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """1発言のスタンスから1件を選ぶ（設計書5.5）。

    `strength` が最大のものを採用し、同値なら最後に現れたものを採用する。
    """

    chosen: Optional[Dict[str, Any]] = None
    for stance in stances:
        if chosen is None or int(stance["strength"]) >= int(chosen["strength"]):
            chosen = stance
    return dict(chosen) if chosen is not None else None


def suspicion_distribution(
    current_stances: Dict[str, Optional[Dict[str, Any]]]
) -> Dict[str, int]:
    """`direction` が `suspect` のスタンスを対象ごとに数える。

    1人1件なので、合計は参加人数を超えない。
    """

    distribution: Dict[str, int] = {}
    for stance in current_stances.values():
        if stance is None or stance["direction"] != DIRECTION_SUSPECT:
            continue
        target = stance["target"]
        distribution[target] = distribution.get(target, 0) + 1
    return distribution


def normalized_entropy(distribution: Dict[str, int], participant_count: int) -> float:
    """疑念分布の正規化エントロピー（設計書9.2）。

    `H = -Σ(p_i × log p_i) / log n` とし、`n` は分布に現れた対象の数ではなく
    参加人数で固定する。対象の数で正規化すると、2人にしか疑いが向いていない
    分布と8人に分散した分布が同じ値になりうる。

    疑いが1件もない時点は0を返す。分散しているのではなく分布が存在しないので、
    「完全な分散」を表す1にはしない。
    """

    total = sum(distribution.values())
    if total <= 0 or participant_count < 2:
        return 0.0

    entropy = 0.0
    for count in distribution.values():
        if count <= 0:
            continue
        ratio = count / total
        entropy -= ratio * math.log(ratio)
    return round(entropy / math.log(participant_count), 6)


def derive_stance_series(
    speeches: Sequence[Dict[str, Any]],
    stances_by_speech: Dict[str, Sequence[Dict[str, Any]]],
    player_ids: Sequence[str],
) -> List[Dict[str, Any]]:
    """`speech_id` の順に各時点の疑念分布を作る（設計書5.5）。

    `speeches` は `speech_id` と `player_id` を持つ発言を発言順に並べたもの。

    スタンスを含まない発言では、その発言者の直前のスタンスをそのまま残す。
    スタンスは「現在の立場」という状態であり、質問や役職主張のように立場を
    示さない発言をしたことは、直前の立場の取り下げにはあたらないためである。
    """

    current: Dict[str, Optional[Dict[str, Any]]] = {pid: None for pid in player_ids}
    series: List[Dict[str, Any]] = []

    for speech in speeches:
        speaker = speech["player_id"]
        chosen = pick_stance(stances_by_speech.get(speech["speech_id"], ()))
        if chosen is not None and speaker in current:
            current[speaker] = chosen

        distribution = suspicion_distribution(current)
        series.append(
            {
                "at_speech_id": speech["speech_id"],
                "current_stances": {
                    pid: (dict(current[pid]) if current[pid] is not None else None)
                    for pid in player_ids
                },
                "suspicion_distribution": distribution,
                "entropy": normalized_entropy(distribution, len(player_ids)),
            }
        )

    return series
