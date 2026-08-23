import sys
import time
from types import SimpleNamespace

import pytest

from dcc_mcp_mari.mari_plugin.commands import MariCommands, _image_set_size, _shader_type


class _Project:
    def __init__(self, *, dirty=False):
        self._dirty = dirty
        self.saved = False

    def name(self):
        return "Demo"

    def uuid(self):
        return "project-uuid"

    def isDirty(self):
        return self._dirty

    def isModified(self):
        return self._dirty

    def info(self):
        return {"author": "test"}

    def save(self, force):
        self.saved = force


class _Projects:
    def __init__(self, project):
        self._project = project
        self._catalog = [project] if project else []
        self.closed = None

    def current(self):
        return self._project

    def list(self):
        return list(self._catalog)

    def close(self, value):
        self.closed = value
        self._project = None

    def rename(self, project, new_name):
        self.renamed = (project, new_name)

    def duplicate(self, project, new_name):
        self.duplicated = (project, new_name)
        duplicate = _Project()
        duplicate.name = lambda: new_name
        duplicate.uuid = lambda: "duplicate-uuid"
        self._catalog.append(duplicate)
        return duplicate

    def remove(self, project):
        self.removed = project


def _fake_mari(project=None, version="7.5v2"):
    projects = _Projects(project)
    return SimpleNamespace(
        app=SimpleNamespace(
            version=lambda: version,
            isRunning=lambda: True,
            logFileName=lambda: "mari.log",
        ),
        projects=projects,
        geo=SimpleNamespace(list=lambda: [], current=lambda: None),
        images=SimpleNamespace(list=lambda: []),
    )


def test_command_map_has_no_arbitrary_python_escape_hatch():
    commands = MariCommands(_fake_mari())

    assert len(commands.method_names) == 39
    assert all("python" not in name and "script" not in name for name in commands.method_names)
    with pytest.raises(ValueError, match="Unsupported Mari command"):
        commands.execute("python.eval", {"source": "open('secret')"})


def test_ping_and_project_inspection_return_bounded_json_values():
    project = _Project()
    commands = MariCommands(_fake_mari(project))

    ping = commands.execute("diagnostics.ping", {})
    inspected = commands.execute("project.inspect", {})

    assert ping["mari_version"] == "7.5v2"
    assert ping["python_version"] == sys.version.split()[0]
    assert ping["command_count"] == 39
    assert inspected["project"]["uuid"] == "project-uuid"
    assert inspected["geometry"] == []


def test_ping_serializes_mari_app_version_objects():
    version = SimpleNamespace(string=lambda: "5.0v1")

    ping = MariCommands(_fake_mari(version=version)).execute("diagnostics.ping", {})

    assert ping["mari_version"] == "5.0v1"


def test_closed_project_lifecycle_calls_are_typed_and_bounded():
    mari = _fake_mari()
    commands = MariCommands(mari)

    renamed = commands.execute("project.rename", {"project": "Old", "new_name": "Renamed"})
    duplicated = commands.execute("project.duplicate", {"project": "Renamed", "new_name": "Copy"})
    removed = commands.execute("project.remove", {"project": "Copy"})

    assert mari.projects.renamed == ("Old", "Renamed")
    assert mari.projects.duplicated == ("Renamed", "Copy")
    assert mari.projects.removed == "Copy"
    assert renamed["project"]["name"] == "Renamed"
    assert duplicated["project"]["name"] == "Copy"
    assert removed == {"removed_project": "Copy"}


def test_archive_project_requires_an_explicit_closed_project(tmp_path):
    mari = _fake_mari()
    calls = []
    mari.projects.archive = lambda project, path: calls.append((project, path))
    archive = tmp_path / "Demo.mra"

    result = MariCommands(mari).execute(
        "project.archive", {"project": "project-uuid", "path": str(archive)}
    )

    assert calls == [("project-uuid", str(archive))]
    assert result == {
        "project": "project-uuid",
        "path": str(archive),
        "exists": False,
    }

    with pytest.raises(RuntimeError, match="Close the current Mari project before archiving"):
        MariCommands(_fake_mari(_Project())).execute(
            "project.archive", {"project": "project-uuid", "path": str(archive)}
        )


def test_duplicate_project_supports_mari_5_single_argument_api():
    class Project:
        def __init__(self, name, uuid):
            self._name = name
            self._uuid = uuid

        def name(self):
            return self._name

        def uuid(self):
            return self._uuid

    source = Project("Source", "source-uuid")
    duplicate = Project("Source copy", "copy-uuid")

    class Projects:
        def __init__(self):
            self.items = [source]

        def current(self):
            return None

        def list(self):
            return list(self.items)

        def duplicate(self, project):
            assert project == "Source"
            self.items.append(duplicate)

        def rename(self, project, new_name):
            assert project == "Source copy"
            duplicate._name = new_name

    mari = _fake_mari()
    mari.projects = Projects()

    result = MariCommands(mari).execute(
        "project.duplicate", {"project": "Source", "new_name": "Requested Copy"}
    )

    assert result["project"]["name"] == "Requested Copy"
    assert result["project"]["uuid"] == "copy-uuid"


def test_image_import_uses_mari_5_safe_single_argument_overload(tmp_path):
    image_path = tmp_path / "image.png"
    image_path.write_bytes(b"image")
    image = SimpleNamespace(
        name=lambda: "image.png",
        mostRelevantPath=lambda: str(image_path),
        width=lambda: 64,
        height=lambda: 64,
        depth=lambda: "byte",
        isUniform=lambda: False,
    )
    mari = _fake_mari(_Project())
    calls = []
    mari.images = SimpleNamespace(
        open=lambda *args: calls.append(args) or [image],
        list=lambda: [image],
    )

    result = MariCommands(mari).execute("image.import", {"path": str(image_path)})

    assert calls == [(str(image_path),)]
    assert result["images"][0]["name"] == "image.png"


def test_channel_resize_converts_to_supported_mari_image_size():
    size_type = SimpleNamespace(Size=lambda value: ("size", value))

    assert _image_set_size(SimpleNamespace(ImageSet=size_type), 512) == ("size", 512)
    with pytest.raises(ValueError, match="power-of-two"):
        _image_set_size(SimpleNamespace(ImageSet=size_type), 300)


def test_shader_type_accepts_exact_paths_and_unique_short_names():
    available = ["Shaders/BRDF", "Lighting/Standalone/Standard Lighting"]

    assert _shader_type(available, "Shaders/BRDF", "standalone") == "Shaders/BRDF"
    assert _shader_type(available, "BRDF", "standalone") == "Shaders/BRDF"
    with pytest.raises(ValueError, match="Unknown Mari standalone shader type"):
        _shader_type(available, "Missing", "standalone")


def test_texture_export_is_forced_to_background_mode(tmp_path):
    output = tmp_path / "BaseColor.1001.png"
    item = SimpleNamespace(
        sourceNodeName=lambda: "BaseColor",
        exportEnabled=lambda: True,
        resolveExportFilePaths=lambda root: [str(output)],
    )
    geometry = SimpleNamespace(name=lambda: "cube")

    class Exports:
        def __init__(self):
            self.calls = []

        def exportItemList(self, value):
            assert value is geometry
            return [item]

        def exportTextures(self, items, root, overrides):
            self.calls.append((items, root, overrides))

    mari = _fake_mari(_Project())
    mari.geo = SimpleNamespace(current=lambda: geometry)
    mari.exports = Exports()

    result = MariCommands(mari).execute(
        "export.run",
        {
            "root_path": str(tmp_path),
            "source_nodes": ["BaseColor"],
            "overrides": {"RESOLUTION": "512 x 512"},
        },
    )

    assert mari.exports.calls == [
        ([item], str(tmp_path), {"RESOLUTION": "512 x 512", "BACKGROUND_EXPORT": True})
    ]
    assert result["background_export"] is True
    assert result["planned_files"] == {"BaseColor": [str(output)]}


def test_expired_command_is_rejected_before_host_mutation():
    project = _Project()
    commands = MariCommands(_fake_mari(project))

    with pytest.raises(RuntimeError, match="expired"):
        commands.execute(
            "project.save",
            {"_dcc_mcp_deadline_unix_ms": int((time.time() - 1) * 1000)},
        )
    assert project.saved is False


def test_close_project_requires_explicit_discard_for_unsaved_changes():
    project = _Project(dirty=True)
    mari = _fake_mari(project)
    commands = MariCommands(mari)

    with pytest.raises(RuntimeError, match="unsaved changes"):
        commands.execute("project.close", {})
    assert mari.projects.current() is project

    result = commands.execute("project.close", {"discard_changes": True})
    assert result["closed_project"] == "Demo"
    assert result["discarded_changes"] is True
    assert mari.projects.current() is None
