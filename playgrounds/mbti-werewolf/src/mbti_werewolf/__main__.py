"""コマンドの入口（設計書8.1）。

    python -m mbti_werewolf experiment              1 Trial（17ケース）を実行する
    python -m mbti_werewolf experiment --trials 5 --brain ollama --model gemma3:4b
    python -m mbti_werewolf experiment --resume e-20260901-210000    止まった実験を続ける
    python -m mbti_werewolf experiment --cases c00 --brain ollama    1ケースだけ実測する
    python -m mbti_werewolf analyze --experiment e-20260901-210000    分析出力だけを作る
    python -m mbti_werewolf masterdata              人物プールとパターンを生成する
    python -m mbti_werewolf pages                   GitHub Pages用の静的サイトを生成する

長時間・多試合の実行は画面を経由しないこの経路で行う。ブラウザやスリープの影響を
受けず、nohup などでシェルから切り離せるためである（要件IF-07、F-23）。

v1の4人版の `run` と操作画面の `ui` はM3で削除した。`ui` はM6でv2.0向けに作り直す
（設計書0.4、11章）。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m mbti_werewolf",
        description="MBTI人狼シミュレーター（AI先行テスト用）",
    )
    sub = parser.add_subparsers(dest="command")

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
    experiment.add_argument(
        "--judge-brain",
        choices=("stub", "ollama", "gemini"),
        help="Judgeの推論手段（既定は --brain と同じ）",
    )
    experiment.add_argument("--judge-model", help="Judgeのモデル名（既定は --model と同じ）")
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

    judge_cmd = sub.add_parser(
        "judge", help="実行済みの実験の発言を事後評価する（ゲームは再実行しない）"
    )
    judge_cmd.add_argument(
        "--experiment", required=True, metavar="EXPERIMENT_ID", help="評価する実験"
    )
    judge_cmd.add_argument("--config", type=Path, help="設定ファイル（既定値を上書きする）")
    judge_cmd.add_argument(
        "--judge-brain", choices=("stub", "ollama", "gemini"), help="Judgeの推論手段"
    )
    judge_cmd.add_argument("--judge-model", help="Judgeのモデル名（例: gemma3:4b）")
    judge_cmd.add_argument("--criteria", help="評価基準の版（既定はv1）")
    judge_cmd.add_argument("--batch-size", type=int, help="1回に評価する発言数（既定8）")
    judge_cmd.add_argument("--runs-dir", type=Path, help="読み取る runs/（既定はリポジトリの runs/）")
    judge_cmd.add_argument(
        "--force",
        action="store_true",
        help="同じ版の評価があるケースも評価し直す（既定は評価のないケースだけ）",
    )

    analyze_cmd = sub.add_parser(
        "analyze", help="実行済みの実験から分析出力を作る（推論は呼ばない）"
    )
    analyze_cmd.add_argument(
        "--experiment", required=True, metavar="EXPERIMENT_ID", help="分析する実験"
    )
    analyze_cmd.add_argument("--runs-dir", type=Path, help="読み取る runs/（既定はリポジトリの runs/）")
    analyze_cmd.add_argument(
        "--criteria", help="読み取るJudge評価の版（既定はv1）"
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

    if args.command == "experiment":
        return command_experiment(args)
    if args.command == "judge":
        return command_judge(args)
    if args.command == "analyze":
        return command_analyze(args)
    if args.command == "masterdata":
        return command_masterdata(args)
    if args.command == "pages":
        return command_pages(args)

    parser.print_help()
    return 1


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
    per_call = summary.get("seconds_per_call")
    if per_call is not None:
        print(
            "1呼び出しあたり: {}秒（設計書1.3の試算は約10.6秒）".format(per_call)
        )
    directory = Path(summary["directory"])
    print("保存先: {}".format(directory))
    print("集計:   {}".format(directory / "experiment_metrics.csv"))
    print("実測:   {}".format(directory / "timing.md"))
    print("-" * 60)
    print("最新結果へのリンク: {}".format(runs_dir / "latest.html"))
    print("公開URL（最新）: https://ziriss8120121.github.io/hackathon-test/runs/latest.html")
    print("URLへ反映するには、runs/ を commit して main へ push する。")
    return 0 if summary["failed_count"] == 0 else 1


def _run_resume(runner, experiment_id: str) -> int:
    from .runner import ResumeError

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
    from .config import ConfigError, load_config
    from .runner import DEFAULT_CASE_ATTEMPTS, ExperimentRunner

    try:
        config = load_config(path=args.config, overrides=_experiment_overrides(args))
    except (ConfigError, ValueError) as exc:
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
        _print_brain_probe(config)
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

    _print_brain_probe(config)

    try:
        summary = runner.run()
    except (
        experiment_module.ConditionFixationError,
        experiment_module.ExperimentError,
    ) as exc:
        print("生成エラー: {}".format(exc), file=sys.stderr)
        return 1

    return _print_experiment_result(summary, runner.runs_dir)


def command_judge(args: argparse.Namespace) -> int:
    from .brains.factory import create_case_brain
    from .config import ConfigError, load_config
    from .judge.judge import Criteria, ExperimentJudge, JudgeError
    from .runner import default_runs_dir

    overrides: Dict[str, Any] = {
        "judge_brain": {"provider": args.judge_brain, "model": args.judge_model},
        "judge_criteria_version": args.criteria,
        "judge_batch_size": args.batch_size,
    }
    try:
        config = load_config(path=args.config, overrides=overrides)
        criteria = Criteria(config.judge_criteria_version)
    except (ConfigError, JudgeError, ValueError, OSError, KeyError) as exc:
        print("設定エラー: {}".format(exc), file=sys.stderr)
        return 2

    runs_dir = args.runs_dir or default_runs_dir()
    judge = ExperimentJudge(
        runs_dir=runs_dir,
        # ケースごとに脳を作り直す。Stubは呼び出し順で出力が決まるため、ケース間で
        # 状態を共有すると評価がケースの実行順に依存する。
        brain_factory=lambda: create_case_brain(
            config, seed=config.base_seed, judge=True
        ),
        criteria=criteria,
        batch_size=config.judge_batch_size,
        on_progress=print,
    )

    print(
        "評価: {} / 基準 {} / 脳={}{} / バッチ{}件".format(
            args.experiment,
            criteria.version,
            config.judge_brain.provider,
            "（{}）".format(config.judge_brain.model) if config.judge_brain.model else "",
            config.judge_batch_size,
        )
    )
    print("-" * 60)
    _print_brain_probe(config, judge=True)

    try:
        summary = judge.run(args.experiment, force=args.force)
    except JudgeError as exc:
        print("評価エラー: {}".format(exc), file=sys.stderr)
        return 2

    print("-" * 60)
    parts = ["評価 {}".format(summary["done_count"]), "失敗 {}".format(summary["failed_count"])]
    if summary["skipped_count"]:
        parts.append("評価済み {}".format(summary["skipped_count"]))
    print(
        "結果: {}（呼び出し{}回、合計{}秒）".format(
            " / ".join(parts), summary["inference_calls"], summary["elapsed_seconds"]
        )
    )
    calls = summary.get("inference_calls") or 0
    elapsed = summary.get("elapsed_seconds") or 0.0
    if calls:
        print(
            "1呼び出しあたり: {:.3f}秒（設計書1.3の試算は約10.6秒）".format(
                float(elapsed) / calls
            )
        )
    print("保存先: {}".format(Path(summary["directory"])))
    for failure in summary["failures"]:
        print("  失敗 {}: {}".format(failure["case"], failure["message"]), file=sys.stderr)
    return 0 if summary["failed_count"] == 0 else 1


def command_analyze(args: argparse.Namespace) -> int:
    from .analysis.analyzer import AnalyzeError, Analyzer
    from .runner import default_runs_dir

    runs_dir = args.runs_dir or default_runs_dir()
    analyzer = Analyzer(
        runs_dir=runs_dir,
        criteria_version=args.criteria or "v1",
        on_progress=print,
    )
    print("分析: {}".format(args.experiment))
    print("-" * 60)
    try:
        summary = analyzer.run(args.experiment)
    except AnalyzeError as exc:
        print("分析エラー: {}".format(exc), file=sys.stderr)
        return 2

    print("-" * 60)
    print(
        "結果: 有効Trial {0} / 除外 {1} / 発言ラベル {2}行".format(
            summary["eligible_count"],
            summary["excluded_count"],
            summary["speech_label_rows"],
        )
    )
    print("保存先: {}".format(summary["directory"]))
    print("最新結果へのリンク: {}".format(runs_dir / "latest.html"))
    return 0


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
    from .record.pages import build_pages

    dest = build_pages(runs_dir=args.runs_dir, output_dir=args.out)
    print("GitHub Pages用サイト: {}".format(dest))
    print("一覧: {}".format(dest / "index.html"))
    return 0


def _experiment_overrides(args: argparse.Namespace) -> Dict[str, Any]:
    overrides: Dict[str, Any] = {
        "trial_count": args.trials,
        "base_seed": args.seed,
        "machine_name": args.machine,
        "brain": {"provider": args.brain, "model": args.model},
        # Judgeを別指定しなければエージェントと同じ経路にする。実測は両方を同じ
        # モデルで回すことが多く、毎回2つ指定させる形にすると取り違えが起きる。
        "judge_brain": {
            "provider": args.judge_brain or args.brain,
            "model": args.judge_model or args.model,
        },
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


def _print_brain_probe(config, judge: bool = False) -> None:
    """実Brainの接続を実行前に確認する。失敗しても止めない（設計書3.5）。"""

    from .brains.factory import probe_brain

    provider = config.judge_brain.provider if judge else config.brain.provider
    if provider == "stub":
        return
    try:
        result = probe_brain(config, seed=config.base_seed, judge=judge)
    except Exception as exc:  # noqa: BLE001 - 確認の失敗で実験を止めない
        print("接続確認: 失敗（{}）".format(exc), file=sys.stderr)
        return
    if not result:
        return
    line = "接続確認: {}".format(result.get("message") or "")
    if result.get("ok"):
        print(line)
    else:
        print(line, file=sys.stderr)
        print("このまま実行します。ケースは失敗として記録されます。", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
