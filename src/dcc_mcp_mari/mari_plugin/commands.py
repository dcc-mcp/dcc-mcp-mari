"""Typed Mari Python API boundary used by the loopback host plugin.

This module intentionally has no dependency on dcc-mcp-core.  The installer
copies it into Mari's script directory, where only Mari's bundled Python and
PySide2 are guaranteed to exist.
"""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional


class MariCommands:
    """Bounded command map for production texture-authoring workflows."""

    def __init__(self, mari_module: Any) -> None:
        self._mari = mari_module
        self._commands: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {
            "diagnostics.ping": self._ping,
            "project.inspect": self._inspect_project,
            "project.list": self._list_projects,
            "project.create": self._create_project,
            "project.open": self._open_project,
            "project.save": self._save_project,
            "project.close": self._close_project,
            "project.archive": self._archive_project,
            "project.rename": self._rename_project,
            "project.duplicate": self._duplicate_project,
            "project.remove": self._remove_project,
            "geometry.list": self._list_geometry,
            "geometry.import": self._import_geometry,
            "geometry.set_current": self._set_current_geometry,
            "geometry.remove": self._remove_geometry,
            "channel.list": self._list_channels,
            "channel.create": self._create_channel,
            "channel.update": self._update_channel,
            "channel.remove": self._remove_channel,
            "node.list": self._list_nodes,
            "node.create": self._create_node,
            "node.connect": self._connect_nodes,
            "node.update": self._update_node,
            "node.remove": self._remove_node,
            "layer.list": self._list_layers,
            "layer.create": self._create_layer,
            "layer.update": self._update_layer,
            "layer.remove": self._remove_layers,
            "shader.list": self._list_shaders,
            "shader.create": self._create_shader,
            "shader.update": self._update_shader,
            "shader.remove": self._remove_shader,
            "image.list": self._list_images,
            "image.import": self._import_image,
            "image.remove": self._remove_image,
            "export.list": self._list_export_items,
            "export.configure": self._configure_export_item,
            "export.remove": self._remove_export_item,
            "export.run": self._export_textures,
        }

    @property
    def method_names(self) -> List[str]:
        return sorted(self._commands)

    def execute(self, method: str, params: Mapping[str, Any]) -> Dict[str, Any]:
        command = self._commands.get(method)
        if command is None:
            raise ValueError("Unsupported Mari command: %s" % method)
        values = dict(params)
        deadline = values.pop("_dcc_mcp_deadline_unix_ms", None)
        if deadline is not None and int(deadline) < int(time.time() * 1000):
            raise RuntimeError("Mari request expired before main-thread execution")
        return command(values)

    # Diagnostics and project lifecycle -------------------------------------------------

    def _ping(self, params: Dict[str, Any]) -> Dict[str, Any]:
        _require_keys(params, set())
        app = self._mari.app
        return {
            "status": "ok",
            "mari_version": _app_version(app),
            "app_running": bool(_optional_call(app, "isRunning", True)),
            "log_file": str(_optional_call(app, "logFileName", "") or ""),
            "host_pid": os.getpid(),
            "host_thread_id": threading.get_ident(),
            "command_count": len(self._commands),
        }

    def _inspect_project(self, params: Dict[str, Any]) -> Dict[str, Any]:
        _require_keys(params, set())
        project = self._current_project(required=False)
        if project is None:
            return {"project_open": False, "project": None, "geometry": [], "images": []}
        geometry = list(self._mari.geo.list())
        images = list(self._mari.images.list())
        return {
            "project_open": True,
            "project": _project_summary(project),
            "geometry": [_geometry_summary(item, self._mari) for item in geometry],
            "images": [_image_summary(item) for item in images],
            "current_geometry": _entity_name(self._mari.geo.current()),
        }

    def _list_projects(self, params: Dict[str, Any]) -> Dict[str, Any]:
        _require_keys(params, set())
        current = self._current_project(required=False)
        projects = list(self._mari.projects.list())
        return {
            "projects": [_project_summary(item) for item in projects],
            "current_project": _entity_name(current),
        }

    def _create_project(self, params: Dict[str, Any]) -> Dict[str, Any]:
        _require_keys(
            params,
            {"name", "geometry_paths", "channels", "project_options"},
            {"name", "geometry_paths"},
        )
        if self._current_project(required=False) is not None:
            raise RuntimeError("Close the current Mari project before creating another")
        name = _non_empty_string(params["name"], "name")
        raw_paths = params["geometry_paths"]
        if not isinstance(raw_paths, list) or not raw_paths:
            raise ValueError("geometry_paths must be a non-empty array")
        geometry_paths = [
            str(_existing_absolute_file(value, "geometry_paths")) for value in raw_paths
        ]
        raw_channels = params.get("channels", [])
        if not isinstance(raw_channels, list):
            raise ValueError("channels must be an array")
        channels = [self._channel_info(value) for value in raw_channels]
        project_options = params.get("project_options", {})
        if not isinstance(project_options, dict):
            raise ValueError("project_options must be an object")
        mesh_arg: Any = geometry_paths[0] if len(geometry_paths) == 1 else geometry_paths
        self._mari.projects.create(name, mesh_arg, channels, [], dict(project_options))
        return {"project": _project_summary(self._current_project())}

    def _open_project(self, params: Dict[str, Any]) -> Dict[str, Any]:
        _require_keys(params, {"project"}, {"project"})
        if self._current_project(required=False) is not None:
            raise RuntimeError("Close the current Mari project before opening another")
        identifier = _non_empty_string(params["project"], "project")
        self._mari.projects.open(identifier)
        return {"project": _project_summary(self._current_project())}

    def _save_project(self, params: Dict[str, Any]) -> Dict[str, Any]:
        _require_keys(params, {"force"})
        project = self._current_project()
        project.save(bool(params.get("force", False)))
        return {"project": _project_summary(project)}

    def _close_project(self, params: Dict[str, Any]) -> Dict[str, Any]:
        _require_keys(params, {"discard_changes"})
        project = self._current_project()
        dirty = bool(
            _optional_call(project, "isModified", _optional_call(project, "isDirty", False))
        )
        discard = bool(params.get("discard_changes", False))
        if dirty and not discard:
            raise RuntimeError(
                "The current project has unsaved changes; save it or allow discard_changes"
            )
        name = _entity_name(project)
        self._mari.projects.close(False)
        return {"closed_project": name, "discarded_changes": dirty and discard}

    def _archive_project(self, params: Dict[str, Any]) -> Dict[str, Any]:
        _require_keys(params, {"path", "project"}, {"path", "project"})
        self._require_closed_project("archiving")
        path = _absolute_output_file(params["path"], "path", {".mra"})
        identifier = _non_empty_string(params["project"], "project")
        self._mari.projects.archive(str(identifier), str(path))
        return {"project": str(identifier), "path": str(path), "exists": path.is_file()}

    def _rename_project(self, params: Dict[str, Any]) -> Dict[str, Any]:
        _require_keys(params, {"project", "new_name"}, {"project", "new_name"})
        self._require_closed_project("renaming")
        identifier = _non_empty_string(params["project"], "project")
        new_name = _non_empty_string(params["new_name"], "new_name")
        self._mari.projects.rename(identifier, new_name)
        renamed = self._find_project(new_name)
        return {
            "previous_project": identifier,
            "project": _project_summary(renamed) if renamed is not None else {"name": new_name},
        }

    def _duplicate_project(self, params: Dict[str, Any]) -> Dict[str, Any]:
        _require_keys(params, {"project", "new_name"}, {"project", "new_name"})
        self._require_closed_project("duplicating")
        identifier = _non_empty_string(params["project"], "project")
        new_name = _non_empty_string(params["new_name"], "new_name")
        known_projects = {
            str(_optional_call(project, "uuid", "") or _entity_name(project))
            for project in self._mari.projects.list()
        }
        try:
            result = self._mari.projects.duplicate(identifier, new_name)
        except TypeError:
            # Mari 5 accepts only the source identifier and chooses a temporary copy name.
            result = self._mari.projects.duplicate(identifier)
        duplicated = self._new_project_since(known_projects)
        if duplicated is None and result is not None and not isinstance(result, (bool, str)):
            duplicated = result
        if duplicated is None:
            duplicated = self._find_project(new_name)
        if duplicated is None:
            raise RuntimeError("Mari did not report the duplicated project")
        if _entity_name(duplicated) != new_name:
            self._mari.projects.rename(_entity_name(duplicated), new_name)
            duplicated = self._find_project(new_name) or duplicated
        return {
            "source_project": identifier,
            "project": _project_summary(duplicated),
        }

    def _remove_project(self, params: Dict[str, Any]) -> Dict[str, Any]:
        _require_keys(params, {"project"}, {"project"})
        self._require_closed_project("removing")
        identifier = _non_empty_string(params["project"], "project")
        self._mari.projects.remove(identifier)
        return {"removed_project": identifier}

    # Geometry -------------------------------------------------------------------------

    def _list_geometry(self, params: Dict[str, Any]) -> Dict[str, Any]:
        _require_keys(params, set())
        self._current_project()
        current = self._mari.geo.current()
        return {
            "geometry": [_geometry_summary(item, self._mari) for item in self._mari.geo.list()],
            "current_geometry": _entity_name(current),
        }

    def _import_geometry(self, params: Dict[str, Any]) -> Dict[str, Any]:
        _require_keys(params, {"path", "load_as_child"}, {"path"})
        self._current_project()
        path = _existing_absolute_file(params["path"], "path")
        loaded = self._mari.geo.load(
            str(path), None, None, bool(params.get("load_as_child", False))
        )
        items = list(loaded) if isinstance(loaded, (list, tuple)) else [loaded] if loaded else []
        return {
            "path": str(path),
            "geometry": [_geometry_summary(item, self._mari) for item in items],
        }

    def _set_current_geometry(self, params: Dict[str, Any]) -> Dict[str, Any]:
        _require_keys(params, {"geometry"}, {"geometry"})
        geometry = self._geometry(params["geometry"])
        self._mari.geo.setCurrent(geometry)
        return {"geometry": _geometry_summary(geometry, self._mari)}

    def _remove_geometry(self, params: Dict[str, Any]) -> Dict[str, Any]:
        _require_keys(params, {"geometry"}, {"geometry"})
        geometry = self._geometry(params["geometry"])
        name = _entity_name(geometry)
        self._mari.geo.remove(name)
        return {"removed_geometry": name}

    # Channels -------------------------------------------------------------------------

    def _list_channels(self, params: Dict[str, Any]) -> Dict[str, Any]:
        _require_keys(params, {"geometry"})
        geometry = self._geometry(params.get("geometry"))
        return {
            "geometry": _entity_name(geometry),
            "channels": [_channel_summary(item, geometry) for item in geometry.channelList()],
        }

    def _create_channel(self, params: Dict[str, Any]) -> Dict[str, Any]:
        _require_keys(
            params,
            {"geometry", "name", "width", "height", "depth", "shader_stack"},
            {"name", "width", "height", "depth"},
        )
        geometry = self._geometry(params.get("geometry"))
        name = _non_empty_string(params["name"], "name")
        width = _bounded_int(params["width"], "width", 1, 32768)
        height = _bounded_int(params["height"], "height", 1, 32768)
        depth = self._depth(params["depth"])
        channel = geometry.createChannel(
            name, width, height, depth, bool(params.get("shader_stack", False))
        )
        return {"geometry": _entity_name(geometry), "channel": _channel_summary(channel, geometry)}

    def _update_channel(self, params: Dict[str, Any]) -> Dict[str, Any]:
        _require_keys(
            params,
            {
                "geometry",
                "channel",
                "new_name",
                "size",
                "depth",
                "colorspace",
                "locked",
                "make_current",
            },
            {"channel"},
        )
        geometry = self._geometry(params.get("geometry"))
        channel = self._channel(geometry, params["channel"])
        if "new_name" in params:
            channel.setName(_non_empty_string(params["new_name"], "new_name"))
        if "size" in params:
            size = _image_set_size(self._mari, params["size"])
            channel.resize(size)
        if "depth" in params:
            convert_all = getattr(channel, "CONVERT_ALL", 0)
            channel.setDepth(self._depth(params["depth"]), convert_all)
        if "colorspace" in params:
            channel.setColorSpace(_non_empty_string(params["colorspace"], "colorspace"))
        if "locked" in params:
            channel.setLocked(bool(params["locked"]))
        if params.get("make_current"):
            geometry.setCurrentChannel(channel)
        return {"geometry": _entity_name(geometry), "channel": _channel_summary(channel, geometry)}

    def _remove_channel(self, params: Dict[str, Any]) -> Dict[str, Any]:
        _require_keys(params, {"geometry", "channel", "strategy"}, {"channel"})
        geometry = self._geometry(params.get("geometry"))
        channel = self._channel(geometry, params["channel"])
        name = _entity_name(channel)
        strategy_name = str(params.get("strategy", "unshared")).casefold()
        strategy_attrs = {
            "none": "DESTROY_NONE",
            "unshared": "DESTROY_UNSHARED",
            "all": "DESTROY_ALL",
        }
        if strategy_name not in strategy_attrs:
            raise ValueError("strategy must be one of: none, unshared, all")
        strategy = getattr(geometry, strategy_attrs[strategy_name], 0)
        geometry.removeChannel(channel, strategy)
        return {
            "geometry": _entity_name(geometry),
            "removed_channel": name,
            "strategy": strategy_name,
        }

    # Node graph -----------------------------------------------------------------------

    def _list_nodes(self, params: Dict[str, Any]) -> Dict[str, Any]:
        _require_keys(params, {"geometry", "selected_only"})
        geometry = self._geometry(params.get("geometry"))
        graph = geometry.nodeGraph()
        nodes = graph.selectedNodeList() if params.get("selected_only") else graph.nodeList()
        return {
            "geometry": _entity_name(geometry),
            "nodes": [_node_summary(node) for node in nodes],
            "available_types": [str(value) for value in graph.typeList()],
        }

    def _create_node(self, params: Dict[str, Any]) -> Dict[str, Any]:
        _require_keys(
            params,
            {
                "geometry",
                "type_id",
                "name",
                "paint",
                "width",
                "height",
                "depth",
                "fill_color",
                "select",
            },
            set(),
        )
        geometry = self._geometry(params.get("geometry"))
        graph = geometry.nodeGraph()
        if params.get("paint"):
            width = _bounded_int(params.get("width", 2048), "width", 1, 32768)
            height = _bounded_int(params.get("height", 2048), "height", 1, 32768)
            depth = self._depth(params.get("depth", "half"))
            color = self._color(params.get("fill_color", [0.0, 0.0, 0.0, 0.0]))
            node = graph.createPaintNode(width, height, depth, color)
        else:
            type_id = _non_empty_string(params.get("type_id"), "type_id")
            node = graph.createNode(type_id)
        if params.get("name"):
            node.setName(_non_empty_string(params["name"], "name"))
        if params.get("select"):
            node.setSelected(True)
        return {"geometry": _entity_name(geometry), "node": _node_summary(node)}

    def _connect_nodes(self, params: Dict[str, Any]) -> Dict[str, Any]:
        _require_keys(
            params,
            {"geometry", "destination_node", "input_port", "source_node"},
            {"destination_node", "input_port"},
        )
        geometry = self._geometry(params.get("geometry"))
        graph = geometry.nodeGraph()
        destination = self._node(graph, params["destination_node"])
        source_name = params.get("source_node")
        source = self._node(graph, source_name) if source_name else None
        port = _non_empty_string(params["input_port"], "input_port")
        destination.setInputNode(port, source)
        return {
            "geometry": _entity_name(geometry),
            "destination": _node_summary(destination),
            "source_node": _entity_name(source),
            "input_port": port,
        }

    def _update_node(self, params: Dict[str, Any]) -> Dict[str, Any]:
        _require_keys(
            params,
            {"geometry", "node", "name", "node_name", "selected", "metadata"},
            {"node"},
        )
        geometry = self._geometry(params.get("geometry"))
        node = self._node(geometry.nodeGraph(), params["node"])
        if "name" in params:
            node.setName(_non_empty_string(params["name"], "name"))
        if "node_name" in params:
            node.setNodeName(_non_empty_string(params["node_name"], "node_name"))
        if "selected" in params:
            node.setSelected(bool(params["selected"]))
        metadata = params.get("metadata", {})
        if not isinstance(metadata, dict):
            raise ValueError("metadata must be an object")
        for key, value in metadata.items():
            node.setMetadata(_non_empty_string(key, "metadata key"), value)
        return {"geometry": _entity_name(geometry), "node": _node_summary(node)}

    def _remove_node(self, params: Dict[str, Any]) -> Dict[str, Any]:
        _require_keys(params, {"geometry", "node"}, {"node"})
        geometry = self._geometry(params.get("geometry"))
        graph = geometry.nodeGraph()
        node = self._node(graph, params["node"])
        name = _node_identifier(node)
        graph.deleteNode(node)
        return {"geometry": _entity_name(geometry), "removed_node": name}

    # Layers ---------------------------------------------------------------------------

    def _list_layers(self, params: Dict[str, Any]) -> Dict[str, Any]:
        _require_keys(params, {"geometry", "channel"})
        geometry = self._geometry(params.get("geometry"))
        channel = self._channel(geometry, params.get("channel"))
        return {
            "geometry": _entity_name(geometry),
            "channel": _entity_name(channel),
            "layers": [_layer_summary(item) for item in channel.layerList()],
        }

    def _create_layer(self, params: Dict[str, Any]) -> Dict[str, Any]:
        _require_keys(
            params,
            {"geometry", "channel", "name", "layer_type", "type_key"},
            {"name", "layer_type"},
        )
        geometry = self._geometry(params.get("geometry"))
        channel = self._channel(geometry, params.get("channel"))
        name = _non_empty_string(params["name"], "name")
        layer_type = str(params["layer_type"]).casefold()
        if layer_type == "paint":
            layer = channel.createPaintableLayer(name)
        elif layer_type == "group":
            layer = channel.createGroupLayer(name)
        elif layer_type == "graph":
            layer = channel.createGraphLayer(name)
        elif layer_type == "adjustment":
            layer = channel.createAdjustmentLayer(
                name, _non_empty_string(params.get("type_key"), "type_key")
            )
        elif layer_type == "procedural":
            layer = channel.createProceduralLayer(
                name, _non_empty_string(params.get("type_key"), "type_key")
            )
        else:
            raise ValueError(
                "layer_type must be one of: paint, group, graph, adjustment, procedural"
            )
        return {
            "geometry": _entity_name(geometry),
            "channel": _entity_name(channel),
            "layer": _layer_summary(layer),
        }

    def _update_layer(self, params: Dict[str, Any]) -> Dict[str, Any]:
        _require_keys(
            params,
            {
                "geometry",
                "channel",
                "layer",
                "name",
                "visible",
                "locked",
                "selected",
                "blend_mode",
                "blend_amount",
            },
            {"layer"},
        )
        geometry = self._geometry(params.get("geometry"))
        channel = self._channel(geometry, params.get("channel"))
        layer = self._layer(channel, params["layer"])
        if "name" in params:
            layer.setName(_non_empty_string(params["name"], "name"))
        if "visible" in params:
            layer.setVisibility(bool(params["visible"]))
        if "locked" in params:
            layer.setLocked(bool(params["locked"]))
        if "selected" in params:
            layer.setSelected(bool(params["selected"]))
        if "blend_amount" in params:
            amount = _bounded_number(params["blend_amount"], "blend_amount", 0.0, 1.0)
            layer.setBlendAmount(amount)
        if "blend_mode" in params:
            mode_name = _non_empty_string(params["blend_mode"], "blend_mode").upper()
            mode = getattr(self._mari.Layer, mode_name, None)
            if mode is None:
                raise ValueError("Unknown Mari layer blend mode: %s" % params["blend_mode"])
            layer.setBlendMode(mode)
        return {
            "geometry": _entity_name(geometry),
            "channel": _entity_name(channel),
            "layer": _layer_summary(layer),
        }

    def _remove_layers(self, params: Dict[str, Any]) -> Dict[str, Any]:
        _require_keys(params, {"geometry", "channel", "layers"}, {"layers"})
        geometry = self._geometry(params.get("geometry"))
        channel = self._channel(geometry, params.get("channel"))
        names = params["layers"]
        if not isinstance(names, list) or not names:
            raise ValueError("layers must be a non-empty array")
        layers = [self._layer(channel, value) for value in names]
        removed = [_entity_name(item) for item in layers]
        channel.removeLayers(layers)
        return {
            "geometry": _entity_name(geometry),
            "channel": _entity_name(channel),
            "removed_layers": removed,
        }

    # Shaders --------------------------------------------------------------------------

    def _list_shaders(self, params: Dict[str, Any]) -> Dict[str, Any]:
        _require_keys(params, {"geometry"})
        geometry = self._geometry(params.get("geometry"))
        current = _optional_call(geometry, "currentShader")
        return {
            "geometry": _entity_name(geometry),
            "shaders": [_shader_summary(item, current) for item in geometry.shaderList()],
            "available_standalone_types": sorted(
                str(value) for value in geometry.shaderStandaloneTypeList()
            ),
            "available_layered_types": sorted(
                str(value) for value in geometry.shaderLayeredTypeList()
            ),
        }

    def _create_shader(self, params: Dict[str, Any]) -> Dict[str, Any]:
        _require_keys(
            params,
            {"geometry", "name", "shader_type", "shader_kind", "make_current"},
            {"name", "shader_type"},
        )
        geometry = self._geometry(params.get("geometry"))
        name = _non_empty_string(params["name"], "name")
        shader_kind = str(params.get("shader_kind", "standalone")).casefold()
        if shader_kind == "standalone":
            shader_type = _shader_type(
                geometry.shaderStandaloneTypeList(), params["shader_type"], "standalone"
            )
            shader = geometry.createStandaloneShader(name, shader_type)
        elif shader_kind == "layered":
            shader_type = _shader_type(
                geometry.shaderLayeredTypeList(), params["shader_type"], "layered"
            )
            shader = geometry.createLayeredShader(name, shader_type)
        else:
            raise ValueError("shader_kind must be one of: standalone, layered")
        if params.get("make_current"):
            geometry.setCurrentShader(shader)
        return {
            "geometry": _entity_name(geometry),
            "shader_kind": shader_kind,
            "shader": _shader_summary(shader, shader),
        }

    def _update_shader(self, params: Dict[str, Any]) -> Dict[str, Any]:
        _require_keys(
            params,
            {"geometry", "shader", "name", "parameters", "channel_inputs", "make_current"},
            {"shader"},
        )
        geometry = self._geometry(params.get("geometry"))
        shader = self._shader(geometry, params["shader"])
        if "name" in params:
            shader.setName(_non_empty_string(params["name"], "name"))
        parameters = params.get("parameters", {})
        if not isinstance(parameters, dict):
            raise ValueError("parameters must be an object")
        for key, value in parameters.items():
            shader.setParameter(str(key), self._host_value(value, geometry))
        inputs = params.get("channel_inputs", {})
        if not isinstance(inputs, dict):
            raise ValueError("channel_inputs must be an object")
        for input_name, channel_name in inputs.items():
            shader.setInput(str(input_name), self._channel(geometry, channel_name))
        if params.get("make_current"):
            geometry.setCurrentShader(shader)
        return {
            "geometry": _entity_name(geometry),
            "shader": _shader_summary(shader, _optional_call(geometry, "currentShader")),
        }

    def _remove_shader(self, params: Dict[str, Any]) -> Dict[str, Any]:
        _require_keys(params, {"geometry", "shader"}, {"shader"})
        geometry = self._geometry(params.get("geometry"))
        shader = self._shader(geometry, params["shader"])
        name = _entity_name(shader)
        geometry.removeShader(shader)
        return {"geometry": _entity_name(geometry), "removed_shader": name}

    # Images and export ----------------------------------------------------------------

    def _list_images(self, params: Dict[str, Any]) -> Dict[str, Any]:
        _require_keys(params, set())
        self._current_project()
        return {"images": [_image_summary(item) for item in self._mari.images.list()]}

    def _import_image(self, params: Dict[str, Any]) -> Dict[str, Any]:
        _require_keys(params, {"path"}, {"path"})
        self._current_project()
        path = _existing_absolute_file(params["path"], "path")
        # Mari 5's generated binding can abort the interpreter while resolving the
        # optional-argument overload, so use the documented single-argument form.
        opened = self._mari.images.open(str(path))
        images = list(opened) if isinstance(opened, (list, tuple)) else [opened]
        return {"images": [_image_summary(image) for image in images], "path": str(path)}

    def _remove_image(self, params: Dict[str, Any]) -> Dict[str, Any]:
        _require_keys(params, {"image"}, {"image"})
        self._current_project()
        image = self._image(params["image"])
        label = _image_identifier(image)
        self._mari.images.remove(image)
        return {"removed_image": label}

    def _list_export_items(self, params: Dict[str, Any]) -> Dict[str, Any]:
        _require_keys(params, {"geometry", "root_path"})
        geometry = self._geometry(params.get("geometry"))
        root = params.get("root_path")
        if root is not None:
            root = str(_existing_absolute_directory(root, "root_path"))
        items = list(self._mari.exports.exportItemList(geometry))
        return {
            "geometry": _entity_name(geometry),
            "export_items": [_export_item_summary(item, root) for item in items],
        }

    def _configure_export_item(self, params: Dict[str, Any]) -> Dict[str, Any]:
        _require_keys(
            params,
            {
                "geometry",
                "source_node",
                "file_template",
                "enabled",
                "resolution",
                "colorspace",
                "depth",
                "uv_indices",
                "post_process",
            },
            {"source_node", "file_template"},
        )
        geometry = self._geometry(params.get("geometry"))
        node = self._node(geometry.nodeGraph(), params["source_node"])
        item = self._export_item(geometry, _node_identifier(node), required=False)
        if item is None:
            item = self._mari.ExportItem()
            item.setSourceNode(node)
            self._mari.exports.addExportItem(item, geometry)
        item.setFileTemplate(_non_empty_string(params["file_template"], "file_template"))
        if "enabled" in params:
            item.setExportEnabled(bool(params["enabled"]))
        if "resolution" in params:
            item.setResolution(_non_empty_string(params["resolution"], "resolution"))
        if "colorspace" in params:
            item.setColorspace(_non_empty_string(params["colorspace"], "colorspace"))
        if "depth" in params:
            item.setDepth(_non_empty_string(params["depth"], "depth"))
        if "uv_indices" in params:
            values = params["uv_indices"]
            if not isinstance(values, list) or any(
                isinstance(value, bool) or not isinstance(value, int) for value in values
            ):
                raise ValueError("uv_indices must be an array of integers")
            item.setUvIndexList(values)
        if "post_process" in params:
            item.setPostProcessCommand(str(params["post_process"] or ""))
        return {"geometry": _entity_name(geometry), "export_item": _export_item_summary(item)}

    def _remove_export_item(self, params: Dict[str, Any]) -> Dict[str, Any]:
        _require_keys(params, {"geometry", "source_node"}, {"source_node"})
        geometry = self._geometry(params.get("geometry"))
        item = self._export_item(geometry, params["source_node"])
        source = str(_optional_call(item, "sourceNodeName", ""))
        self._mari.exports.removeExportItem(item)
        return {"geometry": _entity_name(geometry), "removed_source_node": source}

    def _export_textures(self, params: Dict[str, Any]) -> Dict[str, Any]:
        _require_keys(params, {"geometry", "root_path", "source_nodes", "overrides"}, {"root_path"})
        geometry = self._geometry(params.get("geometry"))
        root = _existing_absolute_directory(params["root_path"], "root_path")
        source_nodes = params.get("source_nodes")
        if source_nodes is not None:
            if not isinstance(source_nodes, list) or not source_nodes:
                raise ValueError("source_nodes must be a non-empty array when provided")
            items = [self._export_item(geometry, name) for name in source_nodes]
        else:
            items = [
                item
                for item in self._mari.exports.exportItemList(geometry)
                if bool(_optional_call(item, "exportEnabled", True))
            ]
        if not items:
            raise RuntimeError("No enabled Mari export items were selected")
        overrides = params.get("overrides", {})
        if not isinstance(overrides, dict):
            raise ValueError("overrides must be an object")
        allowed_overrides = {"RESOLUTION", "COLORSPACE", "DEPTH", "POST_PROCESS"}
        unexpected = sorted(set(overrides) - allowed_overrides)
        if unexpected:
            raise ValueError("Unsupported export overrides: %s" % ", ".join(unexpected))
        planned = {
            str(_optional_call(item, "sourceNodeName", "")): _resolved_paths(item, str(root))
            for item in items
        }
        export_overrides = dict(overrides)
        export_overrides["BACKGROUND_EXPORT"] = True
        self._mari.exports.exportTextures(items, str(root), export_overrides)
        return {
            "geometry": _entity_name(geometry),
            "root_path": str(root),
            "background_export": True,
            "scheduled_item_count": len(items),
            "planned_files": planned,
        }

    # Resolution helpers ---------------------------------------------------------------

    def _current_project(self, required: bool = True) -> Any:
        project = self._mari.projects.current()
        if required and project is None:
            raise RuntimeError("No Mari project is open")
        return project

    def _require_closed_project(self, operation: str) -> None:
        if self._current_project(required=False) is not None:
            raise RuntimeError("Close the current Mari project before %s a project" % operation)

    def _find_project(self, identifier: str) -> Any:
        for project in self._mari.projects.list():
            if identifier in {
                _entity_name(project),
                str(_optional_call(project, "uuid", "") or ""),
            }:
                return project
        return None

    def _new_project_since(self, known_projects: set[str]) -> Any:
        for project in self._mari.projects.list():
            identity = str(_optional_call(project, "uuid", "") or _entity_name(project))
            if identity not in known_projects:
                return project
        return None

    def _geometry(self, value: Any = None) -> Any:
        self._current_project()
        if value is None or str(value).strip() == "":
            geometry = self._mari.geo.current()
        else:
            name = _non_empty_string(value, "geometry")
            geometry = self._mari.geo.find(name)
            if geometry is None:
                geometry = next(
                    (item for item in self._mari.geo.list() if _entity_name(item) == name), None
                )
        if geometry is None:
            raise ValueError("Mari geometry was not found: %s" % (value or "<current>"))
        return geometry

    @staticmethod
    def _channel(geometry: Any, value: Any = None) -> Any:
        if value is None or str(value).strip() == "":
            channel = geometry.currentChannel()
        else:
            name = _non_empty_string(value, "channel")
            channel = geometry.findChannel(name)
            if channel is None:
                channel = next(
                    (item for item in geometry.channelList() if _entity_name(item) == name), None
                )
        if channel is None:
            raise ValueError("Mari channel was not found: %s" % (value or "<current>"))
        return channel

    @staticmethod
    def _node(graph: Any, value: Any) -> Any:
        name = _non_empty_string(value, "node")
        node = next(
            (
                item
                for item in graph.nodeList()
                if name in {_entity_name(item), _node_identifier(item)}
            ),
            None,
        )
        if node is None:
            raise ValueError("Mari node was not found: %s" % name)
        return node

    @staticmethod
    def _layer(channel: Any, value: Any) -> Any:
        name = _non_empty_string(value, "layer")
        layer = channel.findLayer(name)
        if layer is None:
            layer = next((item for item in channel.layerList() if _entity_name(item) == name), None)
        if layer is None:
            raise ValueError("Mari layer was not found: %s" % name)
        return layer

    @staticmethod
    def _shader(geometry: Any, value: Any) -> Any:
        name = _non_empty_string(value, "shader")
        shader = geometry.findShader(name)
        if shader is None:
            shader = next(
                (item for item in geometry.shaderList() if _entity_name(item) == name), None
            )
        if shader is None:
            raise ValueError("Mari shader was not found: %s" % name)
        return shader

    def _image(self, value: Any) -> Any:
        name = _non_empty_string(value, "image")
        for image in self._mari.images.list():
            if name in {_image_identifier(image), _entity_name(image)}:
                return image
        getter = getattr(self._mari.images, "getImage", None)
        image = getter(name) if callable(getter) else None
        if image is None:
            raise ValueError("Mari image was not found: %s" % name)
        return image

    def _export_item(self, geometry: Any, source_node: Any, required: bool = True) -> Any:
        name = _non_empty_string(source_node, "source_node")
        item = next(
            (
                value
                for value in self._mari.exports.exportItemList(geometry)
                if str(_optional_call(value, "sourceNodeName", "")) == name
            ),
            None,
        )
        if required and item is None:
            raise ValueError("Mari export item was not found for source node: %s" % name)
        return item

    def _depth(self, value: Any) -> Any:
        key = str(value).casefold()
        attributes = {
            "8": "DEPTH_BYTE",
            "byte": "DEPTH_BYTE",
            "16": "DEPTH_HALF",
            "half": "DEPTH_HALF",
            "32": "DEPTH_FLOAT",
            "float": "DEPTH_FLOAT",
        }
        attribute = attributes.get(key)
        if attribute is None:
            raise ValueError("depth must be one of: byte, half, float")
        return getattr(self._mari.Image, attribute)

    def _color(self, value: Any) -> Any:
        if not isinstance(value, list) or len(value) not in {3, 4}:
            raise ValueError("fill_color must contain three or four numbers")
        values = [_bounded_number(item, "fill_color", -65504.0, 65504.0) for item in value]
        if len(values) == 3:
            values.append(1.0)
        return self._mari.Color(*values)

    def _channel_info(self, value: Any) -> Any:
        if not isinstance(value, dict):
            raise ValueError("each channel must be an object")
        _require_keys(value, {"name", "width", "height", "depth", "fill_color"}, {"name"})
        name = _non_empty_string(value["name"], "channel.name")
        if set(value) == {"name"}:
            return self._mari.ChannelInfo(name)
        width = _bounded_int(value.get("width", 2048), "channel.width", 1, 32768)
        height = _bounded_int(value.get("height", 2048), "channel.height", 1, 32768)
        depth = self._depth(value.get("depth", "half"))
        color = self._color(value.get("fill_color", [0.0, 0.0, 0.0, 0.0]))
        return self._mari.ChannelInfo(name, width, height, depth, color)

    def _host_value(self, value: Any, geometry: Any) -> Any:
        if not isinstance(value, dict):
            return value
        if set(value) == {"color"}:
            return self._color(value["color"])
        if set(value) == {"channel"}:
            return self._channel(geometry, value["channel"])
        raise ValueError("Structured shader values support only color or channel references")


def _project_summary(project: Any) -> Dict[str, Any]:
    return {
        "name": _entity_name(project),
        "uuid": str(_optional_call(project, "uuid", "") or ""),
        "dirty": bool(_optional_call(project, "isDirty", False)),
        "modified": bool(_optional_call(project, "isModified", False)),
    }


def _geometry_summary(geometry: Any, mari_module: Any) -> Dict[str, Any]:
    graph = _optional_call(geometry, "nodeGraph")
    channels = list(_optional_call(geometry, "channelList", []) or [])
    shaders = list(_optional_call(geometry, "shaderList", []) or [])
    patches = list(_optional_call(geometry, "patchList", []) or [])
    current_geo = _optional_call(mari_module.geo, "current")
    return {
        "name": _entity_name(geometry),
        "current": geometry is current_geo,
        "selected": bool(_optional_call(geometry, "isSelected", False)),
        "current_version": str(_optional_call(geometry, "currentVersionName", "") or ""),
        "channel_count": len(channels),
        "shader_count": len(shaders),
        "node_count": len(_optional_call(graph, "nodeList", []) or []) if graph else 0,
        "patch_count": len(patches),
        "is_ptex": bool(_optional_call(geometry, "isPtex", False)),
    }


def _channel_summary(channel: Any, geometry: Any) -> Dict[str, Any]:
    current = _optional_call(geometry, "currentChannel")
    layers = list(_optional_call(channel, "layerList", []) or [])
    return {
        "name": _entity_name(channel),
        "current": channel is current,
        "width": _json_value(_optional_call(channel, "width")),
        "height": _json_value(_optional_call(channel, "height")),
        "depth": _json_value(_optional_call(channel, "depth")),
        "colorspace": _json_value(_optional_call(channel, "colorSpace")),
        "locked": bool(_optional_call(channel, "isLocked", False)),
        "ptex": bool(_optional_call(channel, "isPtex", False)),
        "shader_stack": bool(_optional_call(channel, "isShaderStack", False)),
        "layer_count": len(layers),
    }


def _node_summary(node: Any) -> Dict[str, Any]:
    ports = list(_optional_call(node, "inputPortNames", []) or [])
    inputs: Dict[str, Optional[str]] = {}
    for port in ports:
        try:
            source = node.inputNode(port)
        except Exception:
            source = None
        inputs[str(port)] = _node_identifier(source) if source is not None else None
    return {
        "name": _entity_name(node),
        "node_name": _node_identifier(node),
        "type_id": str(_optional_call(node, "typeID", "") or ""),
        "selected": bool(_optional_call(node, "isSelected", False)),
        "inputs": inputs,
    }


def _app_version(app: Any) -> str:
    version = _optional_call(app, "version", "unknown")
    string_method = getattr(version, "string", None)
    if callable(string_method):
        try:
            return str(string_method())
        except Exception:
            pass
    return str(version)


def _layer_summary(layer: Any) -> Dict[str, Any]:
    layer_type = next(
        (
            label
            for label, method in (
                ("paint", "isPaintableLayer"),
                ("group", "isGroupLayer"),
                ("graph", "isGraphLayer"),
                ("adjustment", "isAdjustmentLayer"),
                ("procedural", "isProceduralLayer"),
                ("channel", "isChannelLayer"),
                ("shader", "isShaderLayer"),
                ("bake_point", "isBakePointLayer"),
            )
            if bool(_optional_call(layer, method, False))
        ),
        "unknown",
    )
    return {
        "name": _entity_name(layer),
        "type": layer_type,
        "visible": bool(_optional_call(layer, "isVisible", True)),
        "locked": bool(_optional_call(layer, "isLocked", False)),
        "selected": bool(_optional_call(layer, "isSelected", False)),
        "blend_mode": _json_value(_optional_call(layer, "blendMode")),
        "blend_mode_name": str(_optional_call(layer, "blendModeName", "") or ""),
        "blend_amount": _json_value(_optional_call(layer, "blendAmount")),
    }


def _shader_summary(shader: Any, current: Any) -> Dict[str, Any]:
    parameter_names = [
        str(item) for item in (_optional_call(shader, "parameterNameList", []) or [])
    ]
    parameters = {}
    for name in parameter_names:
        try:
            parameters[name] = _json_value(shader.getParameter(name))
        except Exception as exc:
            parameters[name] = {"error": str(exc)}
    return {
        "name": _entity_name(shader),
        "current": shader is current,
        "system": bool(_optional_call(shader, "isSystemShader", False)),
        "inputs": [str(item) for item in (_optional_call(shader, "inputNameList", []) or [])],
        "parameters": parameters,
        "node": _node_identifier(_optional_call(shader, "shaderNode")),
    }


def _image_summary(image: Any) -> Dict[str, Any]:
    if isinstance(image, str):
        return {"name": image, "path": image}
    return {
        "name": _entity_name(image),
        "path": str(
            _optional_call(image, "mostRelevantPath", _optional_call(image, "filePath", "")) or ""
        ),
        "width": _json_value(_optional_call(image, "width")),
        "height": _json_value(_optional_call(image, "height")),
        "depth": _json_value(_optional_call(image, "depth")),
        "uniform": bool(_optional_call(image, "isUniform", False)),
    }


def _export_item_summary(item: Any, root: Optional[str] = None) -> Dict[str, Any]:
    return {
        "source_node": str(_optional_call(item, "sourceNodeName", "") or ""),
        "file_template": str(_optional_call(item, "fileTemplate", "") or ""),
        "enabled": bool(_optional_call(item, "exportEnabled", False)),
        "resolution": _json_value(_optional_call(item, "resolution")),
        "colorspace": _json_value(_optional_call(item, "colorspace")),
        "depth": _json_value(_optional_call(item, "depth")),
        "uv_indices": _json_value(_optional_call(item, "uvIndexList", [])),
        "post_process": str(_optional_call(item, "postProcessCommand", "") or ""),
        "resolved_paths": _resolved_paths(item, root) if root else [],
        "errors": _json_value(_optional_call(item, "errorStringList", [])),
        "warnings": _json_value(_optional_call(item, "warningStringList", [])),
    }


def _resolved_paths(item: Any, root: str) -> List[str]:
    try:
        return [str(value) for value in item.resolveExportFilePaths(root)]
    except Exception:
        return []


def _optional_call(target: Any, name: str, default: Any = None) -> Any:
    if target is None:
        return default
    value = getattr(target, name, None)
    if not callable(value):
        return default if value is None else value
    try:
        return value()
    except Exception:
        return default


def _entity_name(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(_optional_call(value, "name", "") or "")


def _node_identifier(value: Any) -> str:
    if value is None:
        return ""
    return str(_optional_call(value, "nodeName", "") or _entity_name(value))


def _image_identifier(value: Any) -> str:
    return _entity_name(value) or str(
        _optional_call(value, "mostRelevantPath", _optional_call(value, "filePath", "")) or ""
    )


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_value(item) for item in value]
    try:
        return [_json_value(item) for item in value]
    except TypeError:
        return str(value)


def _require_keys(
    params: Mapping[str, Any], allowed: set[str], required: Optional[set[str]] = None
) -> None:
    required = required or set()
    unexpected = sorted(set(params) - allowed)
    if unexpected:
        raise ValueError("Unexpected parameters: %s" % ", ".join(unexpected))
    missing = sorted(key for key in required if key not in params)
    if missing:
        raise ValueError("Missing required parameters: %s" % ", ".join(missing))


def _non_empty_string(value: Any, name: str) -> str:
    if value is None:
        raise ValueError("%s must be a non-empty string" % name)
    text = str(value).strip()
    if not text:
        raise ValueError("%s must be a non-empty string" % name)
    return text


def _bounded_int(value: Any, name: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("%s must be an integer" % name)
    if not minimum <= value <= maximum:
        raise ValueError("%s must be between %d and %d" % (name, minimum, maximum))
    return value


def _bounded_number(value: Any, name: str, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("%s must be numeric" % name)
    result = float(value)
    if not minimum <= result <= maximum:
        raise ValueError("%s must be between %s and %s" % (name, minimum, maximum))
    return result


def _image_set_size(mari_module: Any, value: Any) -> Any:
    size = _bounded_int(value, "size", 256, 32768)
    allowed = {256, 512, 1024, 2048, 4096, 8192, 16384, 32768}
    if size not in allowed:
        raise ValueError("size must be a supported power-of-two Mari image size")
    return mari_module.ImageSet.Size(size)


def _shader_type(available_values: Any, value: Any, shader_kind: str) -> str:
    requested = _non_empty_string(value, "shader_type")
    available = [str(item) for item in available_values]
    if requested in available:
        return requested
    matches = [item for item in available if item.rsplit("/", 1)[-1] == requested]
    if len(matches) == 1:
        return matches[0]
    raise ValueError("Unknown Mari %s shader type: %s" % (shader_kind, requested))


def _existing_absolute_file(value: Any, name: str) -> Path:
    path = Path(str(value or "")).expanduser()
    if not path.is_absolute() or not path.is_file():
        raise ValueError("%s must be an existing absolute file path" % name)
    return path.resolve()


def _existing_absolute_directory(value: Any, name: str) -> Path:
    path = Path(str(value or "")).expanduser()
    if not path.is_absolute() or not path.is_dir():
        raise ValueError("%s must be an existing absolute directory" % name)
    return path.resolve()


def _absolute_output_file(value: Any, name: str, extensions: set[str]) -> Path:
    path = Path(str(value or "")).expanduser()
    if not path.is_absolute():
        raise ValueError("%s must be an absolute path" % name)
    path = path.resolve()
    if path.suffix.casefold() not in extensions:
        raise ValueError("%s must use one of: %s" % (name, ", ".join(sorted(extensions))))
    if not path.parent.is_dir():
        raise ValueError("%s parent directory does not exist" % name)
    return path
