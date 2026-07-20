"""Registre des adaptateurs disponibles."""

from __future__ import annotations

from pathtrace.adapters.base import FrameworkAdapter
from pathtrace.adapters.codex import CodexAdapter


_ADAPTERS: dict[str, FrameworkAdapter] = {
    "codex": CodexAdapter(),
}


def available_adapters() -> tuple[str, ...]:
    return tuple(sorted(_ADAPTERS))


def get_adapter(name: str) -> FrameworkAdapter:
    try:
        return _ADAPTERS[name]
    except KeyError as error:
        supported = ", ".join(available_adapters())
        raise ValueError(f"Framework non supporté : {name}. Disponibles : {supported}") from error
