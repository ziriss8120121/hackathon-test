"""指標の集計（設計書9章）。

確実に取る指標はコードで数える。推論を使わないため、同じログからは常に同じ値が出る。

できれば取る指標（要件4.4）はv1ではルールベースで数える。AIに分類させると判定が
揺れ、心理機能ごとの差を見たいという目的にノイズが混ざるためである。精度は追わない。
数値そのものではなく、機能間の相対差を見るための指標として扱う。

判定に使う語彙はこのモジュールの定数として置く。判定基準をコードの1か所に
固定しておくことで、試合間・実行間の比較が成立する。
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional

from ..agents.mbti_types import mbti_candidates_text

_PLAYER_ID_RE = re.compile(r"p\d+")
_SENTENCE_SPLIT_RE = re.compile(r"[。．.!?！？\n]+")

#: 疑いを表す語。他プレイヤーへの言及と同じ文に出たときに疑い1件として数える。
SUSPICION_WORDS = (
    "怪しい",
    "あやしい",
    "疑",
    "人狼だと思",
    "人狼では",
    "嘘",
    "矛盾",
    "違和感",
    "不自然",
    "信用できな",
    "ごまかし",
    "誘導",
)

#: 反論を表す逆接の接続表現。
REBUTTAL_WORDS = (
    "しかし",
    "ですが",
    "だが",
    "とはいえ",
    "一方で",
    "そうは思わない",
    "違います",
    "反論",
    "それは違",
    "納得できな",
    "受け入れられません",
)

#: 同意を表す語。
AGREEMENT_WORDS = (
    "同意",
    "賛成",
    "たしかに",
    "確かに",
    "そう思います",
    "わかります",
    "同じ意見",
    "納得できました",
    "その通り",
)

#: 推量を表す表現。仮説の数として数える。
HYPOTHESIS_WORDS = (
    "かもしれ",
    "可能性",
    "仮に",
    "おそらく",
    "だとすると",
    "推測",
    "仮説",
    "の線",
    "見立て",
    "気がします",
)

#: 質問を表す語尾。疑問符に加えてこれらも質問として数える。
QUESTION_WORDS = ("ですか", "でしょうか", "のですか", "ますか")


def split_sentences(text: str) -> List[str]:
    return [part.strip() for part in _SENTENCE_SPLIT_RE.split(text or "") if part.strip()]


def _contains_any(text: str, words: Iterable[str]) -> bool:
    return any(word in text for word in words)


def _count_sentences_with(sentences: Iterable[str], words: Iterable[str]) -> int:
    return sum(1 for sentence in sentences if _contains_any(sentence, words))


def _mentioned_ids(sentence: str, exclude: str) -> List[str]:
    return [
        found
        for found in dict.fromkeys(_PLAYER_ID_RE.findall(sentence.lower()))
        if found != exclude
    ]


def _count_questions(text: str) -> int:
    count = text.count("?") + text.count("？")
    for sentence in split_sentences(text):
        if _contains_any(sentence, QUESTION_WORDS):
            count += 1
    return count


def compute_metrics(
    players: List[Any],
    turns: List[Dict[str, Any]],
    votes: List[Dict[str, Any]],
    result: Optional[Dict[str, Any]] = None,
    elapsed_seconds: float = 0.0,
) -> Dict[str, Any]:
    """プレイヤーごとの指標を返す。"""
    winner = (result or {}).get("winner")
    vote_by_voter = {vote["voter"]: vote["target"] for vote in votes}

    speeches_by_player: Dict[str, List[str]] = {}
    for turn in turns:
        speeches_by_player.setdefault(turn["player_id"], []).append(
            turn.get("speech_text", "")
        )

    # 疑われ回数は他プレイヤーの発言を横断して数えるため、先に全体を走査する。
    suspected_by: Dict[str, int] = {}
    for speaker, texts in speeches_by_player.items():
        for text in texts:
            for sentence in split_sentences(text):
                if not _contains_any(sentence, SUSPICION_WORDS):
                    continue
                for target in _mentioned_ids(sentence, speaker):
                    suspected_by[target] = suspected_by.get(target, 0) + 1

    per_player: List[Dict[str, Any]] = []
    for player in players:
        pid = player.player_id
        texts = speeches_by_player.get(pid, [])
        joined = "\n".join(texts)
        sentences = split_sentences(joined)

        suspicion_count = sum(
            1
            for sentence in sentences
            if _contains_any(sentence, SUSPICION_WORDS)
            and _mentioned_ids(sentence, pid)
        )
        char_counts = [len(text) for text in texts]

        per_player.append(
            {
                "player_id": pid,
                "function": player.function,
                "mbti_types": mbti_candidates_text(player.function),
                "role": player.role,
                "speech_count": len(texts),
                "avg_chars": round(sum(char_counts) / len(char_counts), 1)
                if char_counts
                else 0.0,
                "final_vote": vote_by_voter.get(pid, ""),
                "win": None if winner is None else player.team == winner,
                "elapsed_seconds": round(elapsed_seconds, 3),
                "suspicion_count": suspicion_count,
                "suspected_by_count": suspected_by.get(pid, 0),
                "question_count": _count_questions(joined),
                "rebuttal_count": _count_sentences_with(sentences, REBUTTAL_WORDS),
                "agreement_count": _count_sentences_with(sentences, AGREEMENT_WORDS),
                "hypothesis_count": sum(
                    1 for sentence in sentences if _contains_any(sentence, HYPOTHESIS_WORDS)
                ),
                "parse_failed_count": sum(
                    1
                    for turn in turns
                    if turn["player_id"] == pid and turn.get("parse_failed")
                ),
            }
        )

    return {"per_player": per_player}


#: metrics.csv の列（設計書6.6）。要件4.3の必須列を先頭に置く。
CSV_COLUMNS = (
    "run_id",
    "series_id",
    "player_id",
    "function",
    "mbti_types",
    "role",
    "speech_count",
    "avg_chars",
    "final_vote",
    "win",
    "elapsed_seconds",
    "suspicion_count",
    "suspected_by_count",
    "question_count",
    "rebuttal_count",
    "agreement_count",
    "hypothesis_count",
)


def csv_rows(run_log: Dict[str, Any]) -> List[List[Any]]:
    rows: List[List[Any]] = []
    for entry in run_log.get("metrics", {}).get("per_player", []):
        row: List[Any] = []
        for column in CSV_COLUMNS:
            if column == "run_id":
                row.append(run_log.get("run_id", ""))
            elif column == "series_id":
                row.append(run_log.get("series_id", ""))
            elif column == "win":
                value = entry.get("win")
                row.append("" if value is None else ("true" if value else "false"))
            else:
                row.append(entry.get(column, ""))
        rows.append(row)
    return rows
