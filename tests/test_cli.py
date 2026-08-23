from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("operation", ["install", "status", "verify", "uninstall", "upgrade"])
def test_standard_lifecycle_cli_accepts_uniform_flags_and_returns_result_exit_code(
    operation: str, tmp_path: Path, monkeypatch, capsys
) -> None:
    import dcc_mcp_mari.server as server

    observed = {}

    def run_lifecycle(request):
        observed["request"] = request
        return {
            "schema_version": "1.0",
            "operation": request.operation,
            "status": "planned",
            "exit_code": 40,
            "next_steps": [],
        }

    monkeypatch.setattr(server, "run_lifecycle", run_lifecycle, raising=False)
    dcc_path = tmp_path / "Mari.exe"
    script_dir = tmp_path / "Mari" / "Scripts"

    exit_code = server.main(
        [
            operation,
            "--json",
            "--yes",
            "--dry-run",
            "--repair",
            "--dcc-path",
            str(dcc_path),
            "--python",
            sys.executable,
            "--script-dir",
            str(script_dir),
        ]
    )

    request = observed["request"]
    assert request.operation == operation
    assert request.dcc_path == dcc_path
    assert request.python_path == Path(sys.executable)
    assert request.script_dir == script_dir
    assert request.json_output is True
    assert request.yes is True
    assert request.dry_run is True
    assert request.repair is True
    assert exit_code == 40
    assert json.loads(capsys.readouterr().out)["operation"] == operation
