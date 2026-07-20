import json

from pathtrace.engine.report import build_report, format_report, write_json_report


def test_build_report_keeps_enriched_assertion_data(tmp_path):
    trace = {
        "id": "x",
        "session_id": "s",
        "turn_id": "t",
        "framework": "codex",
        "model": "m",
        "prompt": "p",
        "summary": {},
    }
    suite = {"tests": [{"name": "scenario"}]}
    results = [
        {
            "passed": False,
            "assertions": [
                {
                    "passed": False,
                    "type": "must_not_include",
                    "reason": "forbidden",
                    "expected": {},
                    "matched_event_indexes": [1],
                    "failed_event_indexes": [1],
                }
            ],
        }
    ]

    report = build_report(trace, suite, results)
    output = write_json_report(report, tmp_path / "report.json")

    assert report["summary"] == {"status": "failed", "passed": 0, "failed": 1}
    assert report["tests"][0]["assertions"][0]["failed_event_indexes"] == [1]
    assert json.loads(output.read_text(encoding="utf-8"))["summary"]["failed"] == 1


def test_format_report_displays_failure_reason():
    trace = {"framework": "codex", "session_id": "s", "turn_id": "t"}
    suite = {"tests": [{"name": "scenario"}]}
    results = [{"passed": False, "assertions": [{"passed": False, "reason": "forbidden"}]}]

    text = format_report(trace, suite, results)

    assert "FAIL" in text
    assert "forbidden" in text
    assert "Summary: 0 passed, 1 failed" in text
