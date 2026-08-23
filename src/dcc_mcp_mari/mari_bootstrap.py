"""Mari startup script installed into the user's MARI_SCRIPT_PATH."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


def _error_path() -> Path:
    configured = os.environ.get("DCC_MCP_MARI_BOOTSTRAP_ERRORS")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".dcc-mcp" / "mari-bootstrap-errors.jsonl"


def _record(stage: str, error: Exception) -> None:
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "stage": stage,
        "error_type": type(error).__name__,
        "message": str(error)[:1000],
        "python_version": sys.version.split()[0],
    }
    try:
        path = _error_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event, ensure_ascii=True, separators=(",", ":")) + "\n")
    except OSError:
        pass


try:
    from dcc_mcp_mari_host import start
except Exception as error:
    _record("plugin_import", error)
    raise

try:
    start()
except Exception as error:
    _record("plugin_start", error)
    raise
