from pathtrace.visualization.html_graph import render_html_graph, write_html_graph


def test_graph_contains_prompt_skills_commands_and_failed_marker(tmp_path):
    trace = {
        "framework": "codex",
        "session_id": "s",
        "turn_id": "t",
        "prompt": "run tests",
        "model": "m",
        "events": [
            {"type": "skill", "name": "pdfs", "tool": "Read"},
            {"type": "tool_call", "name": "Bash", "command": "pytest", "status": "failure"},
        ],
    }
    report = {
        "summary": {"passed": 0, "failed": 1},
        "tests": [
            {
                "name": "validation",
                "assertions": [
                    {
                        "passed": False,
                        "type": "status_equals",
                        "reason": "wrong status",
                        "failed_event_indexes": [1],
                    }
                ],
            }
        ],
    }

    html = render_html_graph(trace, report)
    output = write_html_graph(trace, report, tmp_path / "graph.html")

    assert "run tests" in html
    assert "pdfs" in html
    assert "pytest" in html
    assert 'node tool_call failed' in html
    assert output.is_file()
