"""Out-of-process DCC-MCP server bound to one live Mari process."""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import threading
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from dcc_mcp_core import DccServerOptions, HostExecutionBridge
from dcc_mcp_core.host import QueueDispatcher, StandaloneHost
from dcc_mcp_core.readiness import AdapterReadinessBinder
from dcc_mcp_core.server_base import DccServerBase

from . import bridge
from .__version__ import __version__
from .dispatcher import MariBridgeDispatcher
from .install import LifecycleRequest, default_script_dir, run_lifecycle

_server: Optional["MariMcpServer"] = None


class MariMcpServer(DccServerBase):
    """DCC-MCP server backed by the authenticated Mari host plugin."""

    def __init__(self, port: Optional[int] = None, host_pid: Optional[int] = None) -> None:
        resolved_pid = host_pid or int(os.environ.get("DCC_MCP_MARI_HOST_PID", "0"))
        if resolved_pid <= 0:
            raise ValueError("A live Mari host PID is required")

        self._host_dispatcher = QueueDispatcher()
        self._host_driver = StandaloneHost(
            self._host_dispatcher,
            thread_name="dcc-mcp-mari-host",
        )
        execution_bridge = HostExecutionBridge(
            dispatcher=MariBridgeDispatcher(),
            host_dispatcher=self._host_dispatcher,
            default_thread_affinity="main",
            default_execution="sync",
            default_timeout_hint_secs=620,
        )
        options = DccServerOptions.from_env(
            "mari",
            Path(__file__).resolve().parent / "skills",
            port=port,
            server_name="dcc-mcp-mari",
            server_version=__version__,
            adapter_version=__version__,
            dcc_pid=resolved_pid,
            dcc_version=os.environ.get("DCC_MCP_MARI_VERSION"),
            instance_type="gui",
            execution_bridge=execution_bridge,
        )
        super().__init__(options=options)
        self._readiness = AdapterReadinessBinder(self)
        self._readiness_stop = threading.Event()
        self._readiness_thread: Optional[threading.Thread] = None
        self._set_bridge_readiness(False)

    def start(self, **kwargs: Any) -> Any:
        self._host_driver.start()
        try:
            handle = super().start(**kwargs)
            self._start_readiness_monitor()
            return handle
        except Exception:
            try:
                super().stop()
            finally:
                self._host_driver.stop()
            raise

    def stop(self) -> None:
        self._stop_readiness_monitor()
        try:
            super().stop()
        finally:
            self._host_driver.stop()

    def _set_bridge_readiness(self, ready: bool) -> None:
        self._readiness.mark_dispatcher_ready(
            ready,
            host_execution_bridge_ready=ready,
            main_thread_executor_ready=ready,
            dcc_ready=ready,
        )

    def _start_readiness_monitor(self) -> None:
        if self._readiness_thread is not None and self._readiness_thread.is_alive():
            return
        self._readiness_stop.clear()
        self._readiness_thread = threading.Thread(
            target=self._monitor_bridge_readiness,
            name="dcc-mcp-mari-readiness",
            daemon=True,
        )
        self._readiness_thread.start()

    def _monitor_bridge_readiness(self) -> None:
        while not self._readiness_stop.wait(2.0):
            if bridge.is_connected():
                self._set_bridge_readiness(True)
                return

    def _stop_readiness_monitor(self) -> None:
        self._readiness_stop.set()
        thread, self._readiness_thread = self._readiness_thread, None
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=1.0)
        self._set_bridge_readiness(False)

    def _version_string(self) -> str:
        return os.environ.get("DCC_MCP_MARI_VERSION", "unknown")


def start_server(
    port: Optional[int] = None,
    host_pid: Optional[int] = None,
) -> MariMcpServer:
    """Start the singleton sidecar for one live Mari process."""
    global _server
    if _server is None or not _server.is_running:
        _server = MariMcpServer(port=port, host_pid=host_pid)
        _server.register_builtin_actions()
        _server.start()
    return _server


def stop_server() -> None:
    """Stop the current singleton sidecar."""
    global _server
    if _server is not None:
        _server.stop()
        _server = None


def _process_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel32.WaitForSingleObject.restype = wintypes.DWORD
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        handle = kernel32.OpenProcess(0x00100000, False, pid)
        if not handle:
            error = ctypes.get_last_error()
            if error == 5:
                return True
            if error == 87:
                return False
            raise OSError(error, ctypes.FormatError(error))
        try:
            result = kernel32.WaitForSingleObject(handle, 0)
            if result == 258:
                return True
            if result == 0:
                return False
            raise OSError(ctypes.get_last_error(), "WaitForSingleObject failed")
        finally:
            kernel32.CloseHandle(handle)

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Install or run the DCC-MCP Mari adapter.")
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve = subparsers.add_parser("serve", help="Run the sidecar for a live Mari process.")
    serve.add_argument("--host-pid", type=int, required=True)
    serve.add_argument("--bridge-port", type=int, required=True)
    serve.add_argument("--mcp-port", type=int)

    lifecycle_help = {
        "install": "Install the Mari startup plugin.",
        "status": "Inspect the receipt-owned Mari installation.",
        "verify": "Verify installed files and live Mari readiness.",
        "uninstall": "Remove receipt-owned files and restore prior files.",
        "upgrade": "Replace the Mari startup plugin transactionally.",
    }
    for operation, help_text in lifecycle_help.items():
        command = subparsers.add_parser(operation, help=help_text)
        command.add_argument("--json", action="store_true", dest="json_output")
        command.add_argument("--yes", action="store_true")
        command.add_argument("--dry-run", action="store_true")
        command.add_argument("--repair", action="store_true")
        command.add_argument("--dcc-path", type=Path)
        command.add_argument(
            "--python", type=Path, default=Path(sys.executable), dest="python_path"
        )
        command.add_argument("--script-dir", type=Path, default=default_script_dir())
        if operation == "install":
            command.add_argument(
                "--overwrite",
                action="store_true",
                dest="repair",
                help="Compatibility alias for --repair.",
            )
    return parser


def _run_sidecar(args: argparse.Namespace) -> None:
    if not 1 <= args.bridge_port <= 65535:
        raise SystemExit("--bridge-port must be between 1 and 65535")
    if args.host_pid <= 0:
        raise SystemExit("--host-pid must be a positive process id")
    os.environ["DCC_MCP_MARI_BRIDGE_PORT"] = str(args.bridge_port)
    os.environ["DCC_MCP_MARI_HOST_PID"] = str(args.host_pid)

    stopped = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stopped.set())
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, lambda *_: stopped.set())

    start_server(port=args.mcp_port, host_pid=args.host_pid)
    try:
        while not stopped.wait(1.0):
            if not _process_is_alive(args.host_pid):
                break
    finally:
        stop_server()


def _print_lifecycle_result(result: Mapping[str, Any], *, json_output: bool) -> None:
    if json_output:
        print(json.dumps(result, sort_keys=True))
        return
    print("%s: %s" % (result.get("status", "unknown"), result.get("reason", "")))
    for step in result.get("next_steps", []):
        command = step.get("command") if isinstance(step, Mapping) else None
        if isinstance(command, list):
            print("next: %s" % " ".join(str(part) for part in command))


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Dispatch installation commands or run a host-bound sidecar."""
    args = _build_parser().parse_args(list(argv) if argv is not None else sys.argv[1:])
    if args.command != "serve":
        result = run_lifecycle(
            LifecycleRequest(
                operation=args.command,
                dcc_path=args.dcc_path,
                python_path=args.python_path,
                script_dir=args.script_dir,
                yes=args.yes,
                dry_run=args.dry_run,
                json_output=args.json_output,
                repair=args.repair,
            )
        )
        _print_lifecycle_result(result, json_output=args.json_output)
        return int(result["exit_code"])
    _run_sidecar(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
