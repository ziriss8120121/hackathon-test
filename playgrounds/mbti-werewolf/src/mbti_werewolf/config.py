"""設定の読み込みと検証（設計書6.3、8.2）。

設定の優先順位は後のものが前を上書きする。

    config/default.json → --config のファイル → コマンド引数 → 画面のフォーム入力

どの経路で実行しても、確定した設定は runs/{series_id}/{run_dir}/config.json に
同じ形で保存される（要件F-20、IF-06）。
"""

from __future__ import annotations

import json
import os
import socket
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .agents.functions import FUNCTION_CODES

SCHEMA_VERSION = "1"
PROMPT_VERSION = "v1"

PROVIDERS = ("stub", "ollama", "gemini")
ROLES = ("werewolf", "villager")

# 過去ログ参照（要件F-18、F-39）はWant要件のため未実装。
SUPPORTED_HISTORY_MODES = ("none",)

_PACKAGE_DIR = Path(__file__).resolve().parent
PLAYGROUND_DIR = _PACKAGE_DIR.parent.parent
DEFAULT_CONFIG_PATH = PLAYGROUND_DIR / "config" / "default.json"


class ConfigError(ValueError):
    """設定が要件を満たさない場合に送出する。"""


def project_root() -> Path:
    """リポジトリのルートを返す。"""
    for candidate in [PLAYGROUND_DIR, *PLAYGROUND_DIR.parents]:
        if (candidate / ".git").exists():
            return candidate
    return PLAYGROUND_DIR.parent.parent


def runs_root() -> Path:
    """実行結果の保存先を返す。

    出力先を移したい場合は環境変数 MBTI_WEREWOLF_RUNS_DIR で上書きする。
    テストは一時ディレクトリを指すためにこれを使う。
    """
    override = os.environ.get("MBTI_WEREWOLF_RUNS_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return project_root() / "runs"


def default_machine_name() -> str:
    """実行環境の識別名（要件F-36）。"""
    return os.environ.get("MBTI_WEREWOLF_MACHINE") or socket.gethostname()


@dataclass
class BrainConfig:
    """エージェントの脳の設定（設計書5.5）。"""

    provider: str = "stub"
    model: str = ""
    temperature: float = 0.8
    max_output_chars: int = 200
    timeout_seconds: int = 120
    max_retries: int = 3

    def to_dict(self) -> Dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "temperature": self.temperature,
            "max_output_chars": self.max_output_chars,
            "timeout_seconds": self.timeout_seconds,
            "max_retries": self.max_retries,
        }


@dataclass
class Config:
    """1回の実行（series）の実験条件。"""

    player_count: int = 4
    turn_count: int = 3
    game_count: int = 1
    functions: List[str] = field(default_factory=lambda: ["Ne", "Ti", "Fe", "Si"])
    role_assignment_mode: str = "seeded_random"
    role_composition: Dict[str, int] = field(
        default_factory=lambda: {"werewolf": 1, "villager": 3}
    )
    seed: int = 42
    base_seed: Optional[int] = None
    history_mode: str = "none"
    history_scope: Optional[str] = None
    brain: BrainConfig = field(default_factory=BrainConfig)
    machine_name: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "player_count": self.player_count,
            "turn_count": self.turn_count,
            "game_count": self.game_count,
            "functions": list(self.functions),
            "role_assignment_mode": self.role_assignment_mode,
            "role_composition": dict(self.role_composition),
            "seed": self.seed,
            "base_seed": self.seed if self.base_seed is None else self.base_seed,
            "history_mode": self.history_mode,
            "history_scope": self.history_scope,
            "brain": self.brain.to_dict(),
            "machine_name": self.machine_name,
        }

    def for_run(self, run_index: int) -> "Config":
        """試合ごとの設定を作る（設計書3.5）。

        seed は base_seed + run_index - 1 とする。1試合目は base_seed そのままに
        なるため、単発実行で指定したseedがそのまま使われる。同じ base_seed を
        指定すれば複数試合の並びごと再現できる（要件F-21、F-22）。
        """
        base = self.seed if self.base_seed is None else self.base_seed
        clone = Config(**{**self.__dict__, "brain": BrainConfig(**self.brain.__dict__)})
        clone.base_seed = base
        clone.seed = base + run_index - 1
        return clone

    def validate(self) -> "Config":
        if self.player_count < 3:
            raise ConfigError("player_count は3以上にしてください。")
        if self.turn_count < 1:
            raise ConfigError("turn_count は1以上にしてください。")
        if self.game_count < 1:
            raise ConfigError("game_count は1以上にしてください。")

        unknown = [f for f in self.functions if f not in FUNCTION_CODES]
        if unknown:
            raise ConfigError(
                "未知の心理機能です: {}。使えるのは {} です。".format(
                    ", ".join(unknown), ", ".join(FUNCTION_CODES)
                )
            )
        if len(self.functions) < self.player_count:
            raise ConfigError(
                "functions が {} 個しかありません。player_count（{}）以上を指定してください。".format(
                    len(self.functions), self.player_count
                )
            )

        unknown_roles = [r for r in self.role_composition if r not in ROLES]
        if unknown_roles:
            raise ConfigError(
                "未知の役職です: {}。使えるのは {} です。".format(
                    ", ".join(unknown_roles), ", ".join(ROLES)
                )
            )
        total = sum(self.role_composition.values())
        if total != self.player_count:
            raise ConfigError(
                "role_composition の合計（{}）が player_count（{}）と一致しません。".format(
                    total, self.player_count
                )
            )
        if self.role_composition.get("werewolf", 0) < 1:
            raise ConfigError("werewolf は1人以上にしてください。")
        if self.role_composition.get("werewolf", 0) >= self.player_count:
            raise ConfigError("werewolf が全員では勝敗が決まりません。")

        if self.role_assignment_mode != "seeded_random":
            raise ConfigError(
                "role_assignment_mode に使えるのは seeded_random です（設計書4.4）。"
            )
        if self.history_mode not in SUPPORTED_HISTORY_MODES:
            raise ConfigError(
                "history_mode に使えるのは {} です。過去ログ参照は未実装です（要件F-18はWant）。".format(
                    ", ".join(SUPPORTED_HISTORY_MODES)
                )
            )

        if self.brain.provider not in PROVIDERS:
            raise ConfigError(
                "未知の provider です: {}。使えるのは {} です。".format(
                    self.brain.provider, ", ".join(PROVIDERS)
                )
            )
        if not 0.0 <= self.brain.temperature <= 2.0:
            raise ConfigError("temperature は0.0以上2.0以下にしてください。")
        if self.brain.max_output_chars < 20:
            raise ConfigError("max_output_chars は20以上にしてください。")
        if self.brain.timeout_seconds < 1:
            raise ConfigError("timeout_seconds は1以上にしてください。")
        if self.brain.max_retries < 0:
            raise ConfigError("max_retries は0以上にしてください。")

        return self


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as fp:
            return json.load(fp)
    except FileNotFoundError:
        raise ConfigError("設定ファイルが見つかりません: {}".format(path))
    except json.JSONDecodeError as exc:
        raise ConfigError("設定ファイルのJSONが壊れています: {} ({})".format(path, exc))


def _merge(base: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    """brain だけは入れ子を保ったまま部分上書きする。"""
    merged = dict(base)
    for key, value in patch.items():
        if value is None and key in ("machine_name", "model"):
            continue
        if key == "brain" and isinstance(value, dict):
            merged["brain"] = {**base.get("brain", {}), **{
                k: v for k, v in value.items() if v is not None
            }}
        elif value is not None or key == "history_scope":
            merged[key] = value
    return merged


def from_dict(raw: Dict[str, Any]) -> Config:
    """辞書から Config を作る。未知のキーは弾く。"""
    known = {f for f in Config.__dataclass_fields__ if f != "brain"}
    unknown = set(raw) - known - {"brain"}
    if unknown:
        raise ConfigError("未知の設定項目です: {}".format(", ".join(sorted(unknown))))

    brain_raw = raw.get("brain") or {}
    unknown_brain = set(brain_raw) - set(BrainConfig.__dataclass_fields__)
    if unknown_brain:
        raise ConfigError(
            "未知の brain 設定です: {}".format(", ".join(sorted(unknown_brain)))
        )

    values = {k: v for k, v in raw.items() if k in known}
    config = Config(**values, brain=BrainConfig(**brain_raw))
    if not config.machine_name:
        config.machine_name = default_machine_name()
    return config


def load_config(
    path: Optional[Path] = None, overrides: Optional[Dict[str, Any]] = None
) -> Config:
    """既定値、設定ファイル、上書き値を統合して検証済みの Config を返す。"""
    raw = _read_json(DEFAULT_CONFIG_PATH) if DEFAULT_CONFIG_PATH.exists() else {}
    if path is not None:
        raw = _merge(raw, _read_json(Path(path)))
    if overrides:
        raw = _merge(raw, overrides)
    return from_dict(raw).validate()


def default_config_dict() -> Dict[str, Any]:
    """操作画面の初期値として返す既定設定（設計書7.4 GET /api/config/default）。"""
    return load_config().to_dict()
