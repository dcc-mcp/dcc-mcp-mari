from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

from dcc_mcp_mari.__version__ import __version__

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_install_guide_documents_agent_first_lifecycle_contract() -> None:
    guide = (REPOSITORY_ROOT / "install.md").read_text(encoding="utf-8")

    headings = [
        "## Requirements",
        "## Supported versions",
        "## Agent quick path",
        "## Manual path",
        "## Verify",
        "## Upgrade",
        "## Uninstall",
        "## Troubleshooting",
    ]
    assert all(heading in guide for heading in headings)
    assert all(platform in guide for platform in ("Windows", "macOS", "Linux"))
    assert all(
        "dcc-mcp-mari %s" % operation in guide
        for operation in ("install", "status", "verify", "upgrade", "uninstall")
    )
    assert all("`%s`" % code in guide for code in (0, 10, 20, 30, 40, 50))
    assert "--json" in guide
    assert "--dry-run" in guide
    assert "--yes" in guide
    assert "--dcc-path" in guide
    assert "--python" in guide
    assert "https://raw.githubusercontent.com/dcc-mcp/dcc-mcp-mari/main/install.md" in guide


def test_ci_runs_explicit_lifecycle_plan_and_receipt_round_trip() -> None:
    workflow = yaml.safe_load(
        (REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    )
    steps = workflow["jobs"]["test"]["steps"]
    names = {step.get("name") for step in steps}

    assert "Lifecycle plan and receipt round-trip" in names


def test_install_guide_wheel_pin_tracks_release_metadata() -> None:
    guide = (REPOSITORY_ROOT / "install.md").read_text(encoding="utf-8")
    project = (REPOSITORY_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    manifest = json.loads(
        (REPOSITORY_ROOT / ".release-please-manifest.json").read_text(encoding="utf-8")
    )
    release_config = json.loads(
        (REPOSITORY_ROOT / "release-please-config.json").read_text(encoding="utf-8")
    )

    guide_pin = re.search(
        r'^python -m pip install "dcc-mcp-mari==([^"]+)"\s+# x-release-please-version$',
        guide,
        re.MULTILINE,
    )
    project_version = re.search(r'^version="([^"]+)"$', project, re.MULTILINE)

    assert guide_pin is not None
    assert project_version is not None
    assert {
        guide_pin.group(1),
        project_version.group(1),
        manifest["."],
        __version__,
    } == {__version__}
    assert {"type": "generic", "path": "install.md"} in release_config["packages"]["."][
        "extra-files"
    ]
