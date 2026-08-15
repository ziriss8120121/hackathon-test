"""同数得票の決着（設計書4.5）。

再投票は行わない。再投票にすると推論の呼び出しが増えて待機時間が伸びるうえ、
再投票でも同数になる可能性が残って終了条件を保証できないためである。
要件F-06の「常に1試合が終了する状態」を、seedを固定した乱数で満たす。

乱数で決めた処刑は実力で決まったものではない。その情報が後からログで判別
できるように、決着方法と候補を必ず残す。
"""

from __future__ import annotations

import random
from typing import Any, Dict, List, Sequence, Tuple


def break_tie(
    candidates: Sequence[str], seed: int, turn_count: int
) -> Tuple[str, Dict[str, Any]]:
    ordered: List[str] = sorted(candidates)
    tie_seed = seed + turn_count
    chosen = random.Random(tie_seed).choice(ordered)
    return chosen, {
        "method": "seeded_random",
        "candidates": ordered,
        "player_id": chosen,
        "seed": tie_seed,
    }
