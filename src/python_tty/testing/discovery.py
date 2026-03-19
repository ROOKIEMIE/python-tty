import inspect
import types
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from python_tty.commands import BaseCommands
from python_tty.commands.registry import COMMAND_REGISTRY
from python_tty.consoles.registry import REGISTRY
from python_tty.testing.decorators import TEST_META_ATTR, TESTABLE_ATTR


@dataclass
class DiscoveredTestCase:
    """Metadata for a single command test case discovered from command classes."""

    command_id: str
    command_name: str
    console_name: Optional[str]
    console_cls: Optional[type]
    commands_cls: type
    method_name: str
    method: object
    class_marked: bool
    method_marked: bool
    test_meta: Dict[str, Any] = field(default_factory=dict)


class DiscoveredTestSuite:
    """Stable suite wrapper returned by discover_tests()."""

    def __init__(self, cases: Sequence[DiscoveredTestCase]):
        ordered = sorted(cases, key=lambda c: c.command_id)
        deduped: Dict[str, DiscoveredTestCase] = {}
        for case in ordered:
            deduped[case.command_id] = case
        self._cases: Tuple[DiscoveredTestCase, ...] = tuple(deduped.values())
        self._cases_by_id: Dict[str, DiscoveredTestCase] = dict(deduped)

    @property
    def cases(self) -> Tuple[DiscoveredTestCase, ...]:
        return self._cases

    def list_cases(self) -> List[DiscoveredTestCase]:
        return list(self._cases)

    def get_case(self, command_id: str) -> Optional[DiscoveredTestCase]:
        return self._cases_by_id.get(command_id)

    def ids(self) -> List[str]:
        return [case.command_id for case in self._cases]

    def __len__(self):
        return len(self._cases)

    def __iter__(self):
        return iter(self._cases)


def discover_tests(*targets, command_ids: Optional[Iterable[str]] = None):
    """Explicitly discover command test cases from modules/classes/methods/ids."""

    expanded_targets = _expand_targets(targets)
    explicit_command_ids: Set[str] = set(command_ids or [])
    commands_classes: List[type] = []
    explicit_classes: Set[type] = set()
    explicit_methods: Set[object] = set()

    for target in expanded_targets:
        if isinstance(target, str):
            explicit_command_ids.add(target)
            continue

        if inspect.isclass(target) and issubclass(target, BaseCommands):
            commands_classes.append(target)
            explicit_classes.add(target)
            continue

        if isinstance(target, types.ModuleType):
            commands_classes.extend(_collect_commands_classes_from_module(target))
            continue

        if isinstance(target, BaseCommands):
            commands_cls = target.__class__
            commands_classes.append(commands_cls)
            explicit_classes.add(commands_cls)
            continue

        func = _unwrap_callable(target)
        if callable(func) and hasattr(func, "info"):
            explicit_methods.add(func)
            owner_cls = _resolve_owner_commands_cls(func)
            if owner_cls is not None:
                commands_classes.append(owner_cls)
            continue

        raise ValueError(f"Unsupported discover_tests target: {target!r}")

    if explicit_command_ids:
        commands_classes.extend(_collect_classes_by_command_ids(explicit_command_ids))

    unique_classes = _unique_ordered(commands_classes)
    cases: List[DiscoveredTestCase] = []

    for commands_cls in unique_classes:
        class_marked = bool(getattr(commands_cls, TESTABLE_ATTR, False))
        class_meta = _read_meta(commands_cls)
        is_explicit_class = commands_cls in explicit_classes
        console_bindings = _resolve_console_bindings(commands_cls)
        command_defs = COMMAND_REGISTRY.collect_from_commands_cls(commands_cls)

        for command_def in command_defs:
            method = _resolve_method(commands_cls, command_def.func)
            method_marked = bool(getattr(method, TESTABLE_ATTR, False))
            method_meta = _read_meta(method)
            method_selected = _is_method_selected(method, explicit_methods)

            for console_name, console_cls in console_bindings:
                command_id = _build_command_id(console_name, command_def.func_name)
                by_id = command_id in explicit_command_ids
                include = is_explicit_class or class_marked or method_marked or method_selected or by_id
                if not include:
                    continue
                case_meta = dict(class_meta)
                case_meta.update(method_meta)
                cases.append(
                    DiscoveredTestCase(
                        command_id=command_id,
                        command_name=command_def.func_name,
                        console_name=console_name,
                        console_cls=console_cls,
                        commands_cls=commands_cls,
                        method_name=method.__name__,
                        method=method,
                        class_marked=class_marked,
                        method_marked=method_marked,
                        test_meta=case_meta,
                    )
                )

    return DiscoveredTestSuite(cases)


def _expand_targets(targets) -> List[object]:
    expanded: List[object] = []
    for target in targets:
        if target is None:
            continue
        if isinstance(target, (list, tuple, set)):
            expanded.extend(_expand_targets(tuple(target)))
            continue
        expanded.append(target)
    return expanded


def _collect_commands_classes_from_module(module: types.ModuleType) -> List[type]:
    classes: List[type] = []
    for _, cls in inspect.getmembers(module, inspect.isclass):
        if not issubclass(cls, BaseCommands) or cls is BaseCommands:
            continue
        if cls.__module__ != module.__name__:
            continue
        classes.append(cls)
    return classes


def _collect_classes_by_command_ids(command_ids: Iterable[str]) -> List[type]:
    classes: List[type] = []
    for command_id in command_ids:
        console_name = _extract_console_name(command_id)
        if not console_name:
            continue
        for registry_name, console_cls, _ in REGISTRY.iter_consoles():
            if registry_name != console_name:
                continue
            commands_cls = COMMAND_REGISTRY.get_commands_cls(console_cls)
            if commands_cls is not None:
                classes.append(commands_cls)
    return classes


def _resolve_console_bindings(commands_cls) -> List[Tuple[str, Optional[type]]]:
    bindings: List[Tuple[str, Optional[type]]] = []
    for console_name, console_cls, _ in REGISTRY.iter_consoles():
        resolved = COMMAND_REGISTRY.get_commands_cls(console_cls)
        if resolved is commands_cls:
            bindings.append((console_name, console_cls))
    if bindings:
        return bindings
    fallback = getattr(commands_cls, "console_name", None)
    if not fallback:
        fallback = commands_cls.__name__.lower()
    return [(fallback, None)]


def _extract_console_name(command_id: str) -> Optional[str]:
    if not isinstance(command_id, str):
        return None
    if not command_id.startswith("cmd:"):
        return None
    parts = command_id.split(":", 2)
    if len(parts) != 3:
        return None
    return parts[1] or None


def _resolve_owner_commands_cls(func) -> Optional[type]:
    module = inspect.getmodule(func)
    if module is None:
        return None
    qualname = getattr(func, "__qualname__", "")
    qualname = qualname.split(".<locals>", 1)[0]
    if "." not in qualname:
        return None
    cls_path = qualname.rsplit(".", 1)[0]
    owner = module
    for part in cls_path.split("."):
        owner = getattr(owner, part, None)
        if owner is None:
            return None
    if inspect.isclass(owner) and issubclass(owner, BaseCommands):
        return owner
    return None


def _resolve_method(commands_cls, fallback):
    name = getattr(fallback, "__name__", None)
    if name and hasattr(commands_cls, name):
        return getattr(commands_cls, name)
    return fallback


def _is_method_selected(method, selected_methods: Set[object]) -> bool:
    method = _unwrap_callable(method)
    for selected in selected_methods:
        if _unwrap_callable(selected) is method:
            return True
    return False


def _unwrap_callable(value):
    return getattr(value, "__func__", value)


def _read_meta(target) -> Dict[str, Any]:
    meta = getattr(target, TEST_META_ATTR, None)
    if isinstance(meta, dict):
        return dict(meta)
    return {}


def _unique_ordered(values: Iterable[type]) -> List[type]:
    seen: Set[type] = set()
    ordered: List[type] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def _build_command_id(console_name: str, command_name: str):
    return f"cmd:{console_name}:{command_name}"
