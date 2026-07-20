"""Interface en ligne de commande Pathtrace."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from pathtrace.adapters import available_adapters, get_adapter
from pathtrace.adapters.base import AdapterInstallError
from pathtrace.campaign import CampaignError, execute_run_suite, format_campaign
from pathtrace.capture import safe_fragment
from pathtrace.engine.evaluator import evaluate_test_suite
from pathtrace.engine.loader import (
    PathtraceLoaderError,
    discover_run_suites,
    find_latest_trace,
    load_tests,
    load_trace,
)
from pathtrace.engine.report import build_report, format_report, write_json_report
from pathtrace.runners import available_runners
from pathtrace.visualization.html_graph import write_html_graph


@click.group()
def cli() -> None:
    """Teste le chemin d'orchestration suivi par un agent IA."""


@cli.command("install")
@click.option("--framework", type=click.Choice(available_adapters()), required=True)
def install_command(framework: str) -> None:
    """Installe la capture passive du framework choisi."""
    try:
        config_path = get_adapter(framework).install(Path.cwd())
    except (ValueError, AdapterInstallError) as error:
        raise click.ClickException(str(error)) from error
    click.echo(f"Capture {framework} installée : {config_path}")
    click.echo("Les traces seront écrites dans .pathtrace/traces/")


@cli.group("hook")
def hook_group() -> None:
    """Commandes internes appelées par les hooks des agents."""


@hook_group.command("receive", hidden=True)
@click.argument("framework")
@click.argument("event_slug")
def receive_hook_command(framework: str, event_slug: str) -> None:
    _handle_hook(framework, event_slug)


@hook_group.command("codex", hidden=True)
@click.argument("event_slug")
def legacy_codex_hook_command(event_slug: str) -> None:
    """Compatibilité avec l'ancienne commande pathtrace hook codex."""
    _handle_hook("codex", event_slug)


def _handle_hook(framework: str, event_slug: str) -> None:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        payload = {}
    try:
        output = get_adapter(framework).handle(event_slug, payload, Path.cwd())
    except ValueError as error:
        raise click.ClickException(str(error)) from error
    if output is not None:
        click.echo(json.dumps({}))


@cli.command("test")
@click.option("--trace", "trace_path", type=click.Path(path_type=Path))
@click.option("--latest", is_flag=True, help="Utilise la trace la plus récente de .pathtrace/traces.")
@click.option("--tests", "tests_path", required=True, type=click.Path(path_type=Path))
@click.option("--report", "write_report", is_flag=True, help="Écrit le rapport JSON.")
@click.option("--graph", "write_graph", is_flag=True, help="Écrit le graphe HTML autonome.")
@click.option("--output-dir", type=click.Path(path_type=Path), default=Path(".pathtrace"))
def test_command(
    trace_path: Path | None,
    latest: bool,
    tests_path: Path,
    write_report: bool,
    write_graph: bool,
    output_dir: Path,
) -> None:
    """Évalue une suite YAML contre une trace déjà capturée."""
    if bool(trace_path) == latest:
        raise click.ClickException("Choisis exactement une source : --trace PATH ou --latest")

    try:
        resolved_trace_path = trace_path or find_latest_trace()
        trace = load_trace(resolved_trace_path)
        test_suite = load_tests(tests_path)
    except PathtraceLoaderError as error:
        raise click.ClickException(str(error)) from error

    results = evaluate_test_suite(trace, test_suite)
    report = build_report(trace, test_suite, results)
    click.echo(format_report(trace, test_suite, results))

    if write_report or write_graph:
        stem = _output_stem(trace)
        report_path = output_dir / "reports" / f"{stem}.json"
        write_json_report(report, report_path)
        click.echo(f"Rapport JSON : {report_path}")
    if write_graph:
        graph_path = output_dir / "graphs" / f"{_output_stem(trace)}.html"
        write_html_graph(trace, report, graph_path)
        click.echo(f"Graphe HTML : {graph_path}")

    if report["summary"]["failed"]:
        raise click.exceptions.Exit(1)


@cli.command("run")
@click.option(
    "--tests",
    "suite_inputs",
    multiple=True,
    required=True,
    help="Suite YAML automatisée, dossier ou motif glob. Option répétable.",
)
@click.option("--framework", type=click.Choice(available_runners()))
@click.option("--project-dir", type=click.Path(path_type=Path))
@click.option("--runner-arg", "runner_args", multiple=True, help="Argument transmis au runner.")
@click.option("--timeout", type=click.FloatRange(min=0.001))
@click.option("--trace-timeout", type=click.FloatRange(min=0.001))
@click.option("--report", "write_report", is_flag=True, help="Écrit les rapports JSON.")
@click.option("--graph", "write_graph", is_flag=True, help="Écrit un graphe HTML par scénario.")
@click.option("--fail-fast", is_flag=True, help="Arrête la campagne au premier échec.")
@click.option("--output-dir", type=click.Path(path_type=Path), default=Path(".pathtrace"))
def run_command(
    suite_inputs: tuple[str, ...],
    framework: str | None,
    project_dir: Path | None,
    runner_args: tuple[str, ...],
    timeout: float | None,
    trace_timeout: float | None,
    write_report: bool,
    write_graph: bool,
    fail_fast: bool,
    output_dir: Path,
) -> None:
    """Lance les prompts d'une campagne puis vérifie chaque trace."""
    try:
        suite_paths = discover_run_suites(suite_inputs)
        campaigns = []
        for suite_path in suite_paths:
            campaign = execute_run_suite(
                suite_path,
                framework_override=framework,
                project_dir_override=project_dir,
                runner_args_override=runner_args,
                timeout_override=timeout,
                trace_timeout_override=trace_timeout,
                output_dir=output_dir,
                write_report=write_report,
                write_graph=write_graph,
                fail_fast=fail_fast,
            )
            campaigns.append(campaign)
            click.echo(f"Suite: {suite_path}")
            click.echo(format_campaign(campaign))
            if fail_fast and campaign["summary"]["failed"]:
                break
    except (PathtraceLoaderError, CampaignError, AdapterInstallError) as error:
        raise click.ClickException(str(error)) from error

    if any(campaign["summary"]["failed"] for campaign in campaigns):
        raise click.exceptions.Exit(1)


def _output_stem(trace: dict[str, object]) -> str:
    values = [
        str(trace.get("framework") or "unknown"),
        str(trace.get("session_id") or "unknown-session"),
        str(trace.get("turn_id") or "unknown-turn"),
    ]
    return "__".join(safe_fragment(value) for value in values)
