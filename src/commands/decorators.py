from functools import wraps
from src.commands import BaseCommands, CommandInfo, CommandStyle
from src.commands.registry import COMMAND_REGISTRY, define_command_style
from src.exceptions.console_exception import ConsoleInitException


def commands(commands_cls):
    if not issubclass(commands_cls, BaseCommands):
        raise ConsoleInitException("Commands must inherit BaseCommands")

    def decorator(console_cls):
        setattr(console_cls, "__commands_cls__", commands_cls)
        COMMAND_REGISTRY.register_console_commands(console_cls, commands_cls)
        return console_cls

    return decorator


def register_command(command_name: str, command_description: str, command_alias=None,
                     command_style=CommandStyle.LOWERCASE,
                     completer=None, validator=None, arg_spec=None):
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