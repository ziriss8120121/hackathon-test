"""GitHub Pages用サイト（設計書7.6、M8）。

`analyze` が書いた実験HTMLも複写し、一覧の入口を実験単位にする。
"""

from __future__ import annotations

from mbti_werewolf.__main__ import main
from mbti_werewolf.analysis.analyzer import Analyzer


def test_pages_copies_analysis_html_and_lists_experiments(tmp_path, capsys):
    runs_dir = tmp_path / "runs"
    code = main(
        [
            "experiment",
            "--brain",
            "stub",
            "--cases",
            "c00",
            "--runs-dir",
            str(runs_dir),
        ]
    )
    assert code == 0
    exp_id = next(path.name for path in runs_dir.iterdir() if path.name.startswith("e-"))

    Analyzer(runs_dir=runs_dir).run(exp_id)

    out = tmp_path / "site"
    code = main(["pages", "--runs-dir", str(runs_dir), "--out", str(out)])
    captured = capsys.readouterr()

    assert code == 0
    assert (out / "runs" / exp_id / "experiment.html").is_file()
    assert (out / "runs" / exp_id / "rq1.html").is_file()
    assert (out / "runs" / exp_id / "rq2.html").is_file()
    assert (out / "runs" / exp_id / "t001" / "trial.html").is_file()
    assert list(out.glob("runs/*/t001/c00-mixed/result.html"))

    html = (out / "index.html").read_text(encoding="utf-8")
    assert "実験の分析" in html
    assert exp_id in html
    assert "runs/{0}/experiment.html".format(exp_id) in html
    assert "simulator.html" in html
    assert (out / "simulator.html").is_file()
    assert (out / "style.css").is_file()
    assert "push は人間が行う" in captured.out
