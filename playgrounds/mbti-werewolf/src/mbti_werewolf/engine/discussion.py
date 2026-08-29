"""自由議論のラウンド制御（設計書4.5／ルール文書v0.7 §2-5）。

ラウンドごとに全員へ順に発言機会を与え、各自が発言か見送りを選ぶ。問い合わせ順は
ラウンドごとに無作為に決める。順を固定しないのは、毎ラウンド同じ参加者が文脈のない
状態で最初に話すことを避けるためである。

問い合わせ順は `trial_seed` から導く。17ケースで同じ順になるため、MBTI構成以外の
条件が揃う（設計書3.1）。ケースごとに違う値を使うと、問い合わせ順という別の変数が
17ケースの間で動いてしまう。
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..agents.agent import CaseAgent, clip_memo, parse_bool
from .view import CaseSpeech, CaseViewBuilder

STOP_ALL_PASS = "all_pass"
STOP_MAX_ROUNDS = "max_rounds"
STOP_MAX_SPEECHES = "max_speeches"
STOP_MAX_TOTAL_CHARS = "max_total_chars"


@dataclass
class DiscussionResult:
    rounds: int
    stop_reason: str
    events: List[Dict[str, Any]] = field(default_factory=list)
    speeches: List[CaseSpeech] = field(default_factory=list)

    @property
    def total_speeches(self) -> int:
        return sum(1 for e in self.events if e["spoke"])

    @property
    def total_passes(self) -> int:
        return sum(1 for e in self.events if not e["spoke"] and not e["skipped"])

    @property
    def total_skips(self) -> int:
        return sum(1 for e in self.events if e["skipped"])

    @property
    def total_chars(self) -> int:
        return sum(e.get("chars", 0) for e in self.events if e["spoke"])

    @property
    def wait_seconds(self) -> float:
        return sum(e.get("wait_seconds", 0.0) for e in self.events)

    @property
    def inference_calls(self) -> int:
        return sum(e.get("attempts", 0) for e in self.events)


def poll_order(player_ids: List[str], trial_seed: int, round_no: int) -> List[str]:
    """そのラウンドの問い合わせ順。seedとラウンド番号から決める（再現性: NF-05）。"""

    order = list(player_ids)
    random.Random("{0}:{1}".format(trial_seed, round_no)).shuffle(order)
    return order


class DiscussionRunner:
    def __init__(
        self,
        players: List[Any],
        agents: Dict[str, CaseAgent],
        view_builder: CaseViewBuilder,
        discussion_config,
        case_id: str,
        trial_seed: int,
    ) -> None:
        self._players = players
        self._agents = agents
        self._views = view_builder
        self._limits = discussion_config
        self._case_id = case_id
        self._trial_seed = trial_seed

    def run(self) -> DiscussionResult:
        limits = self._limits
        speeches: List[CaseSpeech] = []
        events: List[Dict[str, Any]] = []
        consecutive: Dict[str, int] = {p.player_id: 0 for p in self._players}
        order_index = 0
        speech_index = 0
        total_chars = 0
        stop_reason = STOP_MAX_ROUNDS
        rounds_done = 0

        all_ids = [p.player_id for p in self._players]

        for round_no in range(1, limits.max_rounds + 1):
            rounds_done = round_no
            ordered = poll_order(all_ids, self._trial_seed, round_no)
            targets = [pid for pid in ordered if not self._excluded(pid, consecutive)]

            # 対象から外れた人は、そのラウンドで発言していないので連続は途切れる。
            # ここで戻さないと一度上限に達した人が二度と対象に戻らない。
            for pid in ordered:
                if pid not in targets:
                    consecutive[pid] = 0

            if not targets:
                # 全員が連続発言の上限に達したラウンド。誰にも問い合わせないが、
                # ラウンドは消費したものとして数える。ここで数えないと、上限を
                # 設けたことで議論ラウンド数が静かに減り、`max_rounds` と実際の
                # ラウンド数が食い違う。全員が上限に達したときに上限を解除して
                # 発言させると、連続発言の上限そのものが無意味になる。
                continue

            spoke_in_round = 0
            hit_limit: Optional[str] = None

            for position, player_id in enumerate(targets, start=1):
                agent = self._agents[player_id]
                view = self._views.build(player_id, speeches=speeches, round_no=round_no)
                attempt = agent.speak(view, round_no)
                order_index += 1

                event: Dict[str, Any] = {
                    "order": order_index,
                    "round": round_no,
                    "poll_position": position,
                    "player_id": player_id,
                    "attempts": attempt.attempts,
                    "wait_seconds": round(attempt.wait_seconds, 3),
                }

                if not attempt.ok:
                    # 3回とも無効。見送りではなくスキップとして記録する（設計書4.5）。
                    event.update(
                        {
                            "spoke": False,
                            "skipped": True,
                            "memo": "",
                            "parse_failed": True,
                        }
                    )
                    consecutive[player_id] = 0
                    events.append(event)
                    continue

                spoke = bool(parse_bool(attempt.data.get("speak")))
                memo = clip_memo(attempt.data.get("memo"))

                if not spoke:
                    event.update(
                        {
                            "spoke": False,
                            "skipped": False,
                            "memo": memo,
                            "parse_failed": False,
                        }
                    )
                    consecutive[player_id] = 0
                    events.append(event)
                    continue

                raw = " ".join(str(attempt.data.get("speech", "")).split())
                truncated = len(raw) > limits.max_speech_chars
                text = raw[: limits.max_speech_chars]

                speech_index += 1
                speeches.append(
                    CaseSpeech(
                        order=order_index, round=round_no, player_id=player_id, text=text
                    )
                )
                total_chars += len(text)
                spoke_in_round += 1
                consecutive[player_id] += 1

                event.update(
                    {
                        "speech_id": "{0}-s{1:03d}".format(self._case_id, speech_index),
                        "spoke": True,
                        "skipped": False,
                        "speech_text": text,
                        "memo": memo,
                        "chars": len(text),
                        "truncated": truncated,
                        "parse_failed": False,
                    }
                )
                events.append(event)

                if speech_index >= limits.max_speeches:
                    hit_limit = STOP_MAX_SPEECHES
                    break
                if total_chars >= limits.max_total_chars:
                    hit_limit = STOP_MAX_TOTAL_CHARS
                    break

            if hit_limit is not None:
                stop_reason = hit_limit
                break
            if limits.stop_on_all_pass and spoke_in_round == 0:
                stop_reason = STOP_ALL_PASS
                break
            stop_reason = STOP_MAX_ROUNDS

        return DiscussionResult(
            rounds=rounds_done,
            stop_reason=stop_reason,
            events=events,
            speeches=speeches,
        )

    def _excluded(self, player_id: str, consecutive: Dict[str, int]) -> bool:
        """連続発言の上限に達した人をそのラウンドの対象から外す（ルール文書v0.7 §2-5）。"""

        limit = self._limits.max_consecutive_speeches
        if limit is None:
            return False
        return consecutive.get(player_id, 0) >= limit
