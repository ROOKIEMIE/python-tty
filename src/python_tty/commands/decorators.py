from functools import wraps

from prompt_toolkit.completion import Completer
from prompt_toolkit.validation import Validator

from python_tty.commands import BaseCommands
from python_tty.commands.registry import COMMAND_REGISTRY, CommandInfo, CommandStyle, define_command_style
from python_tty.exceptions.console_exception import ConsoleInitException


def commands(commands_cls):
    """Bind a BaseCommands subclass to a Console class for auto command wiring."""
    if not issubclass(commands_cls, BaseCommands):
        raise ConsoleInitException("Commands must inherit BaseCommands")

    def decorator(console_cls):
        from python_tty.consoles import MainConsole, SubConsole
        if not issubclass(console_cls, (MainConsole, SubConsole)):
            raise ConsoleInitException("commands decorator must target a Console class")
        existing = getattr(console_cls, "__commands_cls__", None)
        if existing is not None and existing is not commands_cls:
            raise ConsoleInitException(
                f"{console_cls.__name__} already binds to {existing.__name__}; "
                f"cannot bind to {commands_cls.__name__} again"
            )
        setattr(console_cls, "__commands_cls__", commands_cls)
        COMMAND_REGISTRY.register_console_commands(console_cls, commands_cls)
        return console_cls

    return decorator


def register_command(command_name: str, command_description: str, command_alias=None,
                     command_style=CommandStyle.LOWERCASE,
                     completer=None, validator=None, arg_spec=None):
    """Declare command metadata for a command method on a BaseCommands subclass."""
    if completer is not None and not isinstance(completer, type):
        raise ConsoleInitException("Command completer must be a class")
    if validator is not None and not isinstance(validator, type):
        raise ConsoleInitException("Command validator must be a class")
    if completer is not None and not issubclass(completer, Completer):
        raise ConsoleInitException("Command completer must inherit Completer")
    if validator is not None and not issubclass(validator, Validator):
        raise ConsoleInitException("Command validator must inherit Validator")
    def inner_wrapper(func):
        func.info = CommandInfo(define_command_style(command_name, command_style), command_description,
                                completer, validator, command_alias, arg_spec)
        func.type = None

        @wraps(func)
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)
            return result

        return wrapper

    return inner_wrapper

