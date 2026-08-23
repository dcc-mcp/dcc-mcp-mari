import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

from dcc_mcp_mari import install


def test_install_and_uninstall_copy_only_owned_plugin_paths(tmp_path, monkeypatch):
    executable = tmp_path / "dcc-mcp-mari"
    executable.touch()
    scripts = tmp_path / "Mari" / "Scripts"
    unrelated = scripts / "artist_script.py"
    unrelated.parent.mkdir(parents=True)
    unrelated.write_text("keep", encoding="utf-8")
    monkeypatch.setattr(install, "_find_server_executable", lambda: executable)

    target = install.install_plugin(scripts)

    assert target == scripts / "dcc_mcp_mari_host"
    assert (target / "runtime.py").is_file()
    assert (target / "commands.py").is_file()
    assert (target / "server_path.txt").read_text(encoding="utf-8") == str(executable)
    assert (scripts / "dcc_mcp_mari_bootstrap.py").is_file()
    assert unrelated.is_file()
    with pytest.raises(FileExistsError):
        install.install_plugin(scripts)

    assert install.uninstall_plugin(scripts) is True
    assert unrelated.read_text(encoding="utf-8") == "keep"
    assert install.uninstall_plugin(scripts) is False


def test_failed_install_rolls_back_owned_paths(tmp_path, monkeypatch):
    scripts = tmp_path / "Scripts"
    monkeypatch.setattr(install, "_find_server_executable", lambda: None)

    with pytest.raises(RuntimeError, match="executable"):
        install.install_plugin(scripts)

    assert not (scripts / "dcc_mcp_mari_host").exists()
    assert not (scripts / "dcc_mcp_mari_bootstrap.py").exists()


def test_overwrite_stages_before_preserving_previous_plugin(tmp_path, monkeypatch):
    scripts = tmp_path / "Scripts"
    plugin = scripts / "dcc_mcp_mari_host"
    plugin.mkdir(parents=True)
    marker = plugin / "previous.txt"
    marker.write_text("previous", encoding="utf-8")
    bootstrap = scripts / "dcc_mcp_mari_bootstrap.py"
    bootstrap.write_text("previous bootstrap\n", encoding="utf-8")
    executable = tmp_path / "dcc-mcp-mari"
    executable.touch()
    monkeypatch.setattr(install, "_find_server_executable", lambda: executable)
    monkeypatch.setattr(
        install.shutil,
        "copytree",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("staging failed")),
    )

    with pytest.raises(OSError, match="staging failed"):
        install.install_plugin(scripts, overwrite=True)

    assert marker.read_text(encoding="utf-8") == "previous"
    assert bootstrap.read_text(encoding="utf-8") == "previous bootstrap\n"


def test_bootstrap_captures_plugin_start_failure(tmp_path, monkeypatch):
    error_log = tmp_path / "bootstrap-errors.jsonl"
    monkeypatch.setenv("DCC_MCP_MARI_BOOTSTRAP_ERRORS", str(error_log))
    host_module = types.ModuleType("dcc_mcp_mari_host")
    host_module.start = lambda: (_ for _ in ()).throw(RuntimeError("plugin startup failed"))
    monkeypatch.setitem(sys.modules, "dcc_mcp_mari_host", host_module)
    bootstrap = Path(install.__file__).resolve().parent / "mari_bootstrap.py"
    spec = importlib.util.spec_from_file_location("_dcc_mcp_mari_bootstrap_test", bootstrap)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)

    with pytest.raises(RuntimeError, match="plugin startup failed"):
        spec.loader.exec_module(module)

    event = json.loads(error_log.read_text(encoding="utf-8"))
    assert event["stage"] == "plugin_start"
    assert event["error_type"] == "RuntimeError"
