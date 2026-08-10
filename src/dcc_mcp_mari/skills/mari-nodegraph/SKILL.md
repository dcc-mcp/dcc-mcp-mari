---
name: mari-nodegraph
description: >-
  Inspect and edit Mari node graphs and channel layer stacks through typed host
  operations. Use for graph construction, connections, layers, and blend state.
license: MIT
compatibility: "Mari 5.0+; external sidecar Python 3.9+; dcc-mcp-core 0.19.91+"
allowed-tools: Python
metadata:
  dcc-mcp:
    dcc: mari
    layer: domain
    version: "0.2.1"  # x-release-please-version
    stage: nodegraph
    search-hint: "Mari node graph paint node connect layer stack blend adjustment procedural"
    tags: "mari,nodegraph,layer,paint"
    tools: tools.yaml
---

# Mari Node Graph

List nodes or layers before editing identifiers. Node creation accepts only a
Mari type ID or a bounded paint-node specification. Connections and metadata
are explicit; arbitrary source execution is unavailable.
