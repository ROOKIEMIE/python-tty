import hashlib
import json
from dataclasses import dataclass
from typing import List, Optional

from python_tty.commands.mixins import DefaultCommands
from python_tty.commands.registry import ArgSpec, COMMAND_REGISTRY
from python_tty.consoles.registry import REGISTRY


@dataclass
class _ConsoleEntry:
    name: str
    console_cls: type
    parent: Optional[str]


def export_meta(console_registry=REGISTRY, command_registry=COMMAND_REGISTRY,
                include_default_commands: bool = True):
    """Export console/command metadata as a dict with a revision hash."""
    consoles = []
    entries = _collect_console_entries(console_registry)
    for entry in entries:
        command_defs = command_registry.get_command_defs_for_console(entry.console_cls)
        if not command_defs and include_default_commands:
            command_defs = command_registry.collect_from_commands_cls(DefaultCommands)
        commands = _export_commands(entry.name, command_defs)
        consoles.append({
            "name": entry.name,
            "parent": entry.parent,
            "type": entry.console_cls.__name__,
            "module": entry.console_cls.__module__,
            "commands": commands,
        })
    consoles.sort(key=lambda item: item["name"])
    meta = {
        "version": 1,
        "consoles": consoles,
    }
    meta["revision"] = _compute_revision(meta)
    return meta


def _collect_console_entries(console_registry):
    entries: List[_ConsoleEntry] = []
    root_cls = getattr(console_registry, "_root_cls", None)
    if root_cls is None:
        return entries
    root_name = getattr(console_registry, "_root_name", None)
    if not root_name:
        root_name = _resolve_console_name(root_cls)
    entries.append(_ConsoleEntry(name=root_name, console_cls=root_cls, parent=None))
    subs = getattr(console_registry, "_subs", {})
    for entry in subs.values():
        entries.append(_ConsoleEntry(name=entry.name, console_cls=entry.console_cls, parent=entry.parent_name))
    return entries


def _resolve_console_name(console_cls):
    name = getattr(console_cls, "console_name", None)
    if name:
        return name
    name = getattr(console_cls, "CONSOLE_NAME", None)
    if name:
        return name
    return console_cls.__name__.lower()


def _export_commands(console_name: str, command_defs):
    commands = []
    for command_def in command_defs or []:
        arg_spec = command_def.arg_spec or ArgSpec.from_signature(command_def.func)
        commands.append({
            "id": _build_command_id(console_name, command_def.func_name),
            "name": command_def.func_name,
            "aliases": list(command_def.alias or []),
            "description": command_def.func_description,
            "argspec": {
                "min": arg_spec.min_args,
                "max": arg_spec.max_args,
                "variadic": arg_spec.variadic,
            },
        })
    commands.sort(key=lambda item: item["id"])
    return commands


def _build_command_id(console_name: str, command_name: str):
    return f"cmd:{console_name}:{command_name}"


def _compute_revision(meta):
    payload = dict(meta)
    payload.pop("revision", None)
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


__all__ = [
    "export_meta",
]
