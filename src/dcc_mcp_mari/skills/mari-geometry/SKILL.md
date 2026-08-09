---
name: mari-geometry
description: >-
  Manage Mari geometry entities and paint channels through typed host operations.
  Use for geometry import/selection/removal and channel lifecycle work.
license: MIT
compatibility: "Mari 5.0+; external sidecar Python 3.9+; dcc-mcp-core 0.19.91+"
allowed-tools: Python
metadata:
  dcc-mcp:
    dcc: mari
    layer: domain
    version: "0.1.0"  # x-release-please-version
    stage: geometry
    search-hint: "Mari geometry mesh import channel resolution depth colorspace"
    tags: "mari,geometry,channel,texture"
    tools: tools.yaml
---

# Mari Geometry

Inspect geometry and channels before mutation. Import paths must be existing
absolute files. Channel removal requires an explicit channel and exposes Mari's
bounded node-destruction strategies.
