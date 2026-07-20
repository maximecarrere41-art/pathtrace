"""Génère un graphe HTML autonome, sans dépendance JavaScript externe."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any


def write_html_graph(trace: dict[str, Any], report: dict[str, Any], path: str | Path) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_html_graph(trace, report), encoding="utf-8")
    return output


def render_html_graph(trace: dict[str, Any], report: dict[str, Any]) -> str:
    failed_indexes = _failed_indexes(report)
    nodes = [_prompt_node(trace)] + [
        _event_node(event, index in failed_indexes)
        for index, event in enumerate(trace.get("events", []))
    ] + [_result_node(report)]
    details = _assertion_details(report)
    execution = _execution_details(report)
    payload = html.escape(json.dumps({"trace": trace, "report": report}, ensure_ascii=False, indent=2))
    return f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Pathtrace · {_escape(trace.get('session_id', 'trace'))}</title>
<style>
:root {{ color-scheme: light dark; --bg:#0b1020; --panel:#141b31; --text:#eef2ff; --muted:#9da9c7; --line:#56617d; --tool:#2563eb; --skill:#7c3aed; --ok:#16a34a; --bad:#dc2626; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; font-family:Inter,ui-sans-serif,system-ui,sans-serif; background:var(--bg); color:var(--text); }}
main {{ max-width:1100px; margin:auto; padding:32px 18px 60px; }}
h1 {{ margin:0 0 6px; font-size:30px; }}
.meta {{ color:var(--muted); margin-bottom:28px; }}
.flow {{ display:flex; gap:16px; align-items:stretch; overflow-x:auto; padding:8px 2px 24px; }}
.node {{ min-width:220px; max-width:280px; background:var(--panel); border:2px solid var(--line); border-radius:16px; padding:16px; position:relative; box-shadow:0 12px 30px rgba(0,0,0,.18); }}
.node:not(:last-child)::after {{ content:'→'; position:absolute; right:-18px; top:44%; color:var(--muted); font-size:24px; }}
.node.tool_call {{ border-color:var(--tool); }} .node.skill {{ border-color:var(--skill); }}
.node.failed {{ border-color:var(--bad); box-shadow:0 0 0 3px rgba(220,38,38,.22); }}
.node.result.ok {{ border-color:var(--ok); }} .node.result.bad {{ border-color:var(--bad); }}
.badge {{ display:inline-block; padding:3px 8px; border-radius:999px; background:rgba(255,255,255,.09); color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.05em; }}
.node h2 {{ font-size:17px; margin:10px 0 8px; overflow-wrap:anywhere; }}
.node p {{ margin:5px 0; color:var(--muted); font-size:14px; overflow-wrap:anywhere; }}
section {{ background:var(--panel); border-radius:16px; padding:20px; margin-top:18px; }}
.assertion {{ border-left:4px solid var(--ok); padding:10px 12px; margin:10px 0; background:rgba(255,255,255,.025); }}
.assertion.failed {{ border-left-color:var(--bad); }}
pre {{ white-space:pre-wrap; overflow-wrap:anywhere; color:var(--muted); font-size:12px; }}
summary {{ cursor:pointer; font-weight:700; }}
</style>
</head>
<body><main>
<h1>Pathtrace</h1>
<div class="meta">{_escape(trace.get('framework'))} · session {_escape(trace.get('session_id'))} · tour {_escape(trace.get('turn_id'))}</div>
<div class="flow">{''.join(nodes)}</div>
{execution}
<section><h2>Assertions</h2>{details}</section>
<section><details><summary>Données JSON</summary><pre>{payload}</pre></details></section>
</main></body></html>"""


def _prompt_node(trace: dict[str, Any]) -> str:
    prompt = str(trace.get("prompt") or "(prompt non capturé)")
    return f'<article class="node prompt"><span class="badge">prompt</span><h2>{_escape(_short(prompt, 100))}</h2><p>{_escape(trace.get("model"))}</p></article>'


def _event_node(event: dict[str, Any], failed: bool) -> str:
    event_type = str(event.get("type") or "tool_call")
    classes = f"node {event_type}{' failed' if failed else ''}"
    lines = []
    if event.get("tool"):
        lines.append(f"outil : {_escape(event['tool'])}")
    if event.get("command"):
        lines.append(f"commande : {_escape(_short(str(event['command']), 130))}")
    if event.get("path"):
        lines.append(f"chemin : {_escape(_short(str(event['path']), 130))}")
    if event.get("status"):
        lines.append(f"statut : {_escape(event['status'])}")
    details = "".join(f"<p>{line}</p>" for line in lines)
    return f'<article class="{classes}"><span class="badge">{_escape(event_type)}</span><h2>{_escape(event.get("name"))}</h2>{details}</article>'


def _result_node(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    outcome = report.get("outcome", {})
    ok = outcome.get("passed", summary.get("failed", 0) == 0)
    return f'<article class="node result {"ok" if ok else "bad"}"><span class="badge">résultat</span><h2>{"PASS" if ok else "FAIL"}</h2><p>{summary.get("passed", 0)} réussi(s), {summary.get("failed", 0)} échoué(s)</p></article>'


def _execution_details(report: dict[str, Any]) -> str:
    execution = report.get("execution")
    if not isinstance(execution, dict):
        return ""
    passed = execution.get("passed") is True
    command = " ".join(str(item) for item in execution.get("command", []))
    error = execution.get("error") or execution.get("stderr_tail") or ""
    return (
        '<section><h2>Exécution de l’agent</h2>'
        f'<div class="assertion{"" if passed else " failed"}">'
        f'<strong>{"PASS" if passed else "FAIL"} · processus</strong>'
        f'<p>code retour : {_escape(execution.get("exit_code"))}</p>'
        f'<p>commande : {_escape(command)}</p>'
        f'<p>{_escape(error)}</p></div></section>'
    )


def _assertion_details(report: dict[str, Any]) -> str:
    blocks: list[str] = []
    for test in report.get("tests", []):
        blocks.append(f"<h3>{_escape(test.get('name'))}</h3>")
        for assertion in test.get("assertions", []):
            failed = not assertion.get("passed")
            blocks.append(
                f'<div class="assertion{" failed" if failed else ""}"><strong>{"FAIL" if failed else "PASS"} · {_escape(assertion.get("type"))}</strong><p>{_escape(assertion.get("reason"))}</p></div>'
            )
    return "".join(blocks) or "<p>Aucune assertion.</p>"


def _failed_indexes(report: dict[str, Any]) -> set[int]:
    indexes: set[int] = set()
    for test in report.get("tests", []):
        for assertion in test.get("assertions", []):
            if assertion.get("passed") is False:
                indexes.update(assertion.get("failed_event_indexes", []))
    return indexes


def _escape(value: Any) -> str:
    return html.escape(str(value or ""))


def _short(value: str, limit: int) -> str:
    return value if len(value) <= limit else value[: limit - 1] + "…"
