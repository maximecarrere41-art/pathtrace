"""Exécution automatisée de campagnes prompt → trace → assertions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pathtrace.adapters import get_adapter
from pathtrace.config import InstallTarget, prepare_activation, write_project_config
from pathtrace.capture import safe_fragment
from pathtrace.engine.evaluator import evaluate_test_suite
from pathtrace.engine.loader import load_run_suite, load_trace, scenario_test_suite
from pathtrace.engine.report import build_report, write_json_report
from pathtrace.model import build_trace
from pathtrace.runners import get_runner
from pathtrace.runners.base import RunRequest, RunResult, RunnerExecutionError
from pathtrace.visualization.html_graph import write_html_graph


class CampaignError(RuntimeError):
    """Une suite automatisée ne peut pas être exécutée correctement."""


def execute_run_suite(
    suite_path: Path,
    *,
    framework_override: str | None = None,
    project_dir_override: Path | None = None,
    runner_args_override: tuple[str, ...] = (),
    timeout_override: float | None = None,
    trace_timeout_override: float | None = None,
    output_dir: Path = Path(".pathtrace"),
    write_report: bool = False,
    write_graph: bool = False,
    fail_fast: bool = False,
) -> dict[str, Any]:
    """Lance tous les scénarios d'une suite et retourne un rapport de campagne."""
    suite_path = suite_path.resolve()
    suite = load_run_suite(suite_path)
    defaults = suite.get("defaults") if isinstance(suite.get("defaults"), dict) else {}
    results: list[dict[str, Any]] = []

    for scenario in suite["scenarios"]:
        result = _execute_scenario(
            scenario=scenario,
            suite=suite,
            suite_path=suite_path,
            defaults=defaults,
            framework_override=framework_override,
            project_dir_override=project_dir_override,
            runner_args_override=runner_args_override,
            timeout_override=timeout_override,
            trace_timeout_override=trace_timeout_override,
            output_dir=output_dir,
            write_report=write_report,
            write_graph=write_graph,
        )
        results.append(result)
        if fail_fast and not result["passed"]:
            break

    passed = sum(item["passed"] is True for item in results)
    campaign = {
        "version": 1,
        "suite": str(suite_path),
        "summary": {
            "status": "passed" if passed == len(results) else "failed",
            "passed": passed,
            "failed": len(results) - passed,
            "executed": len(results),
            "declared": len(suite["scenarios"]),
        },
        "scenarios": results,
    }
    if write_report:
        campaign_path = output_dir / "campaigns" / f"{safe_fragment(suite_path.stem)}.json"
        write_json_report(campaign, campaign_path)
        campaign["campaign_report_path"] = str(campaign_path)
    return campaign


def format_campaign(campaign: dict[str, Any]) -> str:
    lines: list[str] = []
    for scenario in campaign["scenarios"]:
        label = "PASS" if scenario["passed"] else "FAIL"
        lines.append(f"[{label}] {scenario['name']}")
        if scenario.get("error"):
            lines.append(f"  {scenario['error']}")
        if scenario.get("trace_path"):
            lines.append(f"  trace: {scenario['trace_path']}")
        if scenario.get("report_path"):
            lines.append(f"  report: {scenario['report_path']}")
        if scenario.get("graph_path"):
            lines.append(f"  graph: {scenario['graph_path']}")
    summary = campaign["summary"]
    lines.append(
        f"Campaign summary: {summary['passed']} passed, {summary['failed']} failed "
        f"({summary['executed']}/{summary['declared']} executed)"
    )
    if campaign.get("campaign_report_path"):
        lines.append(f"Campaign report: {campaign['campaign_report_path']}")
    return "\n".join(lines)


def _execute_scenario(
    *,
    scenario: dict[str, Any],
    suite: dict[str, Any],
    suite_path: Path,
    defaults: dict[str, Any],
    framework_override: str | None,
    project_dir_override: Path | None,
    runner_args_override: tuple[str, ...],
    timeout_override: float | None,
    trace_timeout_override: float | None,
    output_dir: Path,
    write_report: bool,
    write_graph: bool,
) -> dict[str, Any]:
    name = str(scenario["name"])
    prompt = str(scenario["prompt"])
    framework = framework_override or _setting(scenario, defaults, suite, "framework")
    if not isinstance(framework, str) or not framework:
        return _infrastructure_failure(name, prompt, "framework manquant dans la suite ou --framework")

    project_dir = _project_dir(
        project_dir_override,
        _setting(scenario, defaults, suite, "project_dir", "."),
        suite_path,
    )
    timeout = float(timeout_override or _setting(scenario, defaults, suite, "timeout", 600))
    trace_timeout = float(
        trace_timeout_override or _setting(scenario, defaults, suite, "trace_timeout", 10)
    )
    executable = _setting(scenario, defaults, suite, "executable")
    configured_args = _string_tuple(_setting(scenario, defaults, suite, "runner_args", []))
    runner_args = configured_args + tuple(runner_args_override)

    try:
        config = prepare_activation(project_dir, InstallTarget.OBSERVE, framework)
        get_adapter(framework).install(project_dir, config.features_for(framework))
        write_project_config(project_dir, config)
        run_result = get_runner(framework).run(
            RunRequest(
                prompt=prompt,
                project_dir=project_dir,
                timeout_seconds=timeout,
                trace_timeout_seconds=trace_timeout,
                executable=executable if isinstance(executable, str) else None,
                runner_args=runner_args,
            )
        )
    except (ValueError, RunnerExecutionError, OSError) as error:
        return _infrastructure_failure(name, prompt, str(error), framework=framework)

    tests = scenario_test_suite(scenario, suite_path)
    if run_result.trace_path is None:
        return _missing_trace_result(
            name=name,
            prompt=prompt,
            framework=framework,
            run_result=run_result,
            tests=tests,
            output_dir=output_dir,
            suite_path=suite_path,
            write_report=write_report,
            write_graph=write_graph,
        )

    trace = load_trace(run_result.trace_path)
    test_results = evaluate_test_suite(trace, tests)
    report = build_report(trace, tests, test_results)
    _attach_execution(report, run_result)
    passed = report["outcome"]["passed"]
    artifacts = _write_scenario_artifacts(
        suite_path=suite_path,
        scenario_name=name,
        trace=trace,
        report=report,
        output_dir=output_dir,
        write_report=write_report,
        write_graph=write_graph,
    )
    return {
        "name": name,
        "framework": framework,
        "project_dir": str(project_dir),
        "passed": passed,
        "trace_path": str(run_result.trace_path),
        "run": _run_payload(run_result),
        "test_summary": report["summary"],
        **artifacts,
    }


def _missing_trace_result(
    *,
    name: str,
    prompt: str,
    framework: str,
    run_result: RunResult,
    tests: dict[str, Any],
    output_dir: Path,
    suite_path: Path,
    write_report: bool,
    write_graph: bool,
) -> dict[str, Any]:
    trace = build_trace(
        framework=framework,
        session_id="runner",
        turn_id=safe_fragment(name),
        prompt=prompt,
        model="unknown",
        events=[],
        status="failure",
    )
    empty_results = evaluate_test_suite(trace, tests)
    report = build_report(trace, tests, empty_results)
    _attach_execution(report, run_result, error="Aucune trace créée par les hooks de l'agent.")
    artifacts = _write_scenario_artifacts(
        suite_path=suite_path,
        scenario_name=name,
        trace=trace,
        report=report,
        output_dir=output_dir,
        write_report=write_report,
        write_graph=write_graph,
    )
    return {
        "name": name,
        "framework": framework,
        "passed": False,
        "error": "Aucune trace créée par les hooks de l'agent.",
        "trace_path": None,
        "run": _run_payload(run_result),
        "test_summary": report["summary"],
        **artifacts,
    }


def _attach_execution(
    report: dict[str, Any],
    result: RunResult,
    error: str | None = None,
) -> None:
    execution_passed = result.process_passed and result.trace_path is not None and error is None
    report["execution"] = {
        "passed": execution_passed,
        **_run_payload(result),
    }
    if error:
        report["execution"]["error"] = error
    assertions_passed = report["summary"]["failed"] == 0
    report["outcome"] = {"passed": execution_passed and assertions_passed}


def _write_scenario_artifacts(
    *,
    suite_path: Path,
    scenario_name: str,
    trace: dict[str, Any],
    report: dict[str, Any],
    output_dir: Path,
    write_report: bool,
    write_graph: bool,
) -> dict[str, str]:
    stem = "__".join(
        [
            safe_fragment(suite_path.stem),
            safe_fragment(scenario_name),
            safe_fragment(str(trace.get("session_id") or "unknown-session")),
            safe_fragment(str(trace.get("turn_id") or "unknown-turn")),
        ]
    )
    artifacts: dict[str, str] = {}
    if write_report or write_graph:
        report_path = output_dir / "reports" / f"{stem}.json"
        write_json_report(report, report_path)
        artifacts["report_path"] = str(report_path)
    if write_graph:
        graph_path = output_dir / "graphs" / f"{stem}.html"
        write_html_graph(trace, report, graph_path)
        artifacts["graph_path"] = str(graph_path)
    return artifacts


def _run_payload(result: RunResult) -> dict[str, Any]:
    return {
        "command": list(result.command),
        "exit_code": result.exit_code,
        "timed_out": result.timed_out,
        "duration_seconds": result.duration_seconds,
        "stdout_tail": result.stdout[-2000:],
        "stderr_tail": result.stderr[-2000:],
    }


def _infrastructure_failure(
    name: str,
    prompt: str,
    error: str,
    *,
    framework: str | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "framework": framework,
        "prompt": prompt,
        "passed": False,
        "error": error,
        "trace_path": None,
    }


def _setting(
    scenario: dict[str, Any],
    defaults: dict[str, Any],
    suite: dict[str, Any],
    name: str,
    fallback: Any = None,
) -> Any:
    if name in scenario:
        return scenario[name]
    if name in defaults:
        return defaults[name]
    return suite.get(name, fallback)


def _project_dir(override: Path | None, configured: Any, suite_path: Path) -> Path:
    if override is not None:
        return override.resolve()
    path = Path(str(configured or "."))
    if not path.is_absolute():
        path = suite_path.parent / path
    return path.resolve()


def _string_tuple(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, str))
