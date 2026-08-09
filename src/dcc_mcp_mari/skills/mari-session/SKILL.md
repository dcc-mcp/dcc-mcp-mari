---
name: mari-session
description: >-
  Inspect Mari and manage its project lifecycle through typed host operations.
  Use for connection checks, project discovery, create/open/save/close, and
  archive, rename, duplicate, and remove workflows. Not for arbitrary Python execution.
license: MIT
compatibility: "Mari 5.0+; external sidecar Python 3.9+; dcc-mcp-core 0.19.91+"
allowed-tools: Python
metadata:
  dcc-mcp:
    dcc: mari
    layer: domain
    version: "0.1.0"  # x-release-please-version
    stage: session
    search-hint: "Mari project session create open save close archive rename duplicate remove"
    tags: "mari,project,session,archive"
    tools: tools.yaml
---

# Mari Session

Inspect the session before mutations. Creating or opening a project requires
the current project to be closed. `close_project` refuses unsaved changes unless
`discard_changes` is explicit. File paths must be absolute.
Rename, duplicate, and remove operations require the current project to be closed.
