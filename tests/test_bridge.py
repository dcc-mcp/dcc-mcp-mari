import json
import socket
import threading

import pytest

from dcc_mcp_mari.bridge import BridgeConfig, BridgeError, MariBridge


def _start_server(response_factory):
    received = {}
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)

    def serve():
        conn, _ = listener.accept()
        with conn:
            request = json.loads(conn.makefile("r", encoding="utf-8").readline())
            received["request"] = request
            response = response_factory(request)
            conn.sendall(json.dumps(response).encode("utf-8") + b"\n")
        listener.close()

    threading.Thread(target=serve, daemon=True).start()
    return listener.getsockname()[1], received


def test_bridge_sends_authenticated_request_and_matches_response_id():
    port, received = _start_server(
        lambda request: {
            "jsonrpc": "2.0",
            "id": request["id"],
            "result": {"ready": True},
        }
    )
    adapter = MariBridge(BridgeConfig("127.0.0.1", port, "secret", 2))

    assert adapter.call("diagnostics.ping") == {"ready": True}
    assert received["request"]["method"] == "diagnostics.ping"
    assert received["request"]["token"] == "secret"
    assert "_dcc_mcp_deadline_unix_ms" in received["request"]["params"]


def test_bridge_surfaces_structured_host_error():
    port, _ = _start_server(
        lambda request: {
            "jsonrpc": "2.0",
            "id": request["id"],
            "error": {"code": "host_error", "message": "project missing"},
        }
    )
    adapter = MariBridge(BridgeConfig("127.0.0.1", port, "secret", 2))

    with pytest.raises(BridgeError, match="host_error: project missing"):
        adapter.call("project.inspect")


@pytest.mark.parametrize(
    ("host", "port", "token"),
    [("0.0.0.0", 1, "x"), ("127.0.0.1", 0, "x"), ("127.0.0.1", 1, "")],
)
def test_bridge_config_rejects_non_loopback_or_incomplete_values(host, port, token):
    with pytest.raises(BridgeError):
        BridgeConfig(host, port, token)
