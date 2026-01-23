import importlib


DEFAULT_CONSOLE_MODULES = ()


def load_consoles(modules=None):
    """Import console modules so class decorators can register themselves."""
    if modules is None:
        modules = DEFAULT_CONSOLE_MODULES
    elif not isinstance(modules, (list, tuple)):
        modules = [modules]
    for module in modules:
        importlib.import_module(module)
