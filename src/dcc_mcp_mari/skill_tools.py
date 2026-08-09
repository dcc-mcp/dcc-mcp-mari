"""Small reusable adapter between DCC-MCP skill scripts and the Mari bridge."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

from dcc_mcp_core.skill import skill_entry, skill_success

from .bridge import get_bridge

ResultPostprocessor = Callable[[dict[str, Any]], dict[str, Any]]


def bridge_main(
    method: str,
    message: str,
    *,
    postprocess: ResultPostprocessor | None = None,
) -> Callable[..., dict[str, Any]]:
    """Create a decorated tool entry point for one bounded host command."""

    @skill_entry
    def main(**kwargs: Any) -> dict[str, Any]:
        result = get_bridge().call(method, **kwargs)
        if isinstance(result, dict):
            if postprocess is not None:
                result = postprocess(result)
            return skill_success(message, **result)
        return skill_success(message, result=result)

    return main


def wait_for_export_files(result: dict[str, Any]) -> dict[str, Any]:
    """Wait outside Mari's UI thread until a background texture export is durable."""

    planned = result.get("planned_files")
    if not isinstance(planned, dict):
        raise RuntimeError("Mari did not return a valid export plan")
    files = [Path(path) for paths in planned.values() for path in paths]
    if not files:
        raise RuntimeError("Mari could not resolve any export output paths")

    deadline = time.monotonic() + 1_100
    previous: tuple[tuple[int, int], ...] | None = None
    stable_checks = 0
    while time.monotonic() < deadline:
        if all(path.is_file() and path.stat().st_size > 0 for path in files):
            current = tuple((path.stat().st_size, path.stat().st_mtime_ns) for path in files)
            stable_checks = stable_checks + 1 if current == previous else 0
            if stable_checks >= 3:
                completed = dict(result)
                completed["background_export"] = False
                completed["exported_item_count"] = len(planned)
                completed["exported_files"] = [str(path) for path in files]
                return completed
            previous = current
        else:
            previous = None
            stable_checks = 0
        time.sleep(0.5)

    missing = [str(path) for path in files if not path.is_file()]
    raise TimeoutError("Mari texture export did not finish before timeout: %s" % missing)
