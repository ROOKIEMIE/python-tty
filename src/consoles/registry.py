from src.exceptions.console_exception import ConsoleInitException


def _get_console_name(console_cls):
    name = getattr(console_cls, "console_name", None)
    if name:
        return name
    name = getattr(console_cls, "CONSOLE_NAME", None)
    if name:
        return name
    return console_cls.__name__.lower()


def _get_console_kwargs(console_cls):
    kwargs = getattr(console_cls, "console_kwargs", None)
    if kwargs is None:
        return {}
    if not isinstance(kwargs, dict):
        raise ConsoleInitException("console_kwargs must be dict")
    return kwargs


class SubConsoleEntry:
    def __init__(self, console_cls, parent_name, name):
        self.console_cls = console_cls
        self.parent_name = parent_name
        self.name = name


class ConsoleRegistry:
    def __init__(self):
        self._root_cls = None
        self._root_name = None
        self._subs = {}

    def set_root(self, console_cls):
        if self._root_cls is not None:
            raise ConsoleInitException("Root console already set")
        self._root_cls = console_cls
        self._root_name = _get_console_name(console_cls)

    def add_sub(self, console_cls, parent_name):
        name = _get_console_name(console_cls)
        if name == self._root_name or name in self._subs:
            raise ConsoleInitException(f"Console name duplicate [{name}]")
        self._subs[name] = SubConsoleEntry(console_cls, parent_name, name)

    def add_multi(self, console_cls, parent_map):
        if not isinstance(parent_map, dict) or len(parent_map) <= 0:
            raise ConsoleInitException("Multi console mapping is empty")
        for parent_name, instance_name in parent_map.items():
            if not isinstance(parent_name, str) or parent_name == "":
                raise ConsoleInitException("Multi console parent name is empty")
            if not isinstance(instance_name, str) or instance_name == "":
                raise ConsoleInitException("Multi console instance name is empty")
            resolved_name = _resolve_instance_name(parent_name, instance_name)
            if resolved_name == self._root_name or resolved_name in self._subs:
                raise ConsoleInitException(f"Console name duplicate [{resolved_name}]")
            self._subs[resolved_name] = SubConsoleEntry(console_cls, parent_name, resolved_name)

    def register_all(self, manager):
        if self._root_cls is None:
            raise ConsoleInitException("Root console not set")
        manager.set_root_name(self._root_name)
        manager.register(self._root_name, self._root_cls, **_get_console_kwargs(self._root_cls))
        for name, entry in self._subs.items():
            manager.register(name, entry.console_cls, **_get_console_kwargs(entry.console_cls))
        for name, entry in self._subs.items():
            if not manager.is_registered(entry.parent_name):
                raise ConsoleInitException(
                    f"Parent console [{entry.parent_name}] for [{name}] not registered"
                )
        console_tree = _build_console_tree(self._root_name, self._subs)
        manager.set_console_tree(console_tree)


def _resolve_instance_name(parent_name, instance_name):
    prefix = f"{parent_name}_"
    if instance_name.startswith(prefix):
        return instance_name
    return f"{prefix}{instance_name}"


def _build_console_tree(root_name, sub_entries):
    children_map = {}
    for name, entry in sub_entries.items():
        children_map.setdefault(entry.parent_name, []).append(name)
    for parent_name, children in children_map.items():
        children.sort()
    all_names = [root_name]
    all_names.extend(list(sub_entries.keys()))
    for name in all_names:
        if name not in children_map:
            children_map[name] = []
    return {
        "root": root_name,
        "children": children_map,
    }


REGISTRY = ConsoleRegistry()
