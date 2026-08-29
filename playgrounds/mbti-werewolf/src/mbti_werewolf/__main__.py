"""コマンドの入口（設計書8.1）。

    python -m mbti_werewolf ui                      操作画面を開く
    python -m mbti_werewolf run                     1試合を実行する（v1の4人版）
    python -m mbti_werewolf run --games 100 --seed 42
    python -m mbti_werewolf run --brain stub        脳を切り替える
    python -m mbti_werewolf experiment              1 Trial（17ケース）を実行する（v2.0）
    python -m mbti_werewolf experiment --trials 5 --brain ollama --model gemma3:4b
    python -m mbti_werewolf experiment --resume e-20260901-210000    止まった実験を続ける
    python -m mbti_werewolf experiment --cases c00 --brain ollama    1ケースだけ実測する
    python -m mbti_werewolf masterdata              人物プールとパターンを生成する（v2.0）
    python -m mbti_werewolf pages                   GitHub Pages用の静的サイトを生成する

長時間・多試合の実行は画面を経由しないこの経路で行う。ブラウザやスリープの影響を
受けず、nohup などでシェルから切り離せるためである（要件IF-07、F-23）。

`run` はv1の4人版、`experiment` はv2.0の8人ワンナイトである。M3でv2.0の出力が
揃った時点で `run` を削除する（設計書0.4）。
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

    experiment = sub.add_parser(
        "experiment", help="8人ワンナイトの実験を実行する（1 Trial = 17ケース）"
    )
    experiment.add_argument("--config", type=Path, help="設定ファイル（既定値を上書きする）")
    experiment.add_argument("--trials", type=int, help="Trial数（既定は1）")
    experiment.add_argument(
        "--trial-range", help="実行するTrialの範囲（例: 3-7）。分割実行に使う"
    )
    experiment.add_argument("--seed", type=int, help="base_seed")
    experiment.add_argument(
        "--brain", choices=("stub", "ollama", "gemini"), help="推論手段を選ぶ"
    )
    experiment.add_argument("--model", help="モデル名（例: gemma3:4b）")
    experiment.add_argument("--max-rounds", type=int, help="議論のラウンド上限")
    experiment.add_argument("--machine", help="実行環境の識別名")
    experiment.add_argument("--data-dir", type=Path, help="マスタデータの場所（既定は data/）")
    experiment.add_argument("--runs-dir", type=Path, help="出力先（既定はリポジトリの runs/）")
    experiment.add_argument(
        "--resume",
        metavar="EXPERIMENT_ID",
        help="止まった実験を続ける。完了済みのケースは実行しない",
    )
    experiment.add_argument(
        "--cases",
        help="実行するケースを絞る（例: c00 または c00,c05）。1ケースの実測に使う",
    )
    experiment.add_argument(
        "--case-attempts",
        type=int,
        help="1ケースあたりの実行回数の上限（既定2）。1回目が失敗したら作り直して試す",
    )
    experiment.add_argument(
        "--dry-run",
        action="store_true",
        help="ケースを実行せず、Trialと17ケースの生成と条件固定の検査だけを行う",
    )

    masterdata_cmd = sub.add_parser(
        "masterdata", help="人物プールとパターンセットを生成する"
    )
    masterdata_cmd.add_argument("--data-dir", type=Path, help="書き出し先（既定は data/）")
    masterdata_cmd.add_argument("--pool-seed", type=int, help="人物プールのseed（既定1001）")
    masterdata_cmd.add_argument("--pattern-seed", type=int, help="パターンのseed（既定2001）")
    masterdata_cmd.add_argument(
        "--patterns", type=int, default=100, help="生成するパターン数（既定100）"
    )

    pages = sub.add_parser("pages", help="GitHub Pages用の静的サイトを生成する")
    pages.add_argument("--runs-dir", type=Path, help="読み取る runs/（既定はリポジトリの runs/）")
    pages.add_argument("--out", type=Path, help="書き出し先（既定はリポジトリの site/）")

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "ui":
        return command_ui(args)
    if args.command == "run":
        return command_run(args)
    if args.command == "experiment":
        return command_experiment(args)
    if args.command == "masterdata":
        return command_masterdata(args)
    if args.command == "pages":
        return command_pages(args)

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
        "公開URL（一覧）: https://ziriss8120121.github.io/hackathon-test/"
    )
    print(
        "公開URL（最新）: https://ziriss8120121.github.io/hackathon-test/runs/latest.html"
    )
    print("URLへ反映するには、runs/ を commit して main へ push する。")

    return 0 if series.get("status") == "done" else 1


def _case_filter(value: Optional[str]) -> Optional[List[str]]:
    if not value:
        return None
    names = [part.strip() for part in value.split(",") if part.strip()]
    return names or None


def _print_experiment_result(summary: Dict[str, Any], runs_dir: Path) -> int:
    print("-" * 60)
    parts = [
        "完了 {}".format(summary["done_count"]),
        "失敗 {}".format(summary["failed_count"]),
        "無効試合 {}".format(summary["invalid_count"]),
    ]
    if summary["skipped_count"]:
        parts.append("実行せず {}".format(summary["skipped_count"]))
    print(
        "結果: {}（呼び出し{}回、合計{}秒）".format(
            " / ".join(parts), summary["inference_calls"], summary["elapsed_seconds"]
        )
    )
    directory = Path(summary["directory"])
    print("保存先: {}".format(directory))
    print("集計:   {}".format(directory / "experiment_metrics.csv"))
    print("-" * 60)
    print("最新結果へのリンク: {}".format(runs_dir / "latest.html"))
    print("公開URL（最新）: https://ziriss8120121.github.io/hackathon-test/runs/latest.html")
    print("URLへ反映するには、runs/ を commit して main へ push する。")
    return 0 if summary["failed_count"] == 0 else 1


def _run_resume(runner, experiment_id: str) -> int:
    from .experiment_runner import ResumeError

    print("再開: {}".format(experiment_id))
    print("-" * 60)
    try:
        summary = runner.resume(experiment_id)
    except ResumeError as exc:
        print("再開エラー: {}".format(exc), file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 - 復元の失敗は原因をそのまま見せる
        print("再開エラー: {}".format(exc), file=sys.stderr)
        return 1
    return _print_experiment_result(summary, runner.runs_dir)


def command_experiment(args: argparse.Namespace) -> int:
    from . import experiment as experiment_module
    from .experiment_config import ConfigError as ExperimentConfigError
    from .experiment_config import load_config as load_experiment_config
    from .experiment_runner import DEFAULT_CASE_ATTEMPTS, ExperimentRunner

    try:
        config = load_experiment_config(
            path=args.config, overrides=_experiment_overrides(args)
        )
    except (ExperimentConfigError, ValueError) as exc:
        print("設定エラー: {}".format(exc), file=sys.stderr)
        return 2

    runner = ExperimentRunner(
        config,
        data_dir=args.data_dir,
        runs_dir=args.runs_dir,
        on_progress=print,
        case_attempts=args.case_attempts or DEFAULT_CASE_ATTEMPTS,
        case_filter=_case_filter(args.cases),
    )

    try:
        pool, pattern_set, rule_set = runner.load_inputs()
    except Exception as exc:  # noqa: BLE001 - 入力データの不備は原因をそのまま見せる
        print("入力データのエラー: {}".format(exc), file=sys.stderr)
        return 2

    if args.resume:
        return _run_resume(runner, args.resume)

    trial_indices = config.trial_indices()
    print(
        "条件: Trial {}件（{}） / ルール {} / 脳={}{} / seed={}".format(
            len(trial_indices),
            "-".join([str(trial_indices[0]), str(trial_indices[-1])])
            if len(trial_indices) > 1
            else str(trial_indices[0]),
            rule_set.rule_set_id,
            config.brain.provider,
            "（{}）".format(config.brain.model) if config.brain.model else "",
            config.base_seed,
        )
    )
    print(
        "ケース数: {}件（1 Trialあたり{}件）".format(
            len(trial_indices) * experiment_module.CASES_PER_TRIAL,
            experiment_module.CASES_PER_TRIAL,
        )
    )
    print("-" * 60)

    if args.dry_run:
        try:
            plan = experiment_module.build_experiment(
                config, rule_set, pool, pattern_set
            )
        except (
            experiment_module.ConditionFixationError,
            experiment_module.ExperimentError,
        ) as exc:
            print("生成エラー: {}".format(exc), file=sys.stderr)
            return 1
        for trial in plan.trials:
            print(
                "{}: パターン{} / seed={} / ケース{}件 / 条件検査={} / 変動={}".format(
                    trial.trial_id,
                    trial.pattern_id,
                    trial.trial_seed,
                    len(trial.cases),
                    "通過" if trial.condition_check["passed"] else "失敗",
                    trial.condition_check["varying_keys"],
                )
            )
        print("-" * 60)
        print("ケースは実行していない（--dry-run）。")
        return 0

    try:
        summary = runner.run()
    except (
        experiment_module.ConditionFixationError,
        experiment_module.ExperimentError,
    ) as exc:
        print("生成エラー: {}".format(exc), file=sys.stderr)
        return 1

    return _print_experiment_result(summary, runner.runs_dir)


def command_masterdata(args: argparse.Namespace) -> int:
    from . import experiment as experiment_module
    from . import masterdata

    data_dir = args.data_dir or experiment_module.default_data_dir()

    pool = masterdata.build_person_pool(
        seed=args.pool_seed or masterdata.DEFAULT_POOL_SEED
    )
    pattern_set = masterdata.build_pattern_set(
        pool,
        pattern_count=args.patterns,
        seed=args.pattern_seed or masterdata.DEFAULT_PATTERN_SEED,
    )

    pool_path = Path(data_dir) / "persons" / "{}.json".format(pool.pool_id)
    pattern_path = Path(data_dir) / "patterns" / "{}.json".format(
        pattern_set.pattern_set_id
    )
    masterdata.write_json(pool_path, pool.to_dict())
    masterdata.write_json(pattern_path, pattern_set.to_dict())

    print("人物プール: {}（{}人 / seed={}）".format(pool_path, pool.count, pool.seed))
    print(
        "パターン: {}（{}件 / seed={}）".format(
            pattern_path, len(pattern_set.patterns), pattern_set.seed
        )
    )
    return 0


def command_pages(args: argparse.Namespace) -> int:
    from .config import project_root, runs_root
    from .record.pages import build_pages

    dest = build_pages(
        runs_dir=args.runs_dir or runs_root(),
        output_dir=args.out or (project_root() / "site"),
    )
    print("GitHub Pages用サイト: {}".format(dest))
    print("一覧: {}".format(dest / "index.html"))
    return 0


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


def _experiment_overrides(args: argparse.Namespace) -> Dict[str, Any]:
    overrides: Dict[str, Any] = {
        "trial_count": args.trials,
        "base_seed": args.seed,
        "machine_name": args.machine,
        "brain": {"provider": args.brain, "model": args.model},
        "judge_brain": {"provider": args.brain, "model": args.model},
    }
    if args.max_rounds:
        overrides["discussion"] = {"max_rounds": args.max_rounds}
    if args.trial_range:
        parts = args.trial_range.replace("〜", "-").split("-")
        if len(parts) != 2 or not all(p.strip().isdigit() for p in parts):
            raise ValueError(
                "--trial-range は 3-7 の形で指定する: {}".format(args.trial_range)
            )
        start, end = int(parts[0]), int(parts[1])
        overrides["trial_range"] = [start, end]
        # 範囲だけを指定した場合、trial_count が範囲の終端に足りないと検証で弾かれる。
        if not args.trials:
            overrides["trial_count"] = end
    return {key: value for key, value in overrides.items() if value is not None}


if __name__ == "__main__":
    sys.exit(main())
