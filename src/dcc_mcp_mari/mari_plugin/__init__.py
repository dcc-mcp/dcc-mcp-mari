"""Pure-Python package copied into Mari's script path by the installer."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .runtime import PluginRuntime

_runtime: PluginRuntime | None = None


def start(mari_module: Any | None = None) -> PluginRuntime:
    """Start at most one bridge runtime inside the current Mari process."""
    global _runtime
    if _runtime is not None and _runtime.running:
        return _runtime
    if _runtime is not None:
        _runtime.stop()
    if mari_module is None:
        import mari as mari_module

    _runtime = PluginRuntime(mari_module, Path(__file__).resolve().parent)
    _runtime.start()
    return _runtime


def stop() -> None:
    global _runtime
    if _runtime is not None:
        _runtime.stop()
        _runtime = None
