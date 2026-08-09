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
