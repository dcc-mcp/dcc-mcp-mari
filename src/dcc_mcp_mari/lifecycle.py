"""Adapter-owned Install SOP compatibility layer pending the shared Core facade."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional

from .__version__ import __version__

SCHEMA_VERSION = "1.0"
MINIMUM_MARI = (5, 0)
MINIMUM_PYTHON = (3, 9)
MINIMUM_CORE = (0, 19, 91)
RECEIPT_RELATIVE = Path(".dcc-mcp/receipts/mari.json")
PYTHON_PROBE = """
import json
import sys
from importlib.metadata import PackageNotFoundError, version

try:
    core_version = version("dcc-mcp-core")
except PackageNotFoundError:
    core_version = None
try:
    import dcc_mcp_mari  # noqa: F401
    adapter_version = version("dcc-mcp-mari")
except (ImportError, PackageNotFoundError):
    adapter_version = None
print(json.dumps({
    "python": sys.version.split()[0],
    "core": core_version,
    "adapter": adapter_version,
}, separators=(",", ":")))
"""

EXIT_OK = 0
EXIT_PREFLIGHT = 10
EXIT_ACQUIRE = 20
EXIT_INSTALL = 30
EXIT_VERIFY = 40
EXIT_REQUIRES_RESTART = 50


@dataclass(frozen=True)
class LifecycleRequest:
    operation: str
    dcc_path: Optional[Path]
    python_path: Path
    script_dir: Optional[Path] = None
    version: str = __version__
    yes: bool = False
    dry_run: bool = False
    json_output: bool = False
    repair: bool = False

    def with_operation(self, operation: str) -> "LifecycleRequest":
        return replace(self, operation=operation)


class LifecycleFailure(RuntimeError):
    def __init__(self, exit_code: int, stage: str, reason: str) -> None:
        super().__init__(reason)
        self.exit_code = exit_code
        self.stage = stage
        self.reason = reason


def _parse_version(value: str) -> tuple[int, ...]:
    match = re.search(r"(\d+)\.(\d+)(?:[^\d]+(\d+))?", value)
    return tuple(int(part) for part in match.groups(default="0")) if match else ()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _receipt_path(script_dir: Path) -> Path:
    return script_dir / RECEIPT_RELATIVE


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=".%s." % path.name, dir=str(path.parent))
    os.close(descriptor)
    temporary = Path(name)
    try:
        temporary.write_bytes(data)
        os.replace(str(temporary), str(path))
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    _atomic_write(path, (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8"))


def _read_receipt(script_dir: Path) -> Optional[dict[str, Any]]:
    path = _receipt_path(script_dir)
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LifecycleFailure(EXIT_PREFLIGHT, "receipt", "Mari receipt is unreadable") from exc
    if not isinstance(value, dict) or value.get("schema_version") != SCHEMA_VERSION:
        raise LifecycleFailure(EXIT_PREFLIGHT, "receipt", "Mari receipt schema is unsupported")
    _validate_receipt(script_dir, value)
    return value


def _safe_receipt_path(script_dir: Path, value: object, label: str) -> Path:
    if not isinstance(value, str) or not value or Path(value).is_absolute():
        raise LifecycleFailure(EXIT_PREFLIGHT, "receipt", "Receipt %s is unsafe" % label)
    root = script_dir.resolve()
    path = (script_dir / value).resolve()
    try:
        inside = os.path.commonpath((str(root), str(path))) == str(root)
    except ValueError:
        inside = False
    if not inside:
        raise LifecycleFailure(EXIT_PREFLIGHT, "receipt", "Receipt %s escapes script dir" % label)
    return path


def _validate_receipt(script_dir: Path, receipt: Mapping[str, Any]) -> None:
    from .install import BOOTSTRAP_FILENAME, PLUGIN_DIRECTORY

    receipt_version = receipt.get("version")
    if (
        receipt.get("adapter") != "mari"
        or not isinstance(receipt_version, str)
        or not _parse_version(receipt_version)
    ):
        raise LifecycleFailure(EXIT_PREFLIGHT, "receipt", "Mari receipt owner is unsupported")
    backup = receipt.get("backup")
    files = receipt.get("managed_files")
    if not isinstance(backup, dict) or not isinstance(files, list):
        raise LifecycleFailure(EXIT_PREFLIGHT, "receipt", "Mari receipt structure is invalid")
    backup_root = _safe_receipt_path(script_dir, backup.get("root"), "backup root")
    if backup_root.parent != (script_dir / ".dcc-mcp" / "backups").resolve():
        raise LifecycleFailure(EXIT_PREFLIGHT, "receipt", "Receipt backup root is unmanaged")
    if not isinstance(backup.get("plugin"), bool) or not isinstance(backup.get("bootstrap"), bool):
        raise LifecycleFailure(EXIT_PREFLIGHT, "receipt", "Receipt backup flags are invalid")
    if backup["plugin"] and not (backup_root / PLUGIN_DIRECTORY).is_dir():
        raise LifecycleFailure(EXIT_PREFLIGHT, "receipt", "Receipt plugin backup is missing")
    if backup["bootstrap"] and not (backup_root / BOOTSTRAP_FILENAME).is_file():
        raise LifecycleFailure(EXIT_PREFLIGHT, "receipt", "Receipt bootstrap backup is missing")
    seen: set[str] = set()
    for record in files:
        if not isinstance(record, dict):
            raise LifecycleFailure(EXIT_PREFLIGHT, "receipt", "Receipt file entry is invalid")
        relative = record.get("path")
        if not isinstance(relative, str) or relative in seen:
            raise LifecycleFailure(EXIT_PREFLIGHT, "receipt", "Receipt file path is invalid")
        seen.add(relative)
        path = _safe_receipt_path(script_dir, relative, "managed file")
        allowed = relative == BOOTSTRAP_FILENAME or relative.startswith("%s/" % PLUGIN_DIRECTORY)
        if not allowed or path.is_symlink():
            raise LifecycleFailure(EXIT_PREFLIGHT, "receipt", "Receipt owns an unexpected path")
        if not re.fullmatch(r"[0-9a-f]{64}", str(record.get("sha256", ""))):
            raise LifecycleFailure(EXIT_PREFLIGHT, "receipt", "Receipt file digest is invalid")


def _owned_paths(script_dir: Path) -> tuple[Path, Path]:
    from .install import BOOTSTRAP_FILENAME, PLUGIN_DIRECTORY

    return script_dir / PLUGIN_DIRECTORY, script_dir / BOOTSTRAP_FILENAME


def _managed_files(script_dir: Path) -> list[dict[str, str]]:
    plugin, bootstrap = _owned_paths(script_dir)
    paths = [bootstrap]
    if plugin.is_dir():
        paths.extend(path for path in sorted(plugin.rglob("*")) if path.is_file())
    return [
        {"path": path.relative_to(script_dir).as_posix(), "sha256": _sha256(path)}
        for path in paths
        if path.is_file()
    ]


def _backup_existing(script_dir: Path) -> dict[str, Any]:
    plugin, bootstrap = _owned_paths(script_dir)
    backup_root = script_dir / ".dcc-mcp" / "backups" / uuid.uuid4().hex
    record: dict[str, Any] = {
        "root": backup_root.relative_to(script_dir).as_posix(),
        "plugin": plugin.is_dir(),
        "bootstrap": bootstrap.is_file(),
    }
    if record["plugin"]:
        backup_root.mkdir(parents=True, exist_ok=True)
        shutil.copytree(plugin, backup_root / plugin.name)
    if record["bootstrap"]:
        backup_root.mkdir(parents=True, exist_ok=True)
        shutil.copy2(bootstrap, backup_root / bootstrap.name)
    return record


def _remove_owned(script_dir: Path) -> None:
    plugin, bootstrap = _owned_paths(script_dir)
    if plugin.exists():
        shutil.rmtree(plugin)
    bootstrap.unlink(missing_ok=True)


def _restore_backup(script_dir: Path, backup: Mapping[str, Any]) -> None:
    plugin, bootstrap = _owned_paths(script_dir)
    root = script_dir / str(backup.get("root", ""))
    _remove_owned(script_dir)
    if backup.get("plugin"):
        shutil.copytree(root / plugin.name, plugin)
    if backup.get("bootstrap"):
        shutil.copy2(root / bootstrap.name, bootstrap)


def _remove_backup(script_dir: Path, backup: Mapping[str, Any]) -> None:
    root = script_dir / str(backup.get("root", ""))
    if root.is_dir():
        shutil.rmtree(root)


def _installation_state(script_dir: Path, receipt: Optional[Mapping[str, Any]]) -> tuple[str, str]:
    plugin, bootstrap = _owned_paths(script_dir)
    if receipt is None:
        if plugin.exists() or bootstrap.exists():
            return "partial", "Mari startup files exist without an install receipt"
        return "not_installed", "Mari startup plugin is not installed"
    for record in receipt.get("managed_files", []):
        path = script_dir / str(record.get("path", ""))
        if not path.is_file() or _sha256(path) != record.get("sha256"):
            return "partial", "Receipt-managed Mari startup files are missing or changed"
    return "installed", "Mari startup files match the install receipt"


def _resolve_dcc_path(override: Optional[Path]) -> Optional[Path]:
    candidate = override.expanduser() if override is not None else None
    if candidate is None:
        discovered = shutil.which("Mari") or shutil.which("mari")
        if discovered:
            candidate = Path(discovered)
        elif sys.platform == "darwin":
            bundles = sorted(Path("/Applications").glob("Mari*.app"), reverse=True)
            candidate = bundles[0] if bundles else None
        elif os.name == "nt":
            foundry = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Foundry"
            candidates = sorted(
                (*foundry.glob("Mari*/Bundle/bin/Mari*.exe"), *foundry.glob("Mari*/bin/Mari*.exe")),
                reverse=True,
            )
            candidate = candidates[0] if candidates else None
        else:
            candidates = sorted(
                (
                    *Path("/usr/local").glob("Mari*/bin/Mari*"),
                    *Path("/opt/Foundry").glob("Mari*/bin/Mari*"),
                ),
                reverse=True,
            )
            candidate = candidates[0] if candidates else None
    if candidate is not None and candidate.suffix.lower() == ".app":
        candidate = candidate / "Contents" / "MacOS" / "Mari"
    return candidate.resolve() if candidate is not None and candidate.is_file() else None


def _preflight(request: LifecycleRequest) -> tuple[Path, dict[str, Any]]:
    from .install import default_script_dir

    if request.operation not in {"install", "status", "verify", "uninstall", "upgrade"}:
        raise LifecycleFailure(EXIT_PREFLIGHT, "operation", "Unsupported lifecycle operation")
    if request.version != __version__:
        raise LifecycleFailure(EXIT_PREFLIGHT, "version", "A fixed adapter version is required")
    dcc_path = _resolve_dcc_path(request.dcc_path)
    if dcc_path is None:
        raise LifecycleFailure(
            EXIT_PREFLIGHT, "host", "Mari was not detected; use --dcc-path to name its executable"
        )
    try:
        completed = subprocess.run(
            [str(dcc_path), "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise LifecycleFailure(EXIT_PREFLIGHT, "host", "Could not execute Mari --version") from exc
    mari_version = _parse_version(completed.stdout if completed.returncode == 0 else "")
    if mari_version < MINIMUM_MARI:
        raise LifecycleFailure(EXIT_PREFLIGHT, "host", "Mari 5.0+ is required")
    python_path = request.python_path.expanduser().resolve()
    if not python_path.is_file():
        raise LifecycleFailure(EXIT_PREFLIGHT, "python", "--python must name an interpreter")
    try:
        completed = subprocess.run(
            [str(python_path), "-c", PYTHON_PROBE],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise LifecycleFailure(
            EXIT_PREFLIGHT, "python", "Could not execute installer Python"
        ) from exc
    if completed.returncode != 0:
        raise LifecycleFailure(EXIT_PREFLIGHT, "python", "Selected Python environment probe failed")
    try:
        probe = json.loads(completed.stdout)
    except json.JSONDecodeError:
        probe = None
    if not isinstance(probe, dict):
        raise LifecycleFailure(
            EXIT_PREFLIGHT, "python", "Selected Python environment probe returned invalid JSON"
        )
    python_version = _parse_version(str(probe.get("python", "")))
    core_version = probe.get("core")
    adapter_version = probe.get("adapter")
    if python_version < MINIMUM_PYTHON:
        raise LifecycleFailure(EXIT_PREFLIGHT, "python", "Installer Python 3.9+ is required")
    if not isinstance(core_version, str):
        raise LifecycleFailure(
            EXIT_PREFLIGHT, "core", "dcc-mcp-core is not installed in the selected Python"
        )
    if _parse_version(core_version) < MINIMUM_CORE:
        raise LifecycleFailure(EXIT_PREFLIGHT, "core", "dcc-mcp-core 0.19.91+ is required")
    if adapter_version != request.version:
        raise LifecycleFailure(
            EXIT_PREFLIGHT,
            "adapter",
            "The selected Python must import the requested dcc-mcp-mari version",
        )
    script_dir = (request.script_dir or default_script_dir()).expanduser().resolve()
    return script_dir, {
        "adapter_version": request.version,
        "core_version": core_version,
        "mari_version": ".".join(str(part) for part in mari_version),
        "dcc_path": str(dcc_path),
        "installer_python": str(python_path),
        "installer_python_version": ".".join(str(part) for part in python_version),
        "host_python": "embedded:mari",
        "minimum_core_version": ".".join(str(part) for part in MINIMUM_CORE),
        "minimum_mari_version": ".".join(str(part) for part in MINIMUM_MARI),
        "minimum_python_version": ".".join(str(part) for part in MINIMUM_PYTHON),
        "script_dir": str(script_dir),
    }


def _next_step(request: LifecycleRequest, detected: Mapping[str, Any]) -> dict[str, Any]:
    command = [
        "dcc-mcp-mari",
        "verify",
        "--dcc-path",
        str(detected["dcc_path"]),
        "--python",
        str(detected["installer_python"]),
        "--script-dir",
        str(detected["script_dir"]),
        "--json",
    ]
    return {
        "id": "restart-mari-and-verify",
        "description": "Restart Mari so its startup script loads, then verify readiness.",
        "command": command,
        "why": "Mari loads user startup scripts only during host startup.",
    }


def _bootstrap_error_path() -> Path:
    configured = os.environ.get("DCC_MCP_MARI_BOOTSTRAP_ERRORS")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path.home().joinpath(".dcc-mcp", "mari-bootstrap-errors.jsonl").resolve()


def _bootstrap_error_since_install(receipt: Mapping[str, Any]) -> Optional[dict[str, str]]:
    path = _bootstrap_error_path()
    if not path.is_file():
        return None
    try:
        installed_at = datetime.fromisoformat(str(receipt.get("installed_at", "")))
        with path.open("rb") as stream:
            stream.seek(0, os.SEEK_END)
            size = stream.tell()
            stream.seek(max(0, size - 64 * 1024))
            lines = stream.read().splitlines()
        for line in reversed(lines):
            value = json.loads(line.decode("utf-8"))
            if not isinstance(value, dict):
                continue
            timestamp = datetime.fromisoformat(str(value.get("timestamp", "")))
            if timestamp < installed_at:
                return None
            return {
                "timestamp": timestamp.isoformat(),
                "stage": str(value.get("stage", "unknown"))[:128],
                "error_type": str(value.get("error_type", "unknown"))[:128],
                "message": str(value.get("message", ""))[:1000],
                "python_version": str(value.get("python_version", ""))[:128],
            }
    except (OSError, TypeError, UnicodeError, json.JSONDecodeError, ValueError):
        return None
    return None


def _result(
    request: LifecycleRequest,
    *,
    status: str,
    exit_code: int,
    stage: str,
    reason: str,
    script_dir: Optional[Path] = None,
    detected: Optional[Mapping[str, Any]] = None,
    directly_usable: bool = False,
    next_steps: Optional[list[Mapping[str, Any]]] = None,
) -> dict[str, Any]:
    receipt = _receipt_path(script_dir) if script_dir is not None else None
    return {
        "schema_version": SCHEMA_VERSION,
        "operation": request.operation,
        "status": status,
        "exit_code": exit_code,
        "dcc_type": "mari",
        "adapter_version": request.version,
        "core_version": (detected or {}).get("core_version"),
        "steps": [],
        "next_steps": list(next_steps or []),
        "receipt_path": str(receipt) if receipt is not None else None,
        "verify": {
            "directly_usable": directly_usable,
            "failure_stage": None if directly_usable else stage,
            "failure_reason": None if directly_usable else reason,
        },
        "detected": dict(detected or {}),
        "stage": stage,
        "reason": reason,
    }


def _assert_unlocked(script_dir: Path) -> None:
    from dcc_mcp_core.install_lifecycle import inspect_install_root

    inspection = inspect_install_root(script_dir)
    if inspection.get("requires_restart"):
        raise LifecycleFailure(
            EXIT_REQUIRES_RESTART,
            "locked_files",
            "Mari startup files are loaded; close Mari and retry",
        )


def _wait_for_live_sidecar() -> Mapping[str, Any]:
    from dcc_mcp_core.install_lifecycle import wait_for_sidecar_ready

    result = wait_for_sidecar_ready(
        dcc_type="mari",
        timeout_secs=5.0,
        probe_tool="ping",
        probe_arguments={},
        probe_timeout_secs=3.0,
    )
    if not isinstance(result, Mapping):
        raise RuntimeError("Core returned an invalid Mari readiness result")
    return result


def run_lifecycle(request: LifecycleRequest) -> dict[str, Any]:
    from . import install as legacy

    script_dir: Optional[Path] = None
    detected: dict[str, Any] = {}
    try:
        script_dir, detected = _preflight(request)
        receipt = _read_receipt(script_dir)
        state, reason = _installation_state(script_dir, receipt)
        if request.operation == "status":
            return _result(
                request,
                status=state,
                exit_code=EXIT_OK if state in {"installed", "not_installed"} else EXIT_PREFLIGHT,
                stage="status",
                reason=reason,
                script_dir=script_dir,
                detected=detected,
            )
        if request.operation == "verify":
            if state != "installed":
                return _result(
                    request,
                    status=state,
                    exit_code=EXIT_VERIFY,
                    stage="installation",
                    reason=reason,
                    script_dir=script_dir,
                    detected=detected,
                )
            bootstrap_error = _bootstrap_error_since_install(receipt or {})
            if bootstrap_error is not None:
                detected["bootstrap_error"] = bootstrap_error
                return _result(
                    request,
                    status="installed_not_ready",
                    exit_code=EXIT_VERIFY,
                    stage="bootstrap",
                    reason="Mari recorded a plugin bootstrap failure after installation",
                    script_dir=script_dir,
                    detected=detected,
                    next_steps=[_next_step(request, detected)],
                )
            try:
                sidecar = _wait_for_live_sidecar()
            except (ImportError, OSError, RuntimeError, ValueError) as exc:
                sidecar = {"success": False, "ready": False, "message": str(exc)}
            detected["sidecar"] = dict(sidecar)
            if sidecar.get("success") and sidecar.get("ready"):
                return _result(
                    request,
                    status="ready",
                    exit_code=EXIT_OK,
                    stage="verify",
                    reason="Mari plugin and sidecar are ready",
                    script_dir=script_dir,
                    detected=detected,
                    directly_usable=True,
                )
            return _result(
                request,
                status="installed_not_ready",
                exit_code=EXIT_VERIFY,
                stage="host_readiness",
                reason=str(sidecar.get("message") or "Mari sidecar is not ready"),
                script_dir=script_dir,
                detected=detected,
                next_steps=[_next_step(request, detected)],
            )
        repairable = request.operation in {"install", "upgrade"} and request.repair
        if state == "partial" and not repairable:
            raise LifecycleFailure(EXIT_PREFLIGHT, "partial_install", reason)
        if request.dry_run:
            return _result(
                request,
                status="planned",
                exit_code=EXIT_OK,
                stage="plan",
                reason="Preflight passed; no files were changed",
                script_dir=script_dir,
                detected=detected,
            )
        if not request.yes:
            raise LifecycleFailure(EXIT_PREFLIGHT, "confirmation", "Use --yes to change files")
        if request.operation == "install" and state == "installed" and not request.repair:
            return _result(
                request,
                status="installed",
                exit_code=EXIT_OK,
                stage="install",
                reason="Mari startup files already match the receipt",
                script_dir=script_dir,
                detected=detected,
                next_steps=[_next_step(request, detected)],
            )
        _assert_unlocked(script_dir)
        if request.operation in {"install", "upgrade"}:
            rollback = _backup_existing(script_dir)
            backup = dict(receipt.get("backup", {})) if receipt is not None else rollback
            prior_receipt = _receipt_path(script_dir).read_bytes() if receipt else None
            try:
                legacy.install_plugin(script_dir, overwrite=True)
                payload = {
                    "schema_version": SCHEMA_VERSION,
                    "adapter": "mari",
                    "version": request.version,
                    "installed_at": datetime.now(timezone.utc).isoformat(),
                    "detected": detected,
                    "backup": backup,
                    "managed_files": _managed_files(script_dir),
                }
                _write_json(_receipt_path(script_dir), payload)
            except BaseException:
                _restore_backup(script_dir, rollback)
                _remove_backup(script_dir, rollback)
                if prior_receipt is None:
                    _receipt_path(script_dir).unlink(missing_ok=True)
                else:
                    _atomic_write(_receipt_path(script_dir), prior_receipt)
                raise
            if receipt is not None:
                _remove_backup(script_dir, rollback)
            return _result(
                request,
                status="installed",
                exit_code=EXIT_OK,
                stage="install",
                reason="Mari startup files were installed and recorded",
                script_dir=script_dir,
                detected=detected,
                next_steps=[_next_step(request, detected)],
            )
        if receipt is None:
            return _result(
                request,
                status="not_installed",
                exit_code=EXIT_OK,
                stage="uninstall",
                reason="Mari startup plugin is already absent",
                script_dir=script_dir,
                detected=detected,
            )
        rollback = _backup_existing(script_dir)
        prior_receipt = _receipt_path(script_dir).read_bytes()
        try:
            _restore_backup(script_dir, receipt.get("backup", {}))
            _receipt_path(script_dir).unlink()
        except BaseException:
            _restore_backup(script_dir, rollback)
            _atomic_write(_receipt_path(script_dir), prior_receipt)
            _remove_backup(script_dir, rollback)
            raise
        for obsolete in (rollback, receipt.get("backup", {})):
            try:
                _remove_backup(script_dir, obsolete)
            except OSError:
                pass
        return _result(
            request,
            status="uninstalled",
            exit_code=EXIT_OK,
            stage="uninstall",
            reason="Receipt-owned Mari startup files were removed",
            script_dir=script_dir,
            detected=detected,
        )
    except LifecycleFailure as exc:
        return _result(
            request,
            status="failed",
            exit_code=exc.exit_code,
            stage=exc.stage,
            reason=exc.reason,
            script_dir=script_dir,
            detected=detected,
        )
    except PermissionError:
        return _result(
            request,
            status="requires_restart",
            exit_code=EXIT_REQUIRES_RESTART,
            stage="locked_files",
            reason="Mari startup files are locked; close Mari and retry",
            script_dir=script_dir,
            detected=detected,
        )
    except OSError as exc:
        return _result(
            request,
            status="failed",
            exit_code=EXIT_INSTALL,
            stage="filesystem",
            reason=str(exc),
            script_dir=script_dir,
            detected=detected,
        )
    except RuntimeError as exc:
        return _result(
            request,
            status="failed",
            exit_code=EXIT_INSTALL,
            stage="install",
            reason=str(exc)[:1000],
            script_dir=script_dir,
            detected=detected,
        )
