import re
from pathlib import Path

import yaml

from dcc_mcp_mari.mari_plugin.commands import MariCommands

ROOT = Path(__file__).parents[1] / "src" / "dcc_mcp_mari" / "skills"


def test_every_host_command_has_one_typed_tool_wrapper():
    tools = []
    methods = []
    for tools_file in ROOT.glob("*/tools.yaml"):
        document = yaml.safe_load(tools_file.read_text(encoding="utf-8"))
        for tool in document["tools"]:
            tools.append(tool["name"])
            source = tools_file.parent / tool["source_file"]
            assert source.is_file(), source
            match = re.search(r'bridge_main\(\s*"([^"]+)"', source.read_text(encoding="utf-8"))
            assert match, source
            methods.append(match.group(1))
            assert tool["input_schema"]["additionalProperties"] is False
            assert tool["affinity"] == "main"
            assert tool["enforce_thread_affinity"] is True
            assert "annotations" in tool

    expected = set(MariCommands(_minimal_mari()).method_names)
    assert len(tools) == len(set(tools)) == 39
    assert len(methods) == len(set(methods)) == 39
    assert set(methods) == expected


def _minimal_mari():
    class Minimal:
        pass

    return Minimal()
