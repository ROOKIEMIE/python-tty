from python_tty.consoles.core import BaseConsole, MainConsole, SubConsole
from python_tty.consoles.decorators import root, sub, multi
from python_tty.consoles.registry import REGISTRY
from python_tty.consoles.loader import DEFAULT_CONSOLE_MODULES

__all__ = [
    "BaseConsole",
    "MainConsole",
    "SubConsole",
    "DEFAULT_CONSOLE_MODULES",
    "REGISTRY",
    "root",
    "sub",
    "multi",
]

