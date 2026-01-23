from python_tty.consoles.registry import REGISTRY
from python_tty.exceptions.console_exception import ConsoleInitException


def root(console_cls):
    """Mark a MainConsole subclass as the single root console."""
    from python_tty.consoles import MainConsole
    if not issubclass(console_cls, MainConsole):
        raise ConsoleInitException("Root console must inherit MainConsole")
    REGISTRY.set_root(console_cls)
    return console_cls


def sub(parent_name):
    """Register a SubConsole subclass to a single parent console by name."""
    if not isinstance(parent_name, str) or parent_name == "":
        raise ConsoleInitException("Sub console parent name is empty")

    def decorator(console_cls):
        from python_tty.consoles import SubConsole
        if not issubclass(console_cls, SubConsole):
            raise ConsoleInitException("Sub console must inherit SubConsole")
        REGISTRY.add_sub(console_cls, parent_name)
        return console_cls

    return decorator


def multi(parent_map):
    """Register a reusable SubConsole for multiple parents with instance names."""
    if not isinstance(parent_map, dict) or len(parent_map) <= 0:
        raise ConsoleInitException("Multi console mapping is empty")

    def decorator(console_cls):
        from python_tty.consoles import SubConsole
        if not issubclass(console_cls, SubConsole):
            raise ConsoleInitException("Multi console must inherit SubConsole")
        REGISTRY.add_multi(console_cls, parent_map)
        return console_cls

    return decorator

