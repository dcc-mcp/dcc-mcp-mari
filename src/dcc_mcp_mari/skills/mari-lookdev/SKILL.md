---
name: mari-lookdev
description: >-
  Manage Mari shaders, imported images, and export items through typed host
  operations. Use for look-development bindings and production texture export.
license: MIT
compatibility: "Mari 5.0+; external sidecar Python 3.9+; dcc-mcp-core 0.19.91+"
allowed-tools: Python
metadata:
  dcc-mcp:
    dcc: mari
    layer: domain
    version: "0.3.0"  # x-release-please-version
    stage: lookdev
    search-hint: "Mari shader image texture export item colorspace resolution depth UDIM"
    tags: "mari,shader,image,export,lookdev"
    tools: tools.yaml
---

# Mari Look Development and Export

Inspect shaders, images, and export items before mutation. Imported image paths
must exist. Export roots must already exist, and only Mari's bounded resolution,
colorspace, depth, and post-process overrides are accepted.
