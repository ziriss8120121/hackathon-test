"""操作画面のAPIを確認する。

対応要件: F-50〜F-56、AC-13〜AC-15

設計書10章の一覧には無いテストだが、画面から実行する経路が要件の主経路に
なったため追加した。画面のHTML/JSではなくAPIを検査対象にしているのは、画面が
ブラッシュアップで作り替わってもこの契約は変わらないためである（設計書7.1）。
"""

from __future__ import annotations

import threading
import time

import pytest

fastapi_testclient = pytest.importorskip("fastapi.testclient")
TestClient = fastapi_testclient.TestClient

from mbti_werewolf.web.app import JobManager, RunInProgress, create_app


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(runs_dir=tmp_path)) as test_client:
        yield test_client


def _wait_until_finished(client, run_id, timeout=30.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        status = client.get("/api/runs/{}".format(run_id)).json()
        if status["status"] in ("done", "failed"):
            return status
        time.sleep(0.05)
    raise AssertionError("実行が {} 秒以内に終わらなかった".format(timeout))


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_default_config(client):
    config = client.get("/api/config/default").json()

    assert config["player_count"] == 4
    assert config["turn_count"] == 3
    assert config["functions"] == ["Ne", "Si", "Fi", "Te"]
    assert config["mbti_types"] == ["ENTP", "ISFJ", "INFP", "ESTJ"]
    assert config["brain"]["provider"] in ("stub", "ollama", "gemini")
    assert "machine_name" in config


def test_index_and_static_are_served(client):
    assert client.get("/").status_code == 200
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/static/style.css").status_code == 200


def test_run_from_api_produces_same_outputs_as_cli(client, tmp_path):
    """画面経路でも同じ実行と出力になること（AC-16）。"""
    response = client.post(
        "/api/runs",
        json={"seed": 99, "turn_count": 2, "brain": {"provider": "stub"}},
    )

    assert response.status_code == 202
    job = response.json()
    assert job["status"] == "queued"
    assert job["run_id"].endswith("-r001")

    status = _wait_until_finished(client, job["run_id"])
    assert status["status"] == "done"
    assert status["turn_count"] == 2

    log = client.get("/api/runs/{}/log".format(job["run_id"])).json()
    assert log["config"]["seed"] == 99
    assert len(log["turns"]) == 8  # 4人 × 2ターン
    assert log["result"]["winner"] in ("village", "werewolf")

    run_dir = tmp_path / job["series_id"] / "r001"
    for name in ("run_log.json", "summary.md", "timeline.md", "metrics.csv", "result.html"):
        assert (run_dir / name).is_file()

    listed = client.get("/api/runs").json()["runs"]
    assert [item["run_id"] for item in listed] == [job["run_id"]]
    assert listed[0]["winner"] == log["result"]["winner"]

    series = client.get("/api/series/{}".format(job["series_id"])).json()
    assert series["status"] == "done"
    assert series["success_count"] == 1

    # 結果ビューは操作画面からも開ける（要件F-34）。
    assert client.get("/runs/{}/r001/result.html".format(job["series_id"])).status_code == 200


def test_invalid_config_is_rejected(client):
    response = client.post("/api/runs", json={"player_count": 1})

    assert response.status_code == 400
    assert "player_count" in response.json()["detail"]


def test_unknown_run_returns_404(client):
    assert client.get("/api/runs/s-20000101-000000-r001").status_code == 404
    assert client.get("/api/runs/s-20000101-000000-r001/log").status_code == 404


def test_malformed_run_id_is_rejected(client):
    assert client.get("/api/runs/..%2F..%2Fetc").status_code in (400, 404)


def test_second_run_is_rejected_while_running(tmp_path):
    """同時実行は1本に絞る（設計書8.3）。"""
    release = threading.Event()

    class BlockingRunner:
        def __init__(self):
            self.runs_dir = tmp_path

        def create_series(self, config):
            return "s-test"

        def execute_series(self, series_id, config):
            release.wait(timeout=5)

    class FakeConfig:
        game_count = 1

    jobs = JobManager(BlockingRunner())
    try:
        first = jobs.start(FakeConfig())
        assert first["run_id"] == "s-test-r001"

        with pytest.raises(RunInProgress):
            jobs.start(FakeConfig())
    finally:
        release.set()
        jobs.shutdown()
