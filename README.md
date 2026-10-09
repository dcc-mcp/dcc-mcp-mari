# dcc-mcp-mari

Production-oriented [DCC-MCP](https://github.com/dcc-mcp) adapter for Foundry
Mari. It exposes project, geometry, channel, node graph, layer, shader, image,
and texture-export workflows as typed tools without arbitrary Python execution.
The host plugin supports Mari 5.0 and newer while keeping the DCC-MCP runtime
in a separately installed Python 3.9+ sidecar.

<!-- dcc-mcp-coverage-pointer:start -->
<!-- Generated from dcc-mcp-catalog.yml by scripts/generate_adapter_pointer.py in dcc-mcp/dcc-mcp-core. Do not edit by hand. -->
## Part of the DCC-MCP host matrix

**dcc-mcp-mari** — Mari adapter for typed project, geometry, channel, node-graph, layer,
shader, image, and export workflows.

It is one of **47 host adapters** in the DCC-MCP catalog. Every adapter speaks the same
MCP protocol and builds on the same core runtime contract; each one exposes the tools
its own host needs on top of that.

- [All host adapters and install metadata](https://dcc-mcp.github.io/ecosystem)
- [Host matrix on the core README](https://github.com/dcc-mcp/dcc-mcp-core#readme)
- [Showcase](https://dcc-mcp.github.io/showcase)

This block is generated from the catalog entry in
[`dcc-mcp-catalog.yml`](https://github.com/dcc-mcp/dcc-mcp-core/blob/main/dcc-mcp-catalog.yml).
Re-run the generator after changing the catalog.
<!-- dcc-mcp-coverage-pointer:end -->

## Architecture

Mari loads a small standard-library plugin on its GUI thread. The plugin owns an
authenticated loopback socket and starts the separately installed DCC-MCP
sidecar. A Qt timer executes bounded Mari API commands on the host thread, while
networking, discovery, jobs, and Gateway integration stay outside Mari's bundled
Python environment.

## Install

The authoritative agent-first lifecycle, platform paths, stable JSON schema,
exit codes, recovery behavior, and troubleshooting are in
[`install.md`](install.md).

```powershell
python -m pip install dcc-mcp-mari
dcc-mcp-mari install --dcc-path <mari-executable> --python <python> --dry-run --json
dcc-mcp-mari install --dcc-path <mari-executable> --python <python> --yes --json
```

Restart Mari after installation. The default Windows target is
`Documents/Mari/Scripts`. Override it for a custom `MARI_SCRIPT_PATH`:

```powershell
dcc-mcp-mari install --dcc-path <mari-executable> --python <python> --script-dir "D:/Mari/Scripts" --yes --json
```

Uninstall only this adapter's startup files:

```powershell
dcc-mcp-mari uninstall --dcc-path <mari-executable> --python <python> --yes --json
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
