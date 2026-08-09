"""Install the pure-Python host plugin into Mari's user script directory."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

PLUGIN_DIRECTORY = "dcc_mcp_mari_host"
BOOTSTRAP_FILENAME = "dcc_mcp_mari_bootstrap.py"


def default_script_dir() -> Path:
    """Return Mari's documented per-user scripts directory."""
    if sys.platform == "win32":
        return Path.home() / "Documents" / "Mari" / "Scripts"
    return Path.home() / "Mari" / "Scripts"


def install_plugin(script_dir: Path, *, overwrite: bool = False) -> Path:
    """Copy the host plugin and bind it to this environment's console script."""
    root = script_dir.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    target = root / PLUGIN_DIRECTORY
    bootstrap = root / BOOTSTRAP_FILENAME
    existing = [path for path in (target, bootstrap) if path.exists()]
    if existing and not overwrite:
        raise FileExistsError("Mari plugin already exists: %s" % existing[0])
    if target.exists():
        shutil.rmtree(target)
    if bootstrap.exists():
        bootstrap.unlink()

    package_root = Path(__file__).resolve().parent
    shutil.copytree(
        package_root / "mari_plugin",
        target,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    shutil.copy2(package_root / "mari_bootstrap.py", bootstrap)
    executable = _find_server_executable()
    if executable is None:
        shutil.rmtree(target)
        bootstrap.unlink(missing_ok=True)
        raise RuntimeError("dcc-mcp-mari executable was not found in this Python environment")
    (target / "server_path.txt").write_text(str(executable), encoding="utf-8")
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
