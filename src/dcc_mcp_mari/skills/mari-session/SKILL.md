---
name: mari-session
description: >-
  Inspect a connected Mari session through the DCC-MCP terminal/Python boundary.
  This first slice is read-only and does not execute arbitrary source.
license: MIT
compatibility: "Mari; dcc-mcp-core 0.19+"
allowed-tools: "python"
metadata:
  dcc-mcp:
    dcc: mari
    layer: domain
    version: "0.1.0"
    tags: "mari,mcp,dcc,automation"
    tools: tools.yaml
    depends: "dcc-diagnostics"
---

# Mari

Experimental first slice. Live host validation, version matrices, catalog
onboarding, and mutation tools are separate follow-up gates.

