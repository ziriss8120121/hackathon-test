#!/usr/bin/env python3
"""labeling-analysis-spec.md のP0/P1を、完了ケース全体で検証する。

Judgeがある発言はLLMラベルを正とする。ない発言は規則で補い、出典を残す。
ラベル付けでは役職・勝敗を見ない。突合とM指標は分析時だけ行う。
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mbti_werewolf.analysis.indicators import RQ1_METRICS, enriched_case_metrics
from mbti_werewolf.analysis.stats import friedman, median, wilcoxon_signed_rank
from mbti_werewolf.engine.roles import TEAM_WEREWOLF, team_of
from mbti_werewolf.judge.judge import judge_file_name
from mbti_werewolf.judge.stance import pick_stance
from mbti_werewolf.record.case_metrics import (
    normalized_entropy,
    player_metrics,
)

JST = timezone(timedelta(hours=9))
PLAYER_RE = re.compile(r"\b[Pp]([1-8])\b|[Ｐｐ]([1-8])")
ROLE_SELF_RE = re.compile(r"私は(?:、)?(村人|人狼|占い師|怪盗)")
OTHER_ROLE_RE = re.compile(r"[PpＰｐ]([1-8])\s*(?:さん)?(?:は|が)(村人|人狼|占い師|怪盗)")
ROLE_WORDS = ("村人", "人狼", "占い師", "怪盗")
ROLE_EN = {"村人": "villager", "人狼": "werewolf", "占い師": "seer", "怪盗": "thief"}
P0_PAIR_METRICS = RQ1_METRICS + (
    "village_win",
    "suspect_change_rate",
    "judgment_entropy_final",
)
LABEL_ALIAS = {"intent": "vote_intent"}

LABEL_RULES = (
    ("vote_intent", ("投票", "票を", "追放")),
    ("question", ("？", "?", "ですか", "ますか", "でしょうか", "確認")),
    ("rebut", ("しかし", "ただし", "違う", "誤り", "反対", "反論")),
    ("agree", ("同意", "賛成", "同じです", "その通り", "賛成です")),
    ("defend", ("擁護", "信じ", "白だ", "村人だと思う", "疑わなくて")),
    ("suspect", ("疑", "怪しい", "黒", "人狼だと思う", "人狼では")),
    ("hypothesis", ("もし", "可能性", "かもしれない", "ではないか", "仮説")),
    ("claim", ("私は", "役職", "占い", "夜の", "接触", "情報")),
)


def _now() -> str:
    return datetime.now(JST).strftime("%Y-%m-%dT%H:%M:%S+09:00")


def _mean(values: Sequence[Optional[float]]) -> Optional[float]:
    usable = [float(v) for v in values if v is not None]
    if not usable:
        return None
    return round(sum(usable) / len(usable), 4)


def _rate(num: int, den: int) -> Optional[float]:
    if den == 0:
        return None
    return round(num / den, 4)


def _fmt(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return "{0:.3f}".format(value)
    return str(value)


def _pct(value: Optional[float]) -> str:
    if value is None:
        return "—"
    return "{0:.1f}%".format(value * 100)


def load_done_cases(runs_dir: Path) -> List[Tuple[Dict[str, Any], Optional[Dict[str, Any]]]]:
    cases: List[Tuple[Dict[str, Any], Optional[Dict[str, Any]]]] = []
    judge_name = judge_file_name()
    for exp_dir in sorted(p for p in runs_dir.iterdir() if p.is_dir() and p.name.startswith("e-")):
        for path in sorted(exp_dir.rglob("case_log.json")):
            try:
                log = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if log.get("status") != "done":
                continue
            judge = None
            judge_path = path.parent / judge_name
            if judge_path.is_file():
                try:
                    judge = json.loads(judge_path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    judge = None
            cases.append((log, judge))
    return cases


def suspect_entropy(answers: Sequence[Dict[str, Any]], player_count: int) -> Optional[float]:
    dist: Dict[str, int] = {}
    for row in answers:
        suspect = row.get("suspect")
        if not suspect or suspect == "unknown":
            continue
        dist[suspect] = dist.get(suspect, 0) + 1
    return normalized_entropy(dist, player_count)


def enrich_case(log: Dict[str, Any], judge: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    row = enriched_case_metrics(log, judge)
    players = log.get("players") or []
    row["judgment_entropy_pre"] = suspect_entropy(
        log.get("pre_discussion_answers") or [], len(players)
    )
    row["judgment_entropy_final"] = suspect_entropy(
        log.get("pre_vote_answers") or [], len(players)
    )
    pre_e = row["judgment_entropy_pre"]
    fin_e = row["judgment_entropy_final"]
    row["judgment_entropy_delta"] = (
        round(fin_e - pre_e, 4) if pre_e is not None and fin_e is not None else None
    )
    row["village_win"] = 1 if row.get("winner") == "village" else 0 if row.get("winner") else None
    row["werewolf_win"] = 1 if row.get("winner") == "werewolf" else 0 if row.get("winner") else None
    change_vals = [p["suspect_changed"] for p in player_metrics(log)]
    row["suspect_change_rate"] = _mean(change_vals)
    row["has_judge"] = 1 if judge else 0
    return row


def mentions_in(text: str) -> List[str]:
    found = []
    for match in PLAYER_RE.finditer(text):
        num = match.group(1) or match.group(2)
        pid = "p{0}".format(num)
        if pid not in found:
            found.append(pid)
    return found


def assign_labels(text: str) -> List[str]:
    labels: List[str] = []
    for name, needles in LABEL_RULES:
        if any(n in text for n in needles):
            labels.append(name)
    if not labels:
        labels.append("other")
    return labels


def evidence_basis(text: str) -> List[str]:
    bases: List[str] = []
    if any(w in text for w in ("占い", "夜", "役職", "接触", "見た", "確認")):
        bases.append("role_information")
    if any(w in text for w in ("矛盾", "整合", "論理", "つじつま")):
        bases.append("logical_consistency")
    if any(w in text for w in ("態度", "言い回", "発言量", "沈黙")):
        bases.append("behavioral_impression")
    if any(w in text for w in ("同意", "皆", "多数", "みんな")):
        bases.append("social_alignment")
    if any(w in text for w in ("もし", "かも", "可能性", "ではないか")):
        bases.append("speculation")
    if not bases:
        bases.append("unclear")
    return bases


def claim_types(text: str, labels: Sequence[str]) -> List[str]:
    types: List[str] = []
    if any(w in text for w in ROLE_WORDS) or "私は" in text:
        types.append("role")
    if any(w in text for w in ("夜", "接触", "占った", "見た", "情報")):
        types.append("information")
    if "suspect" in labels or any(w in text for w in ("判断", "思う")):
        types.append("judgment")
    if "vote_intent" in labels:
        types.append("vote")
    if not types:
        types.append("none")
    return types


def stance_for(text: str, target: str, labels: Sequence[str]) -> Dict[str, Any]:
    direction = "unclear"
    strength = 1
    if "suspect" in labels or any(w in text for w in ("疑", "怪しい", "黒")):
        direction = "suspicion"
        strength = 3 if any(w in text for w in ("断定", "間違いない", "人狼だ")) else 2
    elif "defend" in labels or any(w in text for w in ("信じ", "擁護", "白")):
        direction = "support"
        strength = 2
    elif "agree" in labels:
        direction = "support"
        strength = 1
    elif "question" in labels:
        direction = "neutral"
        strength = 1
    return {"target": target, "direction": direction, "strength": strength}


def change_type(
    speaker: str,
    mentions: Sequence[str],
    labels: Sequence[str],
    last_focus: Dict[str, Optional[str]],
) -> str:
    if "suspect" not in labels and "hypothesis" not in labels:
        return "none"
    focus = mentions[0] if mentions else None
    prev = last_focus.get(speaker)
    last_focus[speaker] = focus
    if focus is None:
        return "new" if prev is None else "maintain"
    if prev is None:
        return "new"
    if prev == focus:
        return "maintain"
    return "change"


def role_claim_match(text: str, actual: Optional[str]) -> str:
    match = ROLE_SELF_RE.search(text)
    if not match or not actual:
        return "unjudged"
    claimed = ROLE_EN.get(match.group(1))
    if claimed is None:
        return "unjudged"
    return "match" if claimed == actual else "mismatch"


def _norm_labels(labels: Sequence[str]) -> List[str]:
    out = []
    for name in labels:
        mapped = LABEL_ALIAS.get(name, name)
        if mapped not in out:
            out.append(mapped)
    return out


def _pid(value: object) -> str:
    text = str(value or "").strip().lower()
    if text.startswith("p") and text[1:].isdigit():
        return "p{0}".format(text[1:])
    return text


def night_info_by_actor(log: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    info: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for action in log.get("night_actions") or []:
        actor = action.get("actor")
        if not actor:
            continue
        info[actor].append(action)
    return info


def compare_value(predicted: Optional[str], actual: Optional[str]) -> str:
    if not predicted or predicted == "unknown" or not actual:
        return "unjudged"
    return "match" if _pid(predicted) == _pid(actual) or predicted == actual else "mismatch"


def attach_truth(row: Dict[str, Any], log: Dict[str, Any]) -> None:
    """分析時だけ正解と突合する。ラベル付けでは呼ばない。"""

    players = {p["player_id"]: p for p in log.get("players") or []}
    speaker = row["player_id"]
    player = players.get(speaker) or {}
    text = row.get("speech_text") or ""
    pre = {a["player_id"]: a for a in log.get("pre_discussion_answers") or []}
    post = {a["player_id"]: a for a in log.get("pre_vote_answers") or []}
    votes = {v["voter"]: v for v in log.get("votes") or []}
    result = log.get("result") or {}
    executed = list(result.get("executed") or [])
    winner = result.get("winner")
    night = night_info_by_actor(log).get(speaker) or []

    row["self_role_vs_initial"] = role_claim_match(text, player.get("initial_role"))
    row["self_role_vs_final"] = role_claim_match(text, player.get("final_role"))

    other_matches = []
    for match in OTHER_ROLE_RE.finditer(text):
        target = "p{0}".format(match.group(1))
        claimed = ROLE_EN.get(match.group(2))
        actual = (players.get(target) or {}).get("final_role")
        other_matches.append(compare_value(claimed, actual))
    if other_matches:
        row["other_role_vs_final"] = (
            "mismatch" if "mismatch" in other_matches else "match"
        )
    else:
        row["other_role_vs_final"] = "unjudged"

    night_verdicts = []
    for action in night:
        target = action.get("target")
        revealed = action.get("revealed_initial_role")
        if not target or not revealed:
            continue
        if _pid(target) not in row.get("mentions", "").split("|"):
            continue
        claimed = None
        found = OTHER_ROLE_RE.search(text)
        if found:
            claimed = ROLE_EN.get(found.group(2))
        night_verdicts.append(compare_value(claimed, revealed))
    row["night_info_vs_claim"] = (
        "unjudged"
        if not night_verdicts
        else ("mismatch" if "mismatch" in night_verdicts else "match")
    )

    pre_s = (pre.get(speaker) or {}).get("suspect")
    post_s = (post.get(speaker) or {}).get("suspect")
    vote = votes.get(speaker) or {}
    actual_vote = None if vote.get("abstained") else vote.get("target")
    mentions = [m for m in str(row.get("mentions") or "").split("|") if m]
    first = mentions[0] if mentions else None
    row["vs_pre_suspect"] = compare_value(first, pre_s) if first else "unjudged"
    row["vs_final_suspect"] = compare_value(first, post_s) if first else "unjudged"
    row["vs_actual_vote"] = compare_value(first, actual_vote) if first else "unjudged"
    row["vs_executed"] = (
        compare_value(first, executed[0]) if first and executed else "unjudged"
    )
    if "village" in text or "人狼" in text:
        if winner == "village" and "村人" in text and "勝ち" in text:
            row["vs_winner"] = "match"
        elif winner == "werewolf" and "人狼" in text and "勝ち" in text:
            row["vs_winner"] = "match"
        else:
            row["vs_winner"] = "unjudged"
    else:
        row["vs_winner"] = "unjudged"


def label_speeches(
    log: Dict[str, Any], judge: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    players = {p["player_id"]: p for p in log.get("players") or []}
    judged = {s.get("speech_id"): s for s in (judge or {}).get("speeches") or []}
    last_focus: Dict[str, Optional[str]] = {}
    last_stance: Dict[str, Optional[str]] = {}
    rows: List[Dict[str, Any]] = []
    for event in (log.get("discussion") or {}).get("events") or []:
        if not event.get("spoke"):
            continue
        text = event.get("speech_text") or ""
        speaker = event.get("player_id")
        player = players.get(speaker) or {}
        evaluation = judged.get(event.get("speech_id"))
        source = "rule"
        if evaluation and not evaluation.get("parse_failed"):
            source = "judge"
            labels = _norm_labels(evaluation.get("labels") or [])
            mentions = [_pid(m) for m in evaluation.get("mentions") or [] if m]
            raw_stances = evaluation.get("stances") or []
            stances = []
            for item in raw_stances:
                direction = item.get("direction")
                mapped = {
                    "suspect": "suspicion",
                    "defend": "support",
                }.get(direction, direction or "unclear")
                stances.append(
                    {
                        "target": _pid(item.get("target")),
                        "direction": mapped,
                        "strength": item.get("strength"),
                    }
                )
            if not labels:
                labels = ["other"]
        else:
            labels = assign_labels(text)
            mentions = mentions_in(text)
            stances = [stance_for(text, target, labels) for target in mentions]
        chosen = pick_stance(evaluation.get("stances") or []) if evaluation else None
        focus = _pid((chosen or {}).get("target")) if chosen else (mentions[0] if mentions else None)
        prev = last_stance.get(speaker)
        if chosen is None and "suspect" not in labels and "hypothesis" not in labels:
            change = "none"
        elif prev is None and focus:
            change = "new"
        elif prev and focus and prev != focus:
            change = "change"
        elif prev and focus and prev == focus:
            change = "maintain"
        elif prev and not focus:
            change = "withdraw"
        else:
            change = change_type(speaker, mentions, labels, last_focus)
        if focus:
            last_stance[speaker] = focus
        claims = claim_types(text, labels)
        row = {
            "experiment_id": log["experiment_id"],
            "trial_id": log["trial_id"],
            "case_id": log["case_id"],
            "composition": log.get("composition"),
            "homogeneous_type": log.get("homogeneous_type") or "",
            "speech_id": event.get("speech_id") or "",
            "order": event.get("order"),
            "round": event.get("round"),
            "player_id": speaker,
            "person_id": player.get("person_id") or "",
            "mbti": player.get("mbti") or "",
            "speech_text": text,
            "label_source": source,
            "labels": "|".join(labels),
            "mentions": "|".join(mentions),
            "stances": json.dumps(stances, ensure_ascii=False) if stances else "",
            "change_type": change,
            "evidence_basis": "|".join(evidence_basis(text)),
            "claim_type": "|".join(claims),
            "claim_content": text[:120],
        }
        attach_truth(row, log)
        rows.append(row)
    return rows


def process_metrics(speeches: Sequence[Dict[str, Any]], log: Dict[str, Any]) -> Dict[str, Optional[float]]:
    """M-01〜M-07。ケース単位。"""

    n = len(speeches) or 1
    labels_list = [str(s.get("labels") or "").split("|") for s in speeches]
    agree_n = sum(1 for labs in labels_list if "agree" in labs)
    rebut_n = sum(1 for labs in labels_list if "rebut" in labs)
    first_mention: Dict[str, str] = {}
    later_followers: Dict[str, int] = defaultdict(int)
    mention_speakers: Dict[str, set] = defaultdict(set)
    suspect_by_speaker: Dict[str, List[str]] = defaultdict(list)
    for speech in speeches:
        speaker = speech["player_id"]
        mentions = [m for m in str(speech.get("mentions") or "").split("|") if m]
        labs = str(speech.get("labels") or "").split("|")
        for target in mentions:
            mention_speakers[target].add(speaker)
            if target not in first_mention:
                first_mention[target] = speaker
            elif first_mention[target] != speaker:
                later_followers[target] += 1
        if "suspect" in labs and mentions:
            suspect_by_speaker[speaker].append(mentions[0])
    spread = max((len(v) for v in mention_speakers.values()), default=0)
    counter = 0
    speakers = list(suspect_by_speaker)
    for i, a in enumerate(speakers):
        for b in speakers[i + 1 :]:
            a_t = set(suspect_by_speaker[a])
            b_t = set(suspect_by_speaker[b])
            if b in a_t and a in b_t:
                counter += 1
    post = {a["player_id"]: a.get("suspect") for a in log.get("pre_vote_answers") or []}
    counts = Counter(v for v in post.values() if v and v != "unknown")
    majority = counts.most_common(1)[0][0] if counts else None
    minority = 0
    if majority:
        minority = sum(1 for pid, suspect in post.items() if suspect and suspect != "unknown" and suspect != majority)
    leadership = sum(1 for target, _ in first_mention.items() if later_followers.get(target, 0) >= 1)
    return {
        "m01_leadership": _rate(leadership, len(first_mention) or 1),
        "m02_follow": _rate(agree_n + sum(later_followers.values()), n),
        "m03_spread": spread / 8.0,
        "m04_counter": _rate(counter, max(1, len(speakers))),
        "m05_rebut": _rate(rebut_n, n),
        "m06_agree": _rate(agree_n, n),
        "m07_minority": _rate(minority, 8),
    }


def group_stats(rows: Sequence[Dict[str, Any]], keys: Sequence[str]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not rows:
        return out
    n = len(rows)
    village_wins = [r["village_win"] for r in rows]
    village_correct = [r["village_correct"] for r in rows]
    out.append(
        {
            "n_cases": n,
            "village_win_rate": _mean(village_wins),
            "werewolf_win_rate": _mean([r["werewolf_win"] for r in rows]),
            "village_correct_rate": _mean(village_correct),
            "village_vote_accuracy": _mean([r["village_vote_accuracy"] for r in rows]),
            "vote_concentration": _mean([r["vote_concentration"] for r in rows]),
            "judgment_entropy_pre": _mean([r["judgment_entropy_pre"] for r in rows]),
            "judgment_entropy_final": _mean([r["judgment_entropy_final"] for r in rows]),
            "judgment_entropy_delta": _mean([r["judgment_entropy_delta"] for r in rows]),
            "suspect_change_rate": _mean([r["suspect_change_rate"] for r in rows]),
            "correction_rate": _mean([r["correction_rate"] for r in rows]),
            "deterioration_rate": _mean([r["deterioration_rate"] for r in rows]),
            "mean_confidence_delta": _mean([r["mean_confidence_delta"] for r in rows]),
            "mean_rounds": _mean([r["rounds"] for r in rows]),
            "pass_rate": _mean([r["pass_rate"] for r in rows]),
            "speech_count_gini": _mean([r["speech_count_gini"] for r in rows]),
            "final_entropy": _mean([r.get("final_entropy") for r in rows]),
            "convergence_round": _mean([r.get("convergence_round") for r in rows]),
            "has_judge_rate": _mean([r.get("has_judge") for r in rows]),
            "m01_leadership": _mean([r.get("m01_leadership") for r in rows]),
            "m02_follow": _mean([r.get("m02_follow") for r in rows]),
            "m03_spread": _mean([r.get("m03_spread") for r in rows]),
            "m04_counter": _mean([r.get("m04_counter") for r in rows]),
            "m05_rebut": _mean([r.get("m05_rebut") for r in rows]),
            "m06_agree": _mean([r.get("m06_agree") for r in rows]),
            "m07_minority": _mean([r.get("m07_minority") for r in rows]),
        }
    )
    for key, value in zip(keys, [None] * len(keys)):
        out[0][key] = value
    return out


def summarize_by(rows: Sequence[Dict[str, Any]], key: str) -> List[Dict[str, Any]]:
    buckets: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        buckets[str(row.get(key) or "")].append(row)
    result = []
    for name in sorted(buckets):
        stats = group_stats(buckets[name], (key,))[0]
        stats[key] = name
        result.append(stats)
    return result


def write_csv(path: Path, rows: Sequence[Dict[str, Any]], fieldnames: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            clean = {}
            for name in fieldnames:
                value = row.get(name)
                if isinstance(value, list):
                    value = "|".join(str(v) for v in value)
                clean[name] = "" if value is None else value
            writer.writerow(clean)


def complete_trials(rows: Sequence[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    by_trial: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_trial[row["trial_id"]].append(row)
    complete = {}
    for trial_id, cases in by_trial.items():
        mixed = [c for c in cases if c["composition"] == "mixed"]
        homo = [c for c in cases if c["composition"] == "homogeneous"]
        if len(cases) >= 17 and len(mixed) == 1 and len(homo) == 16:
            complete[trial_id] = cases
    return complete


def trial_pairs(
    rows: Sequence[Dict[str, Any]], metric: str = "village_correct"
) -> Tuple[List[float], List[float], List[str]]:
    """完全な17ケースが揃ったTrialだけ、混合 vs 同質中央値のペアを作る。"""

    mixed_vals: List[float] = []
    homo_vals: List[float] = []
    used: List[str] = []
    for trial_id, cases in sorted(complete_trials(rows).items()):
        mixed = [c for c in cases if c["composition"] == "mixed"]
        homo = [c for c in cases if c["composition"] == "homogeneous"]
        left = mixed[0].get(metric)
        right = median([c.get(metric) for c in homo])
        if left is None or right is None:
            continue
        mixed_vals.append(float(left))
        homo_vals.append(float(right))
        used.append(trial_id)
    return mixed_vals, homo_vals, used


def friedman_by_type(rows: Sequence[Dict[str, Any]], metric: str) -> dict:
    types = sorted({r.get("homogeneous_type") for r in rows if r.get("homogeneous_type")})
    matrix = []
    for _trial_id, cases in complete_trials(rows).items():
        by_type = {c.get("homogeneous_type"): c.get(metric) for c in cases if c["composition"] == "homogeneous"}
        matrix.append([by_type.get(name) for name in types])
    result = friedman(matrix)
    result["types"] = types
    return result


def label_counts(speeches: Sequence[Dict[str, Any]], key: str = "composition") -> Dict[str, Counter]:
    counts: Dict[str, Counter] = defaultdict(Counter)
    for row in speeches:
        bucket = str(row.get(key) or "")
        for label in str(row.get("labels") or "").split("|"):
            if label:
                counts[bucket][label] += 1
        counts[bucket]["_n"] += 1
    return counts


def md_table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(_fmt(c) for c in row) + " |")
    return "\n".join(lines)


def render_markdown(
    generated_at: str,
    case_rows: Sequence[Dict[str, Any]],
    speeches: Sequence[Dict[str, Any]],
    coverage: Dict[str, Any],
) -> str:
    mixed = [r for r in case_rows if r["composition"] == "mixed"]
    homo = [r for r in case_rows if r["composition"] == "homogeneous"]
    mixed_s = group_stats(mixed, ())[0] if mixed else {}
    homo_s = group_stats(homo, ())[0] if homo else {}
    by_type = summarize_by(homo, "homogeneous_type")
    pairs = trial_pairs(case_rows)
    wilcox = wilcoxon_signed_rank(pairs[0], pairs[1]) if pairs[2] else None
    label_by_comp = label_counts(speeches, "composition")
    change_by_comp: Dict[str, Counter] = defaultdict(Counter)
    for row in speeches:
        change_by_comp[str(row["composition"])][row["change_type"]] += 1
    match_rows = [s for s in speeches if s["self_role_vs_final"] in ("match", "mismatch")]
    claim_match = _rate(
        sum(1 for s in match_rows if s["self_role_vs_final"] == "match"),
        len(match_rows),
    )

    def metric_row(label: str, key: str, as_pct: bool = False) -> List[Any]:
        fmt = _pct if as_pct else _fmt
        return [label, fmt(mixed_s.get(key)), fmt(homo_s.get(key))]

    type_rows = [
        [
            item["homogeneous_type"],
            item["n_cases"],
            _pct(item["village_win_rate"]),
            _pct(item["village_correct_rate"]),
            _fmt(item["vote_concentration"]),
            _fmt(item["judgment_entropy_final"]),
            _pct(item["correction_rate"]),
            _fmt(item["mean_confidence_delta"]),
        ]
        for item in by_type
    ]

    label_rows = []
    label_names = (
        "suspect",
        "defend",
        "question",
        "rebut",
        "agree",
        "claim",
        "hypothesis",
        "vote_intent",
        "other",
    )
    for name in label_names:
        cells = [name]
        for bucket in ("mixed", "homogeneous"):
            counter = label_by_comp.get(bucket, Counter())
            n = counter.get("_n") or 0
            cells.append(_pct(_rate(counter.get(name, 0), n)))
        label_rows.append(cells)

    lines = [
        "# 発言ラベリング・分析結果",
        "",
        "生成日時: `{0}`".format(generated_at),
        "",
        "対象は `runs/e-*` のうち、`case_log.json` が `done` のケース。",
        "仕様は `docs/submission/labeling-analysis-spec.md`。",
        "",
        "## 読み方",
        "",
        "- **P0** は既存指標。Judgeがある試合は設計どおりの疑念分散・収束ラウンドも使う。",
        "- **P1** の `labels` / `mentions` / `stances` は、Judge済みならLLM、未評価なら規則。`label_source` 列で区別する。",
        "- 役職・勝敗はラベル付けに使っていない。突合は分析時だけ。",
        "- 「支持／反対」は方向の整理であり、データが揃うまでの暫定判断も含む。",
        "",
        "## 対象の範囲",
        "",
        "- 実験数: {0}".format(coverage["experiments"]),
        "- 完了ケース: {0}".format(len(case_rows)),
        "- 混合: {0} / 同質: {1}".format(len(mixed), len(homo)),
        "- 完了発言: {0}".format(len(speeches)),
        "- 17ケース揃ったTrial: {0}".format(len(pairs[2]) or 0),
        "",
        md_table(
            ("実験", "完了ケース", "混合", "同質", "状態"),
            coverage["experiment_rows"],
        ),
        "",
        "## P0：構成による違い（混合 vs 同質）",
        "",
        "単位はケース。1ケース = 1試合。混合 {0} 試合、同質 {1} 試合なので、混合側はブレやすい。".format(
            len(mixed), len(homo)
        ),
        "議論前の分散が0に近いのは、開始時点でほとんどが `unknown` だからである。",
        "",
        md_table(
            ("指標", "混合", "同質"),
            [
                metric_row("R1-03 村人陣営の勝率", "village_win_rate", True),
                metric_row("R1-02 人狼を見抜けた割合（追放に人狼）", "village_correct_rate", True),
                metric_row("村人側の投票正答率", "village_vote_accuracy", True),
                metric_row("R1-05 投票の集中", "vote_concentration"),
                metric_row("R1-04 議論前の判断の分散（低いほど集中）", "judgment_entropy_pre"),
                metric_row("R1-04 投票前の判断の分散", "judgment_entropy_final"),
                metric_row("R1-08 分散の変化（負なら収束）", "judgment_entropy_delta"),
                metric_row("R1-06 判断変更率", "suspect_change_rate", True),
                metric_row("R1-09 誤った初期判断の修正率", "correction_rate", True),
                metric_row("正しい初期判断の悪化率", "deterioration_rate", True),
                metric_row("R1-07 確信度の変化", "mean_confidence_delta"),
                metric_row("平均ラウンド数", "mean_rounds"),
                metric_row("見送り率", "pass_rate", True),
                metric_row("発言回数の偏り", "speech_count_gini"),
            ],
        ),
        "",
        "### いま言えること（P0）",
        "",
    ]

    findings: List[str] = []
    if mixed_s and homo_s:
        if (mixed_s.get("village_win_rate") or 0) != (homo_s.get("village_win_rate") or 0):
            winner = "混合" if (mixed_s.get("village_win_rate") or 0) > (homo_s.get("village_win_rate") or 0) else "同質"
            findings.append(
                "- 村人の勝率は{0}の方が高い（混合 {1} / 同質 {2}）。".format(
                    winner, _pct(mixed_s.get("village_win_rate")), _pct(homo_s.get("village_win_rate"))
                )
            )
        if (homo_s.get("judgment_entropy_final") or 9) < (mixed_s.get("judgment_entropy_final") or 9):
            findings.append("- 投票前の判断は同質の方が集中しやすい（分散が低い）。R1-08の方向と一致する。")
        elif (mixed_s.get("judgment_entropy_final") or 9) < (homo_s.get("judgment_entropy_final") or 9):
            findings.append("- 投票前の判断は混合の方が集中している。R1-08（同質の方が早く強く収束）とは逆向き。")
        if (mixed_s.get("correction_rate") or 0) > (homo_s.get("correction_rate") or 0):
            findings.append("- 誤った初期判断の修正率は混合の方が高い。R1-09の方向と一致する。")
        elif (homo_s.get("correction_rate") or 0) > (mixed_s.get("correction_rate") or 0):
            findings.append("- 誤った初期判断の修正率は同質の方が高い。R1-09とは逆向き。")
        if (homo_s.get("vote_concentration") or 0) > (mixed_s.get("vote_concentration") or 0):
            findings.append("- 投票は同質の方が一点に集まりやすい。")
        else:
            findings.append("- 投票の集中は混合と同質で大きくは違わない、または混合の方が高い。")
    if not findings:
        findings.append("- 完了ケースが少ない、または差が小さいため、方向はまだ言い切れない。")
    if not pairs[2]:
        findings.append("- 17試合が揃ったTrialがないため、Trial単位のWilcoxonは出していない。")
    else:
        findings.append(
            "- 17試合が揃ったTrialは{0}件。村人正答（混合 vs 同質中央値）のWilcoxon p={1}（組数 {2}）。".format(
                len(pairs[2]),
                _fmt((wilcox or {}).get("p_two_sided")),
                (wilcox or {}).get("n") or 0,
            )
        )
    lines.extend(findings)
    lines.extend(
        [
            "",
            "R1-10（収束と正しさ）は、投票前の分散が低いケースほど村人正答が高いかを、ケース単位の相関で見る。",
            "",
            _convergence_correct_note(case_rows),
            "",
            "## RQ2：同質構成のタイプ別",
            "",
            "単位はケース。タイプあたりの試合数が少ない行は参考値。",
            "",
            md_table(
                (
                    "タイプ",
                    "試合数",
                    "村人勝率",
                    "人狼看破",
                    "投票集中",
                    "判断分散",
                    "修正率",
                    "確信度変化",
                ),
                type_rows,
            ),
            "",
            "## P1：発言ラベル（暫定・規則ベース）",
            "",
            "1発言に複数ラベル可。割合は「そのラベルが付いた発言 ÷ 発言数」。",
            "",
            md_table(("ラベル", "混合", "同質"), label_rows),
            "",
            md_table(
                ("議論上の状態", "混合", "同質"),
                [
                    [
                        name,
                        _pct(_rate(change_by_comp["mixed"].get(name, 0), sum(change_by_comp["mixed"].values()) or 0)),
                        _pct(
                            _rate(
                                change_by_comp["homogeneous"].get(name, 0),
                                sum(change_by_comp["homogeneous"].values()) or 0,
                            )
                        ),
                    ]
                    for name in ("new", "maintain", "change", "withdraw", "none")
                ],
            ),
            "",
            "自己の役職主張を、分析時だけ最終役職と突合した（ラベル付けには未使用）。",
            "突合できた自己役職主張: {0}件、事実と一致: {1}。".format(len(match_rows), _pct(claim_match)),
            "",
            "### P1で見えること",
            "",
            _p1_notes(label_by_comp, change_by_comp),
            "",
            "## 突合（分析時のみ）",
            "",
            "発言中の主張を、正解データと突き合わせた。意図的な嘘とは判定していない。",
            "",
            _match_table(speeches),
            "",
            "## M-01〜M-07（探索）",
            "",
            md_table(
                ("指標", "混合", "同質"),
                [
                    ["M-01 主導権（先に出した対象が後から続く）", _fmt(mixed_s.get("m01_leadership")), _fmt(homo_s.get("m01_leadership"))],
                    ["M-02 追随", _fmt(mixed_s.get("m02_follow")), _fmt(homo_s.get("m02_follow"))],
                    ["M-03 疑いの伝播（最多言及人数/8）", _fmt(mixed_s.get("m03_spread")), _fmt(homo_s.get("m03_spread"))],
                    ["M-04 疑い返し", _fmt(mixed_s.get("m04_counter")), _fmt(homo_s.get("m04_counter"))],
                    ["M-05 異議（rebut率）", _pct(mixed_s.get("m05_rebut")), _pct(homo_s.get("m05_rebut"))],
                    ["M-06 同意（agree率）", _pct(mixed_s.get("m06_agree")), _pct(homo_s.get("m06_agree"))],
                    ["M-07 少数意見の維持", _fmt(mixed_s.get("m07_minority")), _fmt(homo_s.get("m07_minority"))],
                ],
            ),
            "",
            "## Trial単位の検定（17試合揃い）",
            "",
            _wilcoxon_section(case_rows),
            "",
            _friedman_section(case_rows),
            "",
            "## 仮説の判定",
            "",
            _hypothesis_verdicts(mixed_s, homo_s, case_rows, speeches),
            "",
            "## ファイル",
            "",
            "- `case_metrics.csv` … ケース単位のP0 / M指標",
            "- `player_metrics.csv` … プレイヤー単位",
            "- `speeches.csv` … 全発言・ラベル・突合",
            "- `summary_by_composition.csv` … 混合・同質の要約",
            "- `summary_by_type.csv` … 同質タイプ別の要約",
            "",
            "## 再実行",
            "",
            "`python playgrounds/mbti-werewolf/scripts/run_judges_then_verify.py`",
            "Judge未了のケースは、同じコマンドで続きから評価する。",
            "",
        ]
    )
    return "\n".join(lines) + "\n"


def _match_table(speeches: Sequence[Dict[str, Any]]) -> str:
    keys = (
        ("self_role_vs_final", "自己役職 ↔ 最終役職"),
        ("self_role_vs_initial", "自己役職 ↔ 開始役職"),
        ("other_role_vs_final", "他者役職 ↔ 最終役職"),
        ("night_info_vs_claim", "夜の情報 ↔ 発言"),
        ("vs_pre_suspect", "言及先 ↔ 議論前判断"),
        ("vs_final_suspect", "言及先 ↔ 投票前判断"),
        ("vs_actual_vote", "言及先 ↔ 実際の投票"),
        ("vs_executed", "言及先 ↔ 追放者"),
        ("vs_winner", "勝敗の言及 ↔ 結果"),
    )
    rows = []
    for key, label in keys:
        judged = [s[key] for s in speeches if s.get(key) in ("match", "mismatch")]
        match_n = sum(1 for v in judged if v == "match")
        rows.append([label, len(judged), _pct(_rate(match_n, len(judged)))])
    return md_table(("突合", "判定できた発言", "一致率"), rows)


def _wilcoxon_section(case_rows: Sequence[Dict[str, Any]]) -> str:
    names = {
        "village_correct": "R1-02 人狼看破",
        "village_win": "R1-03 村人勝率",
        "judgment_entropy_final": "R1-04 判断分散",
        "final_entropy": "R1-04 疑念分散（Judge）",
        "vote_concentration": "R1-05 投票集中",
        "suspect_change_rate": "R1-06 判断変更",
        "mean_confidence_delta": "R1-07 確信度変化",
        "correction_rate": "R1-09 初期判断の修正",
        "convergence_round": "R1-08 収束ラウンド（Judge）",
        "village_vote_accuracy": "村人投票正答",
    }
    rows = []
    for key, label in names.items():
        left, right, used = trial_pairs(case_rows, key)
        stat = wilcoxon_signed_rank(left, right)
        rows.append([label, len(used), stat.get("n") or 0, _fmt(stat.get("p_two_sided")), _fmt(stat.get("r"))])
    return (
        "単位はTrial。混合1試合 vs 同質16試合の中央値。Wilcoxon符号付順位検定（両側）。\n\n"
        + md_table(("指標", "揃ったTrial", "差のある組", "p", "効果量 r"), rows)
    )


def _friedman_section(case_rows: Sequence[Dict[str, Any]]) -> str:
    result = friedman_by_type(case_rows, "village_correct")
    return (
        "RQ2: 同質16タイプの村人正答についてFriedman検定。"
        " 有効行 {0} / タイプ {1} / p={2}。".format(
            result.get("n"), result.get("k"), _fmt(result.get("p"))
        )
    )


def _hypothesis_verdicts(
    mixed_s: Dict[str, Any],
    homo_s: Dict[str, Any],
    case_rows: Sequence[Dict[str, Any]],
    speeches: Sequence[Dict[str, Any]],
) -> str:
    def direction(mixed_v, homo_v, expect_mixed_higher: bool) -> str:
        if mixed_v is None or homo_v is None:
            return "判定不能"
        if abs(mixed_v - homo_v) < 1e-9:
            return "差なし"
        mixed_higher = mixed_v > homo_v
        return "仮説の方向と一致" if mixed_higher == expect_mixed_higher else "仮説と逆"

    left, right, _used = trial_pairs(case_rows, "village_correct")
    p_val = wilcoxon_signed_rank(left, right).get("p_two_sided")
    judge_share = _pct(_rate(sum(1 for s in speeches if s.get("label_source") == "judge"), len(speeches) or 1))
    rows = [
        ["R1-02 構成で看破率が違う", direction(mixed_s.get("village_correct_rate"), homo_s.get("village_correct_rate"), False), "記述: 同質の方が高い。検定p={0}".format(_fmt(p_val))],
        ["R1-03 構成で村人勝率が違う", direction(mixed_s.get("village_win_rate"), homo_s.get("village_win_rate"), False), "記述: 同質の方が高い"],
        ["R1-04 構成で収束・分散が違う", direction(mixed_s.get("judgment_entropy_final"), homo_s.get("judgment_entropy_final"), True), "判断分布の代用。Judge列は別途"],
        ["R1-05 構成で投票集中が違う", direction(mixed_s.get("vote_concentration"), homo_s.get("vote_concentration"), True), "混合の方が集中"],
        ["R1-06 構成で判断変更が違う", direction(mixed_s.get("suspect_change_rate"), homo_s.get("suspect_change_rate"), True), "混合の変更率が高い"],
        ["R1-07 構成で確信度変化が違う", direction(mixed_s.get("mean_confidence_delta"), homo_s.get("mean_confidence_delta"), True), "混合の上昇が大きい"],
        ["R1-08 同質の方が強く収束", direction(homo_s.get("judgment_entropy_final"), mixed_s.get("judgment_entropy_final"), False), "同質の分散が低いなら支持。今回は混合の方が集中"],
        ["R1-09 混合の方が修正する", direction(mixed_s.get("correction_rate"), homo_s.get("correction_rate"), True), "今回は同質の修正率が高い"],
        ["R1-10 収束と正しさの関係が構成で違う", "探索", _convergence_correct_note(case_rows)],
        ["R1-01 / R2-01 意思決定プロセス", "探索", "ラベルLLM比率 {0}。M指標は下表".format(judge_share)],
        ["M-01〜M-07", "探索", "確定判断には使わない"],
    ]
    return md_table(("仮説", "判定", "メモ"), rows)


def _convergence_correct_note(rows: Sequence[Dict[str, Any]]) -> str:
    points = [
        (r["judgment_entropy_final"], r["village_correct"])
        for r in rows
        if r.get("judgment_entropy_final") is not None and r.get("village_correct") is not None
    ]
    if len(points) < 8:
        return "相関を出すにはケースが足りない。"
    mixed_pts = [
        (r["judgment_entropy_final"], r["village_correct"])
        for r in rows
        if r["composition"] == "mixed"
        and r.get("judgment_entropy_final") is not None
        and r.get("village_correct") is not None
    ]
    homo_pts = [
        (r["judgment_entropy_final"], r["village_correct"])
        for r in rows
        if r["composition"] == "homogeneous"
        and r.get("judgment_entropy_final") is not None
        and r.get("village_correct") is not None
    ]

    def corr(pts: List[Tuple[float, float]]) -> Optional[float]:
        if len(pts) < 8:
            return None
        xs = [p[0] for p in pts]
        ys = [float(p[1]) for p in pts]
        if statistics.pstdev(xs) == 0 or statistics.pstdev(ys) == 0:
            return None
        mean_x = sum(xs) / len(xs)
        mean_y = sum(ys) / len(ys)
        num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
        den = (
            sum((x - mean_x) ** 2 for x in xs) ** 0.5
            * sum((y - mean_y) ** 2 for y in ys) ** 0.5
        )
        if den == 0:
            return None
        return round(num / den, 4)

    cm = corr(mixed_pts)
    ch = corr(homo_pts)
    return (
        "投票前の判断分散と村人正答の相関（負なら「集中するほど当たる」）: "
        "混合 {0} / 同質 {1}。".format(_fmt(cm), _fmt(ch))
    )


def _p1_notes(label_by_comp: Dict[str, Counter], change_by_comp: Dict[str, Counter]) -> str:
    notes = []
    for name in ("suspect", "agree", "rebut", "question"):
        mixed_n = label_by_comp.get("mixed", Counter()).get("_n") or 0
        homo_n = label_by_comp.get("homogeneous", Counter()).get("_n") or 0
        mixed_r = _rate(label_by_comp.get("mixed", Counter()).get(name, 0), mixed_n)
        homo_r = _rate(label_by_comp.get("homogeneous", Counter()).get(name, 0), homo_n)
        if mixed_r is None or homo_r is None:
            continue
        if abs(mixed_r - homo_r) >= 0.05:
            side = "混合" if mixed_r > homo_r else "同質"
            notes.append(
                "- `{0}` は{1}の発言に多い（混合 {2} / 同質 {3}）。".format(
                    name, side, _pct(mixed_r), _pct(homo_r)
                )
            )
    mixed_change = _rate(
        change_by_comp.get("mixed", Counter()).get("change", 0),
        sum(change_by_comp.get("mixed", Counter()).values()) or 0,
    )
    homo_change = _rate(
        change_by_comp.get("homogeneous", Counter()).get("change", 0),
        sum(change_by_comp.get("homogeneous", Counter()).values()) or 0,
    )
    if mixed_change is not None and homo_change is not None:
        notes.append(
            "- 疑い先の変更 (`change`) は混合 {0} / 同質 {1}。".format(
                _pct(mixed_change), _pct(homo_change)
            )
        )
    if not notes:
        notes.append("- 構成によるラベル差は、この暫定規則では5ポイント以上開いていない。")
    notes.append("- これは探索用の仮ラベルである。P1仮説の確定判断には使わない。")
    return "\n".join(notes)


def coverage_table(runs_dir: Path, case_rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    by_exp = defaultdict(lambda: {"done": 0, "mixed": 0, "homo": 0})
    for row in case_rows:
        item = by_exp[row["experiment_id"]]
        item["done"] += 1
        if row["composition"] == "mixed":
            item["mixed"] += 1
        else:
            item["homo"] += 1
    experiment_rows = []
    for exp_dir in sorted(p for p in runs_dir.iterdir() if p.is_dir() and p.name.startswith("e-")):
        status = {}
        status_path = exp_dir / "status.json"
        if status_path.is_file():
            try:
                status = json.loads(status_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                status = {}
        item = by_exp.get(exp_dir.name, {"done": 0, "mixed": 0, "homo": 0})
        experiment_rows.append(
            (
                exp_dir.name,
                item["done"],
                item["mixed"],
                item["homo"],
                status.get("status") or "unknown",
            )
        )
    return {"experiments": len(experiment_rows), "experiment_rows": experiment_rows}


def main() -> int:
    parser = argparse.ArgumentParser(description="既存実験のP0/P1分析")
    parser.add_argument(
        "--runs-dir",
        type=Path,
        default=ROOT.parents[1] / "runs",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT.parents[1] / "docs" / "submission" / "labeling-analysis",
    )
    args = parser.parse_args()
    runs_dir = args.runs_dir.resolve()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)

    loaded = load_done_cases(runs_dir)
    case_rows: List[Dict[str, Any]] = []
    player_rows: List[Dict[str, Any]] = []
    speeches: List[Dict[str, Any]] = []
    for log, judge in loaded:
        row = enrich_case(log, judge)
        case_speeches = label_speeches(log, judge)
        row.update(process_metrics(case_speeches, log))
        case_rows.append(row)
        speeches.extend(case_speeches)
        for prow in player_metrics(log):
            prow = dict(prow)
            prow["experiment_id"] = log["experiment_id"]
            prow["trial_id"] = log["trial_id"]
            prow["case_id"] = log["case_id"]
            prow["composition"] = log.get("composition")
            prow["homogeneous_type"] = log.get("homogeneous_type") or ""
            player_rows.append(prow)

    generated_at = _now()
    coverage = coverage_table(runs_dir, case_rows)
    summary_comp = summarize_by(case_rows, "composition")
    summary_type = summarize_by(
        [r for r in case_rows if r["composition"] == "homogeneous"],
        "homogeneous_type",
    )

    case_fields = [
        "experiment_id",
        "trial_id",
        "case_id",
        "composition",
        "homogeneous_type",
        "winner",
        "village_win",
        "werewolf_win",
        "village_correct",
        "village_vote_accuracy",
        "vote_concentration",
        "judgment_entropy_pre",
        "judgment_entropy_final",
        "judgment_entropy_delta",
        "suspect_change_rate",
        "correction_rate",
        "deterioration_rate",
        "mean_confidence_delta",
        "rounds",
        "stop_reason",
        "pass_rate",
        "speech_count_gini",
        "total_speeches",
        "status",
        "has_judge",
        "final_entropy",
        "convergence_round",
        "m01_leadership",
        "m02_follow",
        "m03_spread",
        "m04_counter",
        "m05_rebut",
        "m06_agree",
        "m07_minority",
    ]
    player_fields = [
        "experiment_id",
        "trial_id",
        "case_id",
        "composition",
        "homogeneous_type",
        "player_id",
        "person_id",
        "mbti",
        "final_role",
        "pre_suspect",
        "final_suspect",
        "pre_confidence",
        "final_confidence",
        "suspect_changed",
        "confidence_delta",
        "pre_correct",
        "final_correct",
        "vote_correct",
        "corrected",
        "deteriorated",
        "win",
    ]
    speech_fields = [
        "experiment_id",
        "trial_id",
        "case_id",
        "composition",
        "homogeneous_type",
        "speech_id",
        "order",
        "round",
        "player_id",
        "person_id",
        "mbti",
        "speech_text",
        "labels",
        "mentions",
        "stances",
        "change_type",
        "evidence_basis",
        "claim_type",
        "claim_content",
        "label_source",
        "self_role_vs_initial",
        "self_role_vs_final",
        "other_role_vs_final",
        "night_info_vs_claim",
        "vs_pre_suspect",
        "vs_final_suspect",
        "vs_actual_vote",
        "vs_executed",
        "vs_winner",
    ]

    write_csv(out / "case_metrics.csv", case_rows, case_fields)
    write_csv(out / "player_metrics.csv", player_rows, player_fields)
    write_csv(out / "speeches.csv", speeches, speech_fields)
    write_csv(out / "summary_by_composition.csv", summary_comp, [
        "composition",
        "n_cases",
        "village_win_rate",
        "werewolf_win_rate",
        "village_correct_rate",
        "village_vote_accuracy",
        "vote_concentration",
        "judgment_entropy_pre",
        "judgment_entropy_final",
        "judgment_entropy_delta",
        "suspect_change_rate",
        "correction_rate",
        "deterioration_rate",
        "mean_confidence_delta",
        "mean_rounds",
        "pass_rate",
        "speech_count_gini",
    ])
    write_csv(out / "summary_by_type.csv", summary_type, [
        "homogeneous_type",
        "n_cases",
        "village_win_rate",
        "village_correct_rate",
        "village_vote_accuracy",
        "vote_concentration",
        "judgment_entropy_final",
        "correction_rate",
        "deterioration_rate",
        "mean_confidence_delta",
    ])

    markdown = render_markdown(generated_at, case_rows, speeches, coverage)
    (out / "README.md").write_text(markdown, encoding="utf-8")
    summary_path = out.parent / "labeling-analysis-result.md"
    summary_path.write_text(markdown, encoding="utf-8")

    print("完了ケース: {0}".format(len(case_rows)))
    print("発言: {0}".format(len(speeches)))
    print("出力: {0}".format(out))
    print("まとめ: {0}".format(summary_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
