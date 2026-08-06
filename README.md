# dcc-mcp-mari

Mari adapter foundation for the DCC-MCP organization.

This is an experimental, read-only first slice. It is **not** in the released
`dcc-mcp-cli dcc-types` catalog yet.

## Scope

- Discover the terminal/Python boundary.
- Expose one typed, read-only project inspection tool.
- Keep host API calls outside the MCP HTTP worker.
- Do not expose arbitrary source evaluation.

## Install

```bash
python -m pip install -e ".[test]"
dcc-mcp-mari
```

Configure the bridge environment variables in `src/dcc_mcp_mari/bridge.py`.
A real Mari live smoke is required before catalog onboarding.

Official API reference: https://learn.foundry.com/mari/content/software_api_overview/using_python/python_in_mari.html

