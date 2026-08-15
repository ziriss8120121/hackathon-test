"""コマンドの入口（設計書8.1）。

    python -m mbti_werewolf ui                      操作画面を開く
    python -m mbti_werewolf run                     1試合を実行する
    python -m mbti_werewolf run --games 100 --seed 42
    python -m mbti_werewolf run --brain stub        脳を切り替える

長時間・多試合の実行は画面を経由しないこの経路で行う。ブラウザやスリープの影響を
受けず、nohup などでシェルから切り離せるためである（要件IF-07、F-23）。
"""

from __future__ import annotations

import argparse
import sys
import threading
import webbrowser
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import ConfigError, load_config
from .runner import Runner


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m mbti_werewolf",
        description="MBTI人狼シミュレーター（AI先行テスト用）",
    )
    sub = parser.add_subparsers(dest="command")

    ui = sub.add_parser("ui", help="操作画面を起動する")
    ui.add_argument("--host", default="127.0.0.1")
    ui.add_argument("--port", type=int, default=8765)
    ui.add_argument("--no-browser", action="store_true", help="ブラウザを自動で開かない")

    run = sub.add_parser("run", help="試合を実行する")
    run.add_argument("--config", type=Path, help="設定ファイル（既定値を上書きする）")
    run.add_argument("--games", type=int, help="試合回数")
    run.add_argument("--seed", type=int, help="乱数のseed（base_seed）")
    run.add_argument("--players", type=int, help="参加人数")
    run.add_argument("--turns", type=int, help="議論のターン数")
    run.add_argument("--werewolves", type=int, help="人狼の人数")
    run.add_argument(
        "--functions", help="心理機能をカンマ区切りで指定する（例: Ne,Ti,Fe,Si）"
    )
    run.add_argument(
        "--brain", choices=("stub", "ollama", "gemini"), help="推論手段を選ぶ"
    )
    run.add_argument("--model", help="モデル名（例: gemma3:4b）")
    run.add_argument("--max-output-chars", type=int, help="発言の文字数上限")
    run.add_argument("--machine", help="実行環境の識別名（既定はホスト名）")
    run.add_argument("--runs-dir", type=Path, help="出力先（既定はリポジトリの runs/）")

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "ui":
        return command_ui(args)
    if args.command == "run":
        return command_run(args)

    parser.print_help()
    return 1


def command_ui(args: argparse.Namespace) -> int:
    try:
        import uvicorn
    except ImportError:
        print(
            "uvicorn が入っていません。次を実行してください。\n"
            "  pip install -r requirements.txt",
            file=sys.stderr,
        )
        return 1

    from .web.app import create_app

    url = "http://{}:{}/".format(args.host, args.port)
    print("操作画面: {}".format(url))
    print("停止する場合は Ctrl+C を押してください。")

    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    uvicorn.run(create_app(), host=args.host, port=args.port, log_level="warning")
    return 0


def command_run(args: argparse.Namespace) -> int:
    try:
        config = load_config(path=args.config, overrides=_overrides(args))
    except ConfigError as exc:
        print("設定エラー: {}".format(exc), file=sys.stderr)
        return 2

    runner = Runner(args.runs_dir)
    series_id = runner.create_series(config)

    print("series_id: {}".format(series_id))
    print(
        "条件: {}人 / {}ターン / {}試合 / seed={} / 脳={}{}".format(
            config.player_count,
            config.turn_count,
            config.game_count,
            config.seed,
            config.brain.provider,
            "（{}）".format(config.brain.model) if config.brain.model else "",
        )
    )
    print("-" * 60)

    def report(entry: Dict[str, Any]) -> None:
        mark = "ok  " if entry["status"] == "done" else "fail"
        print(
            "[{}] {:>4}/{:<4} {} 勝者={} 処刑={} {}秒{}".format(
                mark,
                entry["run_index"],
                config.game_count,
                entry["run_id"],
                entry.get("winner") or "—",
                entry.get("executed") or "—",
                entry.get("elapsed_seconds"),
                "  種別={}".format(entry["error_kind"]) if entry.get("error_kind") else "",
            )
        )

    series = runner.execute_series(series_id, config, on_run_finished=report)

    series_path = runner.series_dir(series_id)
    print("-" * 60)
    print(
        "結果: 成功 {} / 失敗 {}（状態: {}、合計 {}秒、AI待機 {}秒）".format(
            series.get("success_count"),
            series.get("failure_count"),
            series.get("status"),
            series.get("elapsed_seconds"),
            series.get("ai_wait_seconds"),
        )
    )
    print("保存先: {}".format(series_path))
    print("集計:   {}".format(series_path / "series_summary.md"))
    if config.game_count == 1:
        print("結果:   {}".format(series_path / "r001" / "result.html"))
    print("-" * 60)
    print("最新結果へのリンク: {}".format(runner.runs_dir / "latest.html"))
    print(
        "スマホ確認用URL（GitHub Pages、未公開・設計書M6）: "
        "https://ziriss8120121.github.io/hackathon-test/runs/latest.html"
    )
    print(
        "上記URLは、リポジトリでGitHub Pagesを公開してから runs/ 配下を commit・push した場合にだけ反映されます"
        "（ローカル実行だけでは反映されません。Pages公開自体は人がSettingsで行う必要があります）。"
    )

    return 0 if series.get("status") == "done" else 1


def _overrides(args: argparse.Namespace) -> Dict[str, Any]:
    overrides: Dict[str, Any] = {
        "game_count": args.games,
        "seed": args.seed,
        "player_count": args.players,
        "turn_count": args.turns,
        "machine_name": args.machine,
        "brain": {
            "provider": args.brain,
            "model": args.model,
            "max_output_chars": args.max_output_chars,
        },
    }
    if args.functions:
        overrides["functions"] = [
            part.strip() for part in args.functions.replace("、", ",").split(",") if part.strip()
        ]
    if args.players or args.werewolves:
        # 人数を変えたら村人の数も合わせて作り直す。合計が人数と一致しないと
        # 設定検証で弾かれるため、片方だけの指定でも整合させる。
        base = load_config(path=args.config)
        players = args.players or base.player_count
        werewolves = args.werewolves or base.role_composition.get("werewolf", 1)
        overrides["role_composition"] = {
            "werewolf": werewolves,
            "villager": players - werewolves,
        }
    return {key: value for key, value in overrides.items() if value is not None}


if __name__ == "__main__":
    sys.exit(main())
