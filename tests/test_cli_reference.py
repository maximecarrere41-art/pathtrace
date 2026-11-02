import re
import shlex
from pathlib import Path

import pytest
from click.testing import CliRunner

from pathtrace.cli import cli


ROOT = Path(__file__).resolve().parents[1]
REFERENCE = (ROOT / "docs" / "cli-reference.md").read_text(encoding="utf-8")
PUBLIC_COMMANDS = [(name, cmd) for name, cmd in cli.commands.items() if not cmd.hidden]
TABLE_ROWS = [line.split("|")[1:-1] for line in REFERENCE.splitlines() if line.strip()]
EXAMPLES = [row[-1].strip().strip("`") for row in TABLE_ROWS[2:]]


@pytest.mark.parametrize(("name", "command"), PUBLIC_COMMANDS)
def test_reference_covers_every_public_command_and_option(name, command):
    assert f"pathtrace {name}" in REFERENCE
    for parameter in command.params:
        for option in (*parameter.opts, *parameter.secondary_opts):
            if option.startswith("--"):
                assert f"`{option}" in REFERENCE, f"Undocumented option: {name} {option}"


@pytest.mark.parametrize("example", EXAMPLES)
def test_documented_examples_use_valid_public_syntax(example):
    if "--help" in shlex.split(example):
        assert CliRunner().invoke(cli, shlex.split(example)[1:]).exit_code == 0
        return
    _, name, *arguments = shlex.split(example)
    command = cli.commands[name]
    assert not command.hidden
    with command.make_context(name, arguments):
        pass


def test_reference_is_only_one_four_column_table():
    assert all(line.startswith("|") and line.endswith("|") for line in REFERENCE.splitlines() if line)
    assert all(len(row) == 4 for row in TABLE_ROWS)
    assert [cell.strip() for cell in TABLE_ROWS[0]] == [
        "Commande Pathtrace", "Paramètres et valeurs possibles", "Explication courte", "Exemple complet"]
    assert EXAMPLES and all(example.startswith("pathtrace ") for example in EXAMPLES)


def test_reference_explains_scope_location_and_default_in_table():
    assert "n'importe quel dossier" in REFERENCE
    assert "racine du projet" in REFERENCE
    assert "défaut : `project`" in REFERENCE


def test_documented_trace_example_produces_report_and_graph(tmp_path):
    result = CliRunner().invoke(cli, ["test", "--trace", str(ROOT / "examples/trace-example.json"),
                                     "--tests", str(ROOT / "examples/path-tests-example.yaml"),
                                     "--report", "--graph", "--output-dir", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert list((tmp_path / "reports").glob("*.json"))
    assert list((tmp_path / "graphs").glob("*.html"))


def test_help_only_advertises_public_commands():
    result = CliRunner().invoke(cli, ["--help"])
    assert not re.search(r"^  hook\s", result.output, re.M)
    assert all(name in result.output for name, _ in PUBLIC_COMMANDS)
