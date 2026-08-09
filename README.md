# dcc-mcp-mari

Production-oriented [DCC-MCP](https://github.com/dcc-mcp) adapter for Foundry
Mari. It exposes project, geometry, channel, node graph, layer, shader, image,
and texture-export workflows as typed tools without arbitrary Python execution.
The host plugin supports Mari 5.0 and newer while keeping the DCC-MCP runtime
in a separately installed Python 3.9+ sidecar.

## Architecture

Mari loads a small standard-library plugin on its GUI thread. The plugin owns an
authenticated loopback socket and starts the separately installed DCC-MCP
sidecar. A Qt timer executes bounded Mari API commands on the host thread, while
networking, discovery, jobs, and Gateway integration stay outside Mari's bundled
Python environment.

## Install

```powershell
python -m pip install dcc-mcp-mari
dcc-mcp-mari install
```

Restart Mari after installation. The default Windows target is
`Documents/Mari/Scripts`. Override it for a custom `MARI_SCRIPT_PATH`:

```powershell
dcc-mcp-mari install --script-dir "D:/Mari/Scripts" --overwrite
```

Uninstall only this adapter's startup files:

```powershell
dcc-mcp-mari uninstall
```

## Capability groups

- `mari-session`: connection and full project lifecycle, including archive,
  rename, duplicate, and removal.
- `mari-geometry`: geometry and channel lifecycle.
- `mari-nodegraph`: nodes, connections, and layer stacks.
- `mari-lookdev`: shaders, images, export items, and texture export.

All host mutations require a live Mari process. File inputs must be existing
absolute paths, output parents must already exist, and destructive operations
are explicitly annotated for DCC-MCP clients.

## Development

```powershell
python -m pip install -e ".[dev]"
python -m ruff check src tests
python -m ruff format --check src tests
python -m pytest
python -m build
python -m twine check dist/*
```

Mari Python API reference: [Using Python in Mari](https://learn.foundry.com/mari/content/software_api_overview/using_python/python_in_mari.html).
