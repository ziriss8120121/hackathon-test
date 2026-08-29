"""所要時間と出力容量の実測記録（設計書1.3、M7）。"""

from __future__ import annotations

from mbti_werewolf.record.timing import (
    bytes_per_done_case,
    case_output_bytes,
    count_stop_reasons,
    directory_bytes,
    format_bytes,
    format_duration,
    seconds_per_call,
    write_timing_note,
)


def test_format_bytes_and_duration():
    assert format_bytes(512) == "512 B"
    assert format_bytes(2048) == "2.0 KB"
    assert format_duration(12.3) == "12.3秒"
    assert format_duration(120) == "約2分"
    assert format_duration(4 * 3600) == "約4.0時間"


def test_directory_and_case_bytes(tmp_path):
    exp = tmp_path / "e-1"
    case = exp / "t001" / "c00-mixed"
    case.mkdir(parents=True)
    (case / "case_log.json").write_text("hello", encoding="utf-8")
    (exp / "timing.md").write_text("note", encoding="utf-8")

    assert directory_bytes(exp) == 5 + 4
    assert case_output_bytes(exp) == 5
    assert bytes_per_done_case(500, 2) == 250
    assert bytes_per_done_case(500, 0) is None


def test_stop_reasons_count_only_done_cases():
    logs = [
        {"status": "done", "discussion": {"stop_reason": "all_pass"}},
        {"status": "done", "discussion": {"stop_reason": "max_rounds"}},
        {"status": "done", "discussion": {"stop_reason": "all_pass"}},
        {"status": "failed", "discussion": {"stop_reason": "max_rounds"}},
        {"status": "done", "discussion": {"stop_reason": None}},
    ]
    assert count_stop_reasons(logs) == {"all_pass": 2, "max_rounds": 1}


def test_timing_note_includes_scale_and_size(tmp_path):
    path = tmp_path / "timing.md"
    write_timing_note(
        path,
        {
            "experiment_id": "e-test",
            "done_count": 1,
            "failed_count": 0,
            "inference_calls": 10,
            "ai_wait_seconds": 106.0,
            "elapsed_seconds": 120.0,
            "seconds_per_done_case": seconds_per_call(120.0, 1),
            "output_bytes": 800_000,
            "case_output_bytes": 700_000,
            "bytes_per_done_case": 700_000,
            "discussion_stop_reasons": {"all_pass": 1},
        },
        {"provider": "ollama", "model": "gemma3:4b"},
    )
    text = path.read_text(encoding="utf-8")
    assert "出力容量" in text
    assert "規模の見込み" in text
    assert "1 Trial（17ケース）" in text
    assert "100 Trial" in text
    assert "all_pass 1" in text
    assert "1 Trial（17ケース）未満" in text
