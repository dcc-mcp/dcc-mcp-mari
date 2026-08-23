from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path


class _Probe:
    def __init__(self, stdout: str, returncode: int = 0) -> None:
        self.stdout = stdout
        self.returncode = returncode


def _successful_probe(command, **_kwargs):
    from dcc_mcp_mari.__version__ import __version__

    if "--version" in command:
        return _Probe("Mari 7.5v2\n")
    return _Probe(
        json.dumps(
            {
                "python": sys.version.split()[0],
                "core": "0.19.91",
                "adapter": __version__,
            }
        )
    )


def test_standard_lifecycle_round_trip_writes_and_consumes_receipt(
    tmp_path: Path, monkeypatch
) -> None:
    import dcc_mcp_mari.install as installer
    from dcc_mcp_mari.install import LifecycleRequest, run_lifecycle

    monkeypatch.setattr(subprocess, "run", _successful_probe)
    server = tmp_path / "bin" / "dcc-mcp-mari.exe"
    server.parent.mkdir()
    server.touch()
    monkeypatch.setattr(installer, "_find_server_executable", lambda: server)
    dcc_path = tmp_path / "Mari7.5.exe"
    dcc_path.touch()
    script_dir = tmp_path / "Mari" / "Scripts"
    request = LifecycleRequest(
        operation="install",
        dcc_path=dcc_path,
        python_path=Path(sys.executable),
        script_dir=script_dir,
        yes=True,
    )

    planned = run_lifecycle(replace(request, dry_run=True))

    assert planned["exit_code"] == 0
    assert planned["status"] == "planned"
    assert not (script_dir / "dcc_mcp_mari_host").exists()

    installed = run_lifecycle(request)
    receipt = Path(str(installed["receipt_path"]))

    assert installed["exit_code"] == 0
    assert receipt.is_file()
    assert run_lifecycle(request.with_operation("status"))["status"] == "installed"
    assert run_lifecycle(request.with_operation("uninstall"))["exit_code"] == 0
    assert not receipt.exists()
    assert not (script_dir / "dcc_mcp_mari_host").exists()
    assert not (script_dir / "dcc_mcp_mari_bootstrap.py").exists()


def test_uninstall_rejects_receipt_paths_outside_script_dir(tmp_path: Path, monkeypatch) -> None:
    import dcc_mcp_mari.install as installer
    from dcc_mcp_mari.install import LifecycleRequest, run_lifecycle

    monkeypatch.setattr(subprocess, "run", _successful_probe)
    server = tmp_path / "bin" / "dcc-mcp-mari.exe"
    server.parent.mkdir()
    server.touch()
    monkeypatch.setattr(installer, "_find_server_executable", lambda: server)
    dcc_path = tmp_path / "Mari7.5.exe"
    dcc_path.touch()
    script_dir = tmp_path / "Mari" / "Scripts"
    request = LifecycleRequest(
        operation="install",
        dcc_path=dcc_path,
        python_path=Path(sys.executable),
        script_dir=script_dir,
        yes=True,
    )
    assert run_lifecycle(request)["exit_code"] == 0
    victim = tmp_path / "victim"
    victim.mkdir()
    (victim / "keep.txt").write_text("keep", encoding="utf-8")
    receipt = script_dir / ".dcc-mcp" / "receipts" / "mari.json"
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    payload["backup"]["root"] = Path(os.path.relpath(victim, script_dir)).as_posix()
    receipt.write_text(json.dumps(payload), encoding="utf-8")

    result = run_lifecycle(request.with_operation("uninstall"))

    assert result["exit_code"] == 10
    assert result["stage"] == "receipt"
    assert (victim / "keep.txt").read_text(encoding="utf-8") == "keep"


def test_preflight_checks_core_in_selected_python(tmp_path: Path, monkeypatch) -> None:
    import dcc_mcp_mari.install as installer
    from dcc_mcp_mari.install import LifecycleRequest, run_lifecycle

    def probe(command, **_kwargs):
        if "--version" in command:
            return _Probe("Mari 7.5v2\n")
        return _Probe(json.dumps({"python": "3.12.1", "core": None, "adapter": "0.2.1"}))

    monkeypatch.setattr(subprocess, "run", probe)
    server = tmp_path / "bin" / "dcc-mcp-mari.exe"
    server.parent.mkdir()
    server.touch()
    monkeypatch.setattr(installer, "_find_server_executable", lambda: server)
    dcc_path = tmp_path / "Mari7.5.exe"
    dcc_path.touch()
    request = LifecycleRequest(
        operation="install",
        dcc_path=dcc_path,
        python_path=Path(sys.executable),
        script_dir=tmp_path / "Mari" / "Scripts",
        yes=True,
    )

    result = run_lifecycle(request)

    assert result["exit_code"] == 10
    assert result["stage"] == "core"


def test_preflight_rejects_non_json_selected_python_probe(tmp_path: Path, monkeypatch) -> None:
    import dcc_mcp_mari.install as installer
    from dcc_mcp_mari.install import LifecycleRequest, run_lifecycle

    def probe(command, **_kwargs):
        if "--version" in command:
            return _Probe("Mari 7.5v2\n")
        return _Probe("Python 3.12.1\n")

    monkeypatch.setattr(subprocess, "run", probe)
    server = tmp_path / "bin" / "dcc-mcp-mari.exe"
    server.parent.mkdir()
    server.touch()
    monkeypatch.setattr(installer, "_find_server_executable", lambda: server)
    dcc_path = tmp_path / "Mari7.5.exe"
    dcc_path.touch()
    request = LifecycleRequest(
        operation="status",
        dcc_path=dcc_path,
        python_path=Path(sys.executable),
        script_dir=tmp_path / "Mari" / "Scripts",
    )

    result = run_lifecycle(request)

    assert result["exit_code"] == 10
    assert result["stage"] == "python"


def test_preflight_detects_mari_from_path_without_override(tmp_path: Path, monkeypatch) -> None:
    import dcc_mcp_mari.install as installer
    import dcc_mcp_mari.lifecycle as lifecycle
    from dcc_mcp_mari.install import LifecycleRequest, run_lifecycle

    dcc_path = tmp_path / "bin" / "Mari"
    dcc_path.parent.mkdir()
    dcc_path.touch()
    monkeypatch.setattr(lifecycle.shutil, "which", lambda _name: str(dcc_path))
    monkeypatch.setattr(subprocess, "run", _successful_probe)
    server = tmp_path / "bin" / "dcc-mcp-mari.exe"
    server.touch()
    monkeypatch.setattr(installer, "_find_server_executable", lambda: server)
    request = LifecycleRequest(
        operation="install",
        dcc_path=None,
        python_path=Path(sys.executable),
        script_dir=tmp_path / "Mari" / "Scripts",
        yes=True,
    )

    result = run_lifecycle(request)

    assert result["exit_code"] == 0
    assert result["detected"]["dcc_path"] == str(dcc_path.resolve())
    assert result["next_steps"][0]["command"][3] == str(dcc_path.resolve())


def test_verify_requires_receipt_and_live_sidecar_readiness(tmp_path: Path, monkeypatch) -> None:
    import dcc_mcp_core.install_lifecycle as core_lifecycle

    import dcc_mcp_mari.install as installer
    from dcc_mcp_mari.install import LifecycleRequest, run_lifecycle

    monkeypatch.setattr(subprocess, "run", _successful_probe)
    server = tmp_path / "bin" / "dcc-mcp-mari.exe"
    server.parent.mkdir()
    server.touch()
    monkeypatch.setattr(installer, "_find_server_executable", lambda: server)
    observed = {}

    def wait_for_sidecar_ready(**kwargs):
        observed.update(kwargs)
        return {"success": True, "ready": True, "status": "ready"}

    monkeypatch.setattr(core_lifecycle, "wait_for_sidecar_ready", wait_for_sidecar_ready)
    dcc_path = tmp_path / "Mari7.5.exe"
    dcc_path.touch()
    request = LifecycleRequest(
        operation="install",
        dcc_path=dcc_path,
        python_path=Path(sys.executable),
        script_dir=tmp_path / "Mari" / "Scripts",
        yes=True,
    )
    assert run_lifecycle(request)["exit_code"] == 0

    result = run_lifecycle(request.with_operation("verify"))

    assert result["exit_code"] == 0
    assert result["status"] == "ready"
    assert result["verify"]["directly_usable"] is True
    assert result["detected"]["sidecar"]["ready"] is True
    assert observed["probe_tool"] == "ping"


def test_verify_reports_bootstrap_error_recorded_after_install(tmp_path: Path, monkeypatch) -> None:
    import dcc_mcp_core.install_lifecycle as core_lifecycle

    import dcc_mcp_mari.install as installer
    from dcc_mcp_mari.install import LifecycleRequest, run_lifecycle

    monkeypatch.setattr(subprocess, "run", _successful_probe)
    server = tmp_path / "bin" / "dcc-mcp-mari.exe"
    server.parent.mkdir()
    server.touch()
    monkeypatch.setattr(installer, "_find_server_executable", lambda: server)
    monkeypatch.setattr(
        core_lifecycle,
        "wait_for_sidecar_ready",
        lambda **_kwargs: {"success": True, "ready": True, "status": "ready"},
    )
    error_log = tmp_path / "bootstrap-errors.jsonl"
    monkeypatch.setenv("DCC_MCP_MARI_BOOTSTRAP_ERRORS", str(error_log))
    dcc_path = tmp_path / "Mari7.5.exe"
    dcc_path.touch()
    request = LifecycleRequest(
        operation="install",
        dcc_path=dcc_path,
        python_path=Path(sys.executable),
        script_dir=tmp_path / "Mari" / "Scripts",
        yes=True,
    )
    assert run_lifecycle(request)["exit_code"] == 0
    error_log.write_text(
        json.dumps(
            {
                "timestamp": "9999-01-01T00:00:00+00:00",
                "stage": "plugin_start",
                "error_type": "RuntimeError",
                "message": "plugin startup failed",
                "python_version": "3.10.0",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = run_lifecycle(request.with_operation("verify"))

    assert result["exit_code"] == 40
    assert result["stage"] == "bootstrap"
    assert result["detected"]["bootstrap_error"]["stage"] == "plugin_start"


def test_upgrade_accepts_receipt_from_an_older_adapter_version(tmp_path: Path, monkeypatch) -> None:
    import dcc_mcp_mari.install as installer
    from dcc_mcp_mari.install import LifecycleRequest, run_lifecycle

    monkeypatch.setattr(subprocess, "run", _successful_probe)
    server = tmp_path / "bin" / "dcc-mcp-mari.exe"
    server.parent.mkdir()
    server.touch()
    monkeypatch.setattr(installer, "_find_server_executable", lambda: server)
    dcc_path = tmp_path / "Mari7.5.exe"
    dcc_path.touch()
    script_dir = tmp_path / "Mari" / "Scripts"
    request = LifecycleRequest(
        operation="install",
        dcc_path=dcc_path,
        python_path=Path(sys.executable),
        script_dir=script_dir,
        yes=True,
    )
    assert run_lifecycle(request)["exit_code"] == 0
    receipt_path = script_dir / ".dcc-mcp" / "receipts" / "mari.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["version"] = "0.1.0"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    result = run_lifecycle(request.with_operation("upgrade"))

    assert result["exit_code"] == 0
    upgraded = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert upgraded["version"] == request.version


def test_repair_receipt_restores_preexisting_files_on_uninstall(
    tmp_path: Path, monkeypatch
) -> None:
    import dcc_mcp_mari.install as installer
    from dcc_mcp_mari.install import LifecycleRequest, run_lifecycle

    monkeypatch.setattr(subprocess, "run", _successful_probe)
    server = tmp_path / "bin" / "dcc-mcp-mari.exe"
    server.parent.mkdir()
    server.touch()
    monkeypatch.setattr(installer, "_find_server_executable", lambda: server)
    dcc_path = tmp_path / "Mari7.5.exe"
    dcc_path.touch()
    script_dir = tmp_path / "Mari" / "Scripts"
    plugin = script_dir / "dcc_mcp_mari_host"
    plugin.mkdir(parents=True)
    (plugin / "artist.py").write_text("artist plugin\n", encoding="utf-8")
    bootstrap = script_dir / "dcc_mcp_mari_bootstrap.py"
    bootstrap.write_text("artist bootstrap\n", encoding="utf-8")
    request = LifecycleRequest(
        operation="install",
        dcc_path=dcc_path,
        python_path=Path(sys.executable),
        script_dir=script_dir,
        yes=True,
        repair=True,
    )

    installed = run_lifecycle(request)
    uninstalled = run_lifecycle(request.with_operation("uninstall"))

    assert installed["exit_code"] == 0
    assert uninstalled["exit_code"] == 0
    assert (plugin / "artist.py").read_text(encoding="utf-8") == "artist plugin\n"
    assert bootstrap.read_text(encoding="utf-8") == "artist bootstrap\n"


def test_install_runtime_failure_returns_stable_install_exit_code(
    tmp_path: Path, monkeypatch
) -> None:
    import dcc_mcp_mari.install as installer
    from dcc_mcp_mari.install import LifecycleRequest, run_lifecycle

    monkeypatch.setattr(subprocess, "run", _successful_probe)
    monkeypatch.setattr(installer, "_find_server_executable", lambda: None)
    dcc_path = tmp_path / "Mari7.5.exe"
    dcc_path.touch()
    request = LifecycleRequest(
        operation="install",
        dcc_path=dcc_path,
        python_path=Path(sys.executable),
        script_dir=tmp_path / "Mari" / "Scripts",
        yes=True,
    )

    result = run_lifecycle(request)

    assert result["exit_code"] == 30
    assert result["stage"] == "install"
