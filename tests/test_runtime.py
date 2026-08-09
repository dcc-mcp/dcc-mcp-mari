from pathlib import Path
from types import SimpleNamespace

from dcc_mcp_mari.mari_plugin.runtime import PluginRuntime


class _Commands:
    def execute(self, method, params):
        return {"method": method, "params": params}


def _runtime(tmp_path: Path) -> PluginRuntime:
    runtime = PluginRuntime(SimpleNamespace(), tmp_path)
    runtime._token = "secret"
    runtime._commands = _Commands()
    return runtime


def test_runtime_rejects_invalid_token(tmp_path):
    runtime = _runtime(tmp_path)
    request = {
        "jsonrpc": "2.0",
        "token": "wrong",
        "method": "diagnostics.ping",
        "params": {},
    }

    try:
        runtime._execute_request(request)
    except PermissionError as exc:
        assert "token" in str(exc)
    else:
        raise AssertionError("invalid token was accepted")


def test_runtime_dispatches_only_valid_json_rpc_objects(tmp_path):
    runtime = _runtime(tmp_path)
    response = runtime._execute_request(
        {
            "jsonrpc": "2.0",
            "token": "secret",
            "method": "project.inspect",
            "params": {"value": 1},
        }
    )

    assert response == {"result": {"method": "project.inspect", "params": {"value": 1}}}


def test_runtime_health_uses_host_diagnostics(tmp_path):
    runtime = _runtime(tmp_path)
    response = runtime._execute_request(
        {
            "jsonrpc": "2.0",
            "token": "secret",
            "method": "bridge.health",
            "params": {},
        }
    )

    assert response["result"]["method"] == "diagnostics.ping"
