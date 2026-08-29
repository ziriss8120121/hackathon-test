"""順位ベースの検定（設計書9.4）。

RQ1はWilcoxon符号付順位検定、RQ2はFriedman検定。どちらも正規分布を仮定せず、
順位だけで計算できる。SciPyを足さないため、ここへ実装している（1.1）。
"""

from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple


def median(values: Sequence[Optional[float]]) -> Optional[float]:
    usable = sorted(v for v in values if v is not None)
    if not usable:
        return None
    mid = len(usable) // 2
    if len(usable) % 2:
        return float(usable[mid])
    return (usable[mid - 1] + usable[mid]) / 2.0


def iqr(values: Sequence[Optional[float]]) -> Optional[float]:
    """四分位範囲。点が3つ未満なら区間を置けないので None。"""

    usable = sorted(v for v in values if v is not None)
    if len(usable) < 3:
        return None
    q1 = _percentile(usable, 0.25)
    q3 = _percentile(usable, 0.75)
    return q3 - q1


def _percentile(sorted_values: Sequence[float], fraction: float) -> float:
    last = len(sorted_values) - 1
    pos = fraction * last
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return float(sorted_values[lo])
    weight = pos - lo
    return sorted_values[lo] * (1 - weight) + sorted_values[hi] * weight


def average_ranks(values: Sequence[float]) -> List[float]:
    """同値は平均順位にする。WilcoxonとFriedmanの両方で使う。"""

    indexed = sorted(enumerate(values), key=lambda item: item[1])
    ranks = [0.0] * len(values)
    index = 0
    while index < len(indexed):
        end = index
        while end < len(indexed) and indexed[end][1] == indexed[index][1]:
            end += 1
        avg = (index + 1 + end) / 2.0
        for pos in range(index, end):
            ranks[indexed[pos][0]] = avg
        index = end
    return ranks


def wilcoxon_signed_rank(
    left: Sequence[Optional[float]], right: Sequence[Optional[float]]
) -> dict:
    """対応あり2群のWilcoxon符号付順位検定（両側）。

    `left` が混合側、`right` が同質側。差は混合 − 同質。差が0の組は捨てる（9.4）。
    組が20以下なら符号の全列挙で正確なpを出し、それを超えたら正規近似にする。
    1,700ケースをケース単位で検定する経路は持たない。単位はTrialである。
    """

    diffs: List[float] = []
    for a, b in zip(left, right):
        if a is None or b is None:
            continue
        delta = float(a) - float(b)
        if delta != 0:
            diffs.append(delta)

    n = len(diffs)
    empty = {
        "n": n,
        "w_plus": None,
        "w_minus": None,
        "p_two_sided": None,
        "r": None,
        "method": None,
    }
    if n == 0:
        return empty

    ranks = average_ranks([abs(d) for d in diffs])
    w_plus = sum(rank for rank, diff in zip(ranks, diffs) if diff > 0)
    w_minus = sum(rank for rank, diff in zip(ranks, diffs) if diff < 0)

    if n <= 20:
        p_value, z_score = _wilcoxon_exact(ranks, diffs)
        method = "exact"
    else:
        p_value, z_score = _wilcoxon_normal(w_plus, n)
        method = "normal"

    effect = None if z_score is None else round(abs(z_score) / math.sqrt(n), 4)
    return {
        "n": n,
        "w_plus": round(w_plus, 4),
        "w_minus": round(w_minus, 4),
        "p_two_sided": p_value,
        "r": effect,
        "method": method,
    }


def _wilcoxon_exact(
    ranks: Sequence[float], diffs: Sequence[float]
) -> Tuple[Optional[float], Optional[float]]:
    """各差の符号を独立に反転したときの W+ の分布から両側pを出す。"""

    observed = sum(rank for rank, diff in zip(ranks, diffs) if diff > 0)
    total = 1 << len(ranks)
    extreme = 0
    mean = sum(ranks) / 2.0
    for mask in range(total):
        w_plus = 0.0
        for index, rank in enumerate(ranks):
            if mask & (1 << index):
                w_plus += rank
        # 観測値以上に平均から離れているものを数える。
        if abs(w_plus - mean) + 1e-9 >= abs(observed - mean):
            extreme += 1
    p_value = min(1.0, extreme / total)
    variance = sum(r * r for r in ranks) / 4.0
    z_score = 0.0 if variance == 0 else (observed - mean) / math.sqrt(variance)
    return round(p_value, 6), z_score


def _wilcoxon_normal(w_plus: float, n: int) -> Tuple[Optional[float], Optional[float]]:
    mean = n * (n + 1) / 4.0
    variance = n * (n + 1) * (2 * n + 1) / 24.0
    if variance == 0:
        return None, None
    z_score = (w_plus - mean) / math.sqrt(variance)
    p_value = math.erfc(abs(z_score) / math.sqrt(2.0))
    return round(min(1.0, p_value), 6), z_score


def friedman(matrix: Sequence[Sequence[Optional[float]]]) -> dict:
    """対応ありk条件のFriedman検定。

    行がTrial、列がタイプ。欠損を含む行は捨てる。事後比較はしない（9.4）。
    """

    if not matrix:
        return {"n": 0, "k": 0, "q": None, "p": None, "rank_sums": []}

    k = len(matrix[0])
    complete: List[List[float]] = []
    for row in matrix:
        if len(row) != k or any(value is None for value in row):
            continue
        complete.append([float(v) for v in row])

    n = len(complete)
    if n < 2 or k < 2:
        return {"n": n, "k": k, "q": None, "p": None, "rank_sums": [0.0] * k}

    rank_sums = [0.0] * k
    for row in complete:
        ranks = average_ranks(row)
        for index, rank in enumerate(ranks):
            rank_sums[index] += rank

    q_stat = (12.0 / (n * k * (k + 1))) * sum(s * s for s in rank_sums) - 3.0 * n * (k + 1)
    df = k - 1
    p_value = chi2_sf(max(0.0, q_stat), df)
    return {
        "n": n,
        "k": k,
        "q": round(q_stat, 4),
        "p": round(p_value, 6),
        "rank_sums": [round(s, 4) for s in rank_sums],
    }


def chi2_sf(stat: float, df: int) -> float:
    """カイ二乗分布の上側確率。Wilson–Hilferty近似。SciPyを足さないため。"""

    if df < 1:
        return 1.0
    if stat <= 0:
        return 1.0
    mu = 1.0 - 2.0 / (9.0 * df)
    sigma = math.sqrt(2.0 / (9.0 * df))
    z_score = ((stat / df) ** (1.0 / 3.0) - mu) / sigma
    return min(1.0, max(0.0, 0.5 * math.erfc(z_score / math.sqrt(2.0))))
