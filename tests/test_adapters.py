import pytest

from pathtrace.adapters import available_adapters, get_adapter
from pathtrace.adapters.base import FrameworkAdapter


def test_registry_exposes_supported_adapters():
    assert available_adapters() == ("claude-code", "codex")
    assert isinstance(get_adapter("claude-code"), FrameworkAdapter)
    assert isinstance(get_adapter("codex"), FrameworkAdapter)


def test_registry_rejects_unknown_adapter():
    with pytest.raises(ValueError, match="Framework non supporté"):
        get_adapter("unknown")
