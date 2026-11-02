from pathlib import Path
import os


def provider_home(framework: str) -> Path:
    names = {"codex": ("CODEX_HOME", ".codex"),
             "claude-code": ("CLAUDE_CONFIG_DIR", ".claude")}
    variable, directory = names[framework]
    configured = os.getenv(variable)
    return Path(configured).expanduser() if configured else Path.home() / directory


def provider_security_path(framework: str) -> Path:
    return provider_home(framework) / "pathtrace" / "security.yaml"
