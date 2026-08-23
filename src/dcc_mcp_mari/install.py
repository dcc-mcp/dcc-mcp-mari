"""Install the pure-Python host plugin into Mari's user script directory."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import uuid
from pathlib import Path

PLUGIN_DIRECTORY = "dcc_mcp_mari_host"
BOOTSTRAP_FILENAME = "dcc_mcp_mari_bootstrap.py"


def default_script_dir() -> Path:
    """Return Mari's documented per-user scripts directory."""
    if sys.platform == "win32":
        return Path.home() / "Documents" / "Mari" / "Scripts"
    return Path.home() / "Mari" / "Scripts"


def install_plugin(script_dir: Path, *, overwrite: bool = False) -> Path:
    """Stage and atomically promote the host plugin and startup script."""
    root = script_dir.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    target = root / PLUGIN_DIRECTORY
    bootstrap = root / BOOTSTRAP_FILENAME
    existing = [path for path in (target, bootstrap) if path.exists()]
    if existing and not overwrite:
        raise FileExistsError("Mari plugin already exists: %s" % existing[0])
    executable = _find_server_executable()
    if executable is None:
        raise RuntimeError("dcc-mcp-mari executable was not found in this Python environment")

    package_root = Path(__file__).resolve().parent
    suffix = uuid.uuid4().hex
    target_backup = root / (".%s.backup-%s" % (PLUGIN_DIRECTORY, suffix))
    bootstrap_backup = root / (".%s.backup-%s" % (BOOTSTRAP_FILENAME, suffix))
    with tempfile.TemporaryDirectory(prefix=".dcc-mcp-mari-install-", dir=str(root)) as temp:
        staging = Path(temp)
        staged_target = staging / PLUGIN_DIRECTORY
        staged_bootstrap = staging / BOOTSTRAP_FILENAME
        shutil.copytree(
            package_root / "mari_plugin",
            staged_target,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        shutil.copy2(package_root / "mari_bootstrap.py", staged_bootstrap)
        (staged_target / "server_path.txt").write_text(str(executable), encoding="utf-8")

        moved_target = False
        moved_bootstrap = False
        try:
            if target.exists():
                os.replace(str(target), str(target_backup))
                moved_target = True
            if bootstrap.exists():
                os.replace(str(bootstrap), str(bootstrap_backup))
                moved_bootstrap = True
            os.replace(str(staged_target), str(target))
            os.replace(str(staged_bootstrap), str(bootstrap))
        except BaseException:
            if target.exists():
                shutil.rmtree(target)
            bootstrap.unlink(missing_ok=True)
            if moved_target and target_backup.exists():
                os.replace(str(target_backup), str(target))
            if moved_bootstrap and bootstrap_backup.exists():
                os.replace(str(bootstrap_backup), str(bootstrap))
            raise
        else:
            if target_backup.exists():
                shutil.rmtree(target_backup)
            bootstrap_backup.unlink(missing_ok=True)
    return target


def uninstall_plugin(script_dir: Path) -> bool:
    """Remove only the two paths owned by this package."""
    root = script_dir.expanduser().resolve()
    target = root / PLUGIN_DIRECTORY
    bootstrap = root / BOOTSTRAP_FILENAME
    removed = False
    if target.is_dir():
        shutil.rmtree(target)
        removed = True
    if bootstrap.is_file():
        bootstrap.unlink()
        removed = True
    return removed


def _find_server_executable() -> Path | None:
    scripts_dir = Path(sys.executable).resolve().parent
    candidate = scripts_dir / ("dcc-mcp-mari.exe" if sys.platform == "win32" else "dcc-mcp-mari")
    if candidate.is_file():
        return candidate.resolve()
    resolved = shutil.which("dcc-mcp-mari")
    return Path(resolved).resolve() if resolved else None


from .lifecycle import LifecycleRequest, run_lifecycle  # noqa: E402,F401
