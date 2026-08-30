"""操作画面のAPI（設計書7.4、8.3、10章 test_web_api）。

画面はファイルを読むだけなので、ここで確認するのは契約である。コマンドから実行した
結果が一覧に出ること、実行中の再要求が 409 になること、分析未生成が「未生成」で
返ることを確かめる。
"""

from __future__ import annotations

import threading
import time

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from mbti_werewolf.web.app import create_app


@pytest.fixture
def client(tmp_path, v2_data_dir):
    app = create_app(data_dir=v2_data_dir, runs_dir=tmp_path)
    return TestClient(app), tmp_path


def test_health_returns_ok(client):
    http, _runs = client
    response = http.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_default_config_comes_from_code(client):
    http, _runs = client
    response = http.get("/api/config/default")
    assert response.status_code == 200
    body = response.json()
    assert body["brain"]["provider"] == "stub"
    assert body["trial_count"] == 1
    assert body["discussion"]["max_rounds"] == 6


def test_masterdata_lists_are_readable(client):
    http, _runs = client
    pools = http.get("/api/data/pools").json()
    rules = http.get("/api/data/rules").json()
    patterns = http.get("/api/data/patterns").json()
    assert pools[0]["pool_id"] == "pool-001"
    assert pools[0]["count"] == 100
    assert rules[0]["rule_set_id"] == "onenight-8p-v0.7"
    assert patterns[0]["pattern_set_id"] == "pattern-set-001"


def test_start_experiment_returns_202_and_appears_in_the_list(client):
    http, runs_dir = client
    response = http.post(
        "/api/experiments",
        json={"brain": {"provider": "stub"}, "cases": "c00"},
    )
    assert response.status_code == 202
    experiment_id = response.json()["experiment_id"]
    assert experiment_id.startswith("e-")

    listed = http.get("/api/experiments").json()
    assert listed[0]["experiment_id"] == experiment_id

    deadline = time.time() + 20
    log_path = None
    while time.time() < deadline:
        trials = http.get("/api/experiments/{}/trials".format(experiment_id)).json()
        if trials and any(case.get("status") == "done" for trial in trials for case in trial.get("cases") or []):
            break
        status = http.get("/api/experiments/{}".format(experiment_id)).json()
        if status.get("status") == "done":
            break
        time.sleep(0.1)
    status = http.get("/api/experiments/{}".format(experiment_id)).json()
    assert status["status"] == "done"
    trials = http.get("/api/experiments/{}/trials".format(experiment_id)).json()
    assert len(trials) == 1
    trial_id = trials[0]["trial_id"]
    trial = http.get("/api/trials/{}".format(trial_id)).json()
    assert len(trial["cases"]) >= 1
    case_id = trial["cases"][0]["case_id"]
    case = http.get("/api/cases/{}".format(case_id)).json()
    assert case["status"] == "done"
    log = http.get("/api/cases/{}/log".format(case_id)).json()
    assert log["composition"] == "mixed"
    judge = http.get("/api/cases/{}/judge".format(case_id)).json()
    assert judge["status"] == "missing"
    analysis = http.get(
        "/api/experiments/{}/analysis/experiment".format(experiment_id)
    ).json()
    assert analysis["status"] == "missing"
    assert (runs_dir / experiment_id / "t001" / "c00-mixed" / "result.html").is_file()


def test_second_start_while_running_returns_409(client, monkeypatch):
    http, _runs = client
    started = threading.Event()
    release = threading.Event()

    def hang(self, experiment_id=None):
        started.set()
        release.wait(timeout=5)
        return {"experiment_id": experiment_id}

    monkeypatch.setattr(
        "mbti_werewolf.web.app.ExperimentRunner.run", hang
    )
    first = http.post("/api/experiments", json={"brain": {"provider": "stub"}, "cases": "c00"})
    assert first.status_code == 202
    assert started.wait(timeout=3)
    second = http.post("/api/experiments", json={"brain": {"provider": "stub"}, "cases": "c00"})
    assert second.status_code == 409
    release.set()


def test_unknown_experiment_is_404(client):
    http, _runs = client
    response = http.get("/api/experiments/e-missing")
    assert response.status_code == 404


def test_index_serves_the_shell_page(client):
    http, _runs = client
    response = http.get("/")
    assert response.status_code == 200
    assert "操作画面" in response.text
    css = http.get("/static/style.css")
    assert css.status_code == 200
