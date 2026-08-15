"""Construction d'une action Security canonique."""

from __future__ import annotations

import ntpath
import os
import posixpath
import re
import shlex
from pathlib import Path
from typing import Any

from pathtrace.security.model import SecurityAction, SecurityActionType


GIT_COMMAND = re.compile(r"git(?:\.exe)?(?=\s|$|[\"'])", re.IGNORECASE)
GIT_PREFIXES = (
    re.compile(
        r"(?:^|&&|&|\|\||\||;)\s*[\"']?(?P<git>git(?:\.exe)?)",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*cmd(?:\.exe)?\s+/[ck]\s+[\"']?(?P<git>git(?:\.exe)?)",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*(?:powershell|pwsh)(?:\.exe)?\b.*?"
        r"(?:-command|-c)\s+.*?(?P<git>git(?:\.exe)?)",
        re.IGNORECASE,
    ),
)
WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:[\\/]")
SHELL_TOOLS = {
    "bash",
    "cmd",
    "powershell",
    "shell",
    "shell_command",
}
GIT_OPTIONS_WITH_VALUE = {
    "-c",
    "--config-env",
    "--git-dir",
    "--namespace",
    "--work-tree",
}
GIT_FLAG_OPTIONS = {
    "--bare",
    "--glob-pathspecs",
    "--icase-pathspecs",
    "--literal-pathspecs",
    "--no-optional-locks",
    "--no-pager",
    "--no-replace-objects",
    "--noglob-pathspecs",
    "--paginate",
}
GIT_OPTIONS_WITH_ASSIGNMENT = (
    "--config-env=",
    "--git-dir=",
    "--namespace=",
    "--work-tree=",
)


def build_security_action(
    *,
    framework: str,
    session_id: str | None,
    turn_id: str | None,
    tool: str | None,
    tool_input: Any,
    cwd: str | None = None,
) -> SecurityAction:
    inputs = tool_input if isinstance(tool_input, dict) else {}
    cwd = cwd or _first_text(inputs, "cwd", "working_directory", "workingDirectory")
    command = _first_text(inputs, "command", "cmd", "script")
    resource = _first_text(
        inputs,
        "file_path",
        "filePath",
        "path",
        "resource",
        "url",
        "uri",
    )
    mcp_server = _mcp_server(tool)
    git_command = _git_command(command) if _is_shell_tool(tool) else None
    action_type = _action_type(tool, command, resource, mcp_server, git_command)
    if action_type is SecurityActionType.GIT:
        command = canonicalize_git_command(git_command or "", cwd)
    if action_type is SecurityActionType.FILESYSTEM:
        resource = canonicalize_filesystem_path(resource or "", cwd)
        cwd = canonicalize_filesystem_path(cwd or os.getcwd(), None)
    return SecurityAction(
        action_type=action_type,
        framework=framework,
        session_id=session_id,
        turn_id=turn_id,
        tool=tool,
        command=command,
        resource=resource,
        mcp_server=mcp_server,
        cwd=cwd,
    )


def _action_type(
    tool: str | None,
    command: str | None,
    resource: str | None,
    mcp_server: str | None,
    git_command: str | None,
) -> SecurityActionType:
    if mcp_server:
        return SecurityActionType.MCP
    if command and _is_shell_tool(tool):
        if git_command:
            return SecurityActionType.GIT
        return SecurityActionType.SHELL
    if resource and resource.lower().startswith(("http://", "https://")):
        return SecurityActionType.NETWORK
    if resource:
        return SecurityActionType.FILESYSTEM
    return SecurityActionType.TOOL


def canonicalize_filesystem_path(value: str, cwd: str | None) -> str:
    """Normalise un chemin sans exiger que la ressource existe."""
    effective_cwd = cwd or os.getcwd()
    windows = is_windows_path(value, effective_cwd)
    normalized = _lexical_filesystem_path(value, effective_cwd, windows)
    return _resolve_real_path(normalized, windows)


def _lexical_filesystem_path(
    value: str,
    effective_cwd: str,
    windows: bool,
) -> str:
    if windows:
        expanded = _without_windows_device_prefix(ntpath.expanduser(value))
        drive, _ = ntpath.splitdrive(expanded)
        cwd_drive, _ = ntpath.splitdrive(effective_cwd)
        if not drive and expanded.startswith(("\\", "/")) and cwd_drive:
            expanded = f"{cwd_drive}{expanded}"
        elif not ntpath.isabs(expanded):
            expanded = ntpath.join(effective_cwd, expanded)
        return ntpath.normcase(ntpath.normpath(expanded)).replace("\\", "/")

    expanded = os.path.expanduser(value)
    if not posixpath.isabs(expanded):
        expanded = posixpath.join(effective_cwd.replace("\\", "/"), expanded)
    return posixpath.normpath(expanded)


def canonicalize_git_command(command: str, cwd: str | None) -> str:
    """Retourne l'invocation Git utile au matching, sans parser tout le shell."""
    extracted = _git_command(command) or command
    normalized = GIT_COMMAND.sub("git", extracted.strip().strip("\"'"), count=1)
    normalized = _without_git_global_options(normalized)
    return normalized.casefold() if is_windows_path(cwd or os.getcwd()) else normalized


def is_windows_path(*values: str | None) -> bool:
    if os.name == "nt":
        return True
    return any(
        value
        and (
            WINDOWS_DRIVE.match(value) is not None
            or "\\" in value
            or value.startswith("//")
        )
        for value in values
    )


def _git_command(command: str | None) -> str | None:
    if not command:
        return None
    for pattern in GIT_PREFIXES:
        match = pattern.search(command)
        if match:
            return command[match.start("git") :].strip().strip("\"'")
    return None


def _is_shell_tool(tool: str | None) -> bool:
    return tool is None or tool.casefold() in SHELL_TOOLS


def _without_windows_device_prefix(value: str) -> str:
    folded = value.casefold()
    if folded.startswith("\\\\?\\unc\\"):
        return f"\\\\{value[8:]}"
    if folded.startswith("\\\\?\\"):
        return value[4:]
    return value


def _resolve_real_path(value: str, windows: bool) -> str:
    if windows != (os.name == "nt"):
        return value
    try:
        resolved = str(Path(value).resolve(strict=False))
    except (OSError, RuntimeError):
        return value
    return _lexical_filesystem_path(resolved, os.getcwd(), windows)


def _without_git_global_options(command: str) -> str:
    try:
        tokens = shlex.split(command, posix=False)
    except ValueError:
        return command
    if not tokens or tokens[0].casefold() not in {"git", "git.exe"}:
        return command

    index = 1
    while index < len(tokens):
        option = tokens[index].casefold()
        if option in GIT_OPTIONS_WITH_VALUE:
            if index + 1 >= len(tokens):
                return command
            index += 2
            continue
        if option in GIT_FLAG_OPTIONS or option.startswith(GIT_OPTIONS_WITH_ASSIGNMENT):
            index += 1
            continue
        break
    return " ".join(("git", *tokens[index:]))


def _mcp_server(tool: str | None) -> str | None:
    if not isinstance(tool, str) or not tool.startswith("mcp__"):
        return None
    parts = tool.split("__", 2)
    return parts[1] if len(parts) == 3 and parts[1] else None


def _first_text(data: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value:
            return value
    return None
