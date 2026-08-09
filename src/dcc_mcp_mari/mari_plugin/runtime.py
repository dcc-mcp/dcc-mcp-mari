"""Pure-stdlib runtime loaded inside Mari's bundled Python interpreter."""

from __future__ import annotations

import hmac
import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from .commands import MariCommands

MAX_MESSAGE_BYTES = 1024 * 1024


class PluginRuntime:
    """Own one authenticated loopback bridge and its external MCP sidecar."""

    def __init__(self, mari_module: Any, plugin_dir: Path) -> None:
        self._mari = mari_module
        self._plugin_dir = plugin_dir
        self._commands = MariCommands(mari_module)
        self._listener: Optional[socket.socket] = None
        self._child: Optional[subprocess.Popen[Any]] = None
        self._log_handle: Optional[Any] = None
        self._timer: Optional[Any] = None
        self._token = secrets.token_urlsafe(32)
        self._stopped = False

    def start(self) -> None:
        """Bind the bridge, launch the sidecar, and attach the main-thread timer."""
        if self.running:
            return
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", 0))
        listener.listen(8)
        listener.setblocking(False)
        self._listener = listener
        try:
            self._start_child(int(listener.getsockname()[1]))
            self._start_timer()
        except Exception:
            self.stop()
            raise
        self._log("DCC-MCP Mari started; sidecar log: %s" % self.log_path)

    @property
    def running(self) -> bool:
        return (
            not self._stopped
            and self._listener is not None
            and self._child is not None
            and self._child.poll() is None
        )

    @property
    def log_path(self) -> Path:
        return Path(tempfile.gettempdir()) / ("dcc-mcp-mari-%s.log" % os.getpid())

    def poll(self) -> None:
        """Execute a bounded number of requests on Mari's GUI thread."""
        if self._stopped:
            return
        for _ in range(4):
            try:
                accepted = self._listener.accept() if self._listener else (None, None)
                connection, _address = accepted
            except (BlockingIOError, OSError):
                break
            if connection is not None:
                self._handle_connection(connection)
        if self._child is not None and self._child.poll() is not None:
            code = self._child.returncode
            self._child = None
            self._log("DCC-MCP Mari sidecar exited with code %s; see %s" % (code, self.log_path))

    def stop(self) -> None:
        """Release only resources owned by this plugin runtime."""
        if self._stopped:
            return
        self._stopped = True
        if self._timer is not None:
            self._timer.stop()
            self._timer = None
        if self._listener is not None:
            self._listener.close()
            self._listener = None
        if self._child is not None and self._child.poll() is None:
            self._child.terminate()
            try:
                self._child.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._child.kill()
        self._child = None
        if self._log_handle is not None:
            self._log_handle.close()
            self._log_handle = None

    def _start_timer(self) -> None:
        try:
            from PySide2 import QtCore, QtWidgets
        except ImportError as exc:
            raise RuntimeError("Mari PySide2 runtime is unavailable") from exc
        application = QtWidgets.QApplication.instance()
        if application is None:
            raise RuntimeError("Mari QApplication is unavailable")
        timer = QtCore.QTimer(application)
        timer.setInterval(15)
        timer.timeout.connect(self.poll)
        timer.start()
        application.aboutToQuit.connect(self.stop)
        self._timer = timer

    def _handle_connection(self, connection: socket.socket) -> None:
        request_id: Any = None
        with connection:
            connection.settimeout(0.1)
            try:
                request = json.loads(_read_line(connection).decode("utf-8"))
                if isinstance(request, dict):
                    request_id = request.get("id")
                response = self._execute_request(request)
            except Exception as exc:
                response = {
                    "error": {
                        "code": "invalid_request",
                        "message": str(exc) or type(exc).__name__,
                    }
                }
            envelope = {"jsonrpc": "2.0", "id": request_id, **response}
            encoded = json.dumps(envelope, separators=(",", ":")).encode("utf-8")
            if len(encoded) > MAX_MESSAGE_BYTES:
                encoded = json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "error": {
                            "code": "response_too_large",
                            "message": "Response exceeds 1 MiB",
                        },
                    },
                    separators=(",", ":"),
                ).encode("utf-8")
            try:
                connection.sendall(encoded + b"\n")
            except OSError:
                pass

    def _execute_request(self, request: Any) -> Dict[str, Any]:
        if not isinstance(request, dict):
            raise ValueError("request must be an object")
        if request.get("jsonrpc") != "2.0":
            raise ValueError("jsonrpc must be '2.0'")
        supplied = str(request.get("token") or "")
        if not hmac.compare_digest(supplied, self._token):
            raise PermissionError("invalid bridge token")
        method = request.get("method")
        params = request.get("params", {})
        if not isinstance(method, str) or not method:
            raise ValueError("method must be a non-empty string")
        if not isinstance(params, dict):
            raise ValueError("params must be an object")
        if method == "bridge.health":
            if params:
                raise ValueError("bridge.health accepts no parameters")
            return {"result": self._commands.execute("diagnostics.ping", {})}
        try:
            return {"result": self._commands.execute(method, dict(params))}
        except Exception as exc:
            return {
                "error": {
                    "code": "host_error",
                    "message": str(exc) or type(exc).__name__,
                }
            }

    def _start_child(self, port: int) -> None:
        configured = os.environ.get("DCC_MCP_MARI_SERVER", "").strip()
        if configured:
            server = Path(configured).expanduser().resolve()
        else:
            path_file = self._plugin_dir / "server_path.txt"
            if not path_file.is_file():
                raise RuntimeError("server_path.txt is missing; reinstall the Mari plugin")
            server = Path(path_file.read_text(encoding="utf-8").strip()).expanduser().resolve()
        if not server.is_file():
            raise RuntimeError("DCC-MCP Mari server not found: %s" % server)

        env = dict(os.environ)
        env["DCC_MCP_MARI_BRIDGE_HOST"] = "127.0.0.1"
        env["DCC_MCP_MARI_BRIDGE_PORT"] = str(port)
        env["DCC_MCP_MARI_BRIDGE_TOKEN"] = self._token
        env["DCC_MCP_MARI_VERSION"] = _app_version(self._mari.app)
        env["DCC_MCP_MARI_HOST_PID"] = str(os.getpid())
        if sys.platform == "win32":
            env.setdefault("DCC_MCP_UI_CONTROL_BACKEND", "windows-uia")
            env["DCC_MCP_UI_CONTROL_UIA_PROCESS_ID"] = str(os.getpid())

        self._log_handle = self.log_path.open("a", encoding="utf-8")
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
        self._child = subprocess.Popen(
            [str(server), "serve", "--host-pid", str(os.getpid()), "--bridge-port", str(port)],
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=self._log_handle,
            stderr=subprocess.STDOUT,
            creationflags=creationflags,
        )

    def _log(self, message: str) -> None:
        logger = getattr(self._mari, "utils", None)
        logger = getattr(logger, "log", None)
        if callable(logger):
            logger(message)
            return
        print(message)


def _read_line(connection: socket.socket) -> bytes:
    chunks = bytearray()
    while len(chunks) <= MAX_MESSAGE_BYTES:
        chunk = connection.recv(min(65536, MAX_MESSAGE_BYTES + 1 - len(chunks)))
        if not chunk:
            break
        newline = chunk.find(b"\n")
        chunks.extend(chunk if newline < 0 else chunk[:newline])
        if newline >= 0:
            break
    if len(chunks) > MAX_MESSAGE_BYTES:
        raise ValueError("request exceeds 1 MiB")
    if not chunks:
        raise ValueError("empty request")
    return bytes(chunks)


def _optional_call(target: Any, name: str, fallback: Any = None) -> Any:
    method = getattr(target, name, None)
    return method() if callable(method) else fallback


def _app_version(app: Any) -> str:
    version = _optional_call(app, "version", "unknown")
    string_method = getattr(version, "string", None)
    if callable(string_method):
        try:
            return str(string_method())
        except Exception:
            pass
    return str(version)
