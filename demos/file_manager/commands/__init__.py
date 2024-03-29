import enum
import inspect
import re
import shlex
from abc import ABC
from functools import wraps

from prompt_toolkit.completion import NestedCompleter
from prompt_toolkit.document import Document
from prompt_toolkit.validation import DummyValidator, Validator, ValidationError
from demos.file_manager.consoles import proxy_print
from demos.file_manager.exceptions.console_exception import ConsoleExit, ConsoleInitException
from demos.file_manager.utils.table import Table


class CommandStyle(enum.Enum):
    NONE = 0  # ClassName => ClassName
    LOWERCASE = 1  # ClassName => classname
    UPPERCASE = 2  # ClassName => CLASSNAME
    POWERSHELL = 3  # ClassName => Class-Name
    SLUGIFIED = 4  # ClassName => class-name


class CommandInfo:
    def __init__(self, func_name, func_description,
                 completer=None, validator=None,
                 command_alias=None):
        self.func_name = func_name
        self.func_description = func_description
        self.completer = completer
        self.validator = validator
        if command_alias is None:
            self.alias = []
        else:
            if type(command_alias) == str:
                self.alias = [command_alias]
            elif type(command_alias) == list:
                self.alias = command_alias
            else:
                self.alias = []


def define_command_style(command_name, style):
    if style == CommandStyle.NONE:
        return command_name
    elif style == CommandStyle.LOWERCASE:
        return command_name.lower()
    elif style == CommandStyle.UPPERCASE:
        return command_name.upper()
    command_name = re.sub(r'(.)([A-Z][a-z]+)', r'\1-\2', command_name)
    command_name = re.sub(r'([a-z0-9])([A-Z])', r'\1-\2', command_name)
    if style == CommandStyle.POWERSHELL:
        return command_name
    elif style == CommandStyle.SLUGIFIED:
        return command_name.lower()


def register_command(command_name: str, command_description: str, command_alias=None,
                     command_style=CommandStyle.LOWERCASE,
                     completer=None, validator=None):
    def inner_wrapper(func):
        func.info = CommandInfo(define_command_style(command_name, command_style), command_description,
                                completer, validator, command_alias)
        func.type = None

        @wraps(func)
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)
            return result

        return wrapper

    return inner_wrapper


class GeneralValidator(Validator, ABC):
    def __init__(self, console, func):
        self.console = console
        self.func = func
        super().__init__()


class NoneArgumentValidator(GeneralValidator):
    def __init__(self, console, func):
        super().__init__(console, func)

    def validate(self, document: Document) -> None:
        sig = inspect.signature(self.func)
        name_list = []
        for name, param in sig.parameters.items():
            name_list.append(name)
        args = shlex.split(document.text)
        if len(args) != (len(name_list) - 1):
            raise ValidationError(message="Too many arguments!")


class CommandValidator(Validator):
    def __init__(self, command_validators: dict, enable_undefined_command=False):
        self.command_validators = command_validators
        self.enable_undefined_command = enable_undefined_command
        super().__init__()

    def validate(self, document: Document) -> None:
        args_l = shlex.split(document.text.strip())
        if len(args_l) <= 0:
            return
        cmd = args_l[0]
        if cmd in self.command_validators.keys():
            cmd_validator = self.command_validators[cmd]
            cmd_validator.validate(Document(text=' '.join(args_l[1:])))
        else:
            if not self.enable_undefined_command:
                raise ValidationError(message="Bad command")


class BaseCommands:
    def __init__(self, console):
        self.console = console
        self.command_completers = {}
        self.command_validators = {}
        self.command_funcs = {}
        self._init_funcs()
        self.completer = NestedCompleter.from_nested_dict(self.command_completers)
        self.validator = CommandValidator(self.command_validators, self.enable_undefined_command)

    @property
    def enable_undefined_command(self):
        return False

    def _init_funcs(self):
        # Separate function and inner class
        funcs = self._get_funcs()
        self._collect_completer_and_validator(funcs)

    def _get_funcs(self):
        cls = self.__class__
        funcs = []
        for member_name in dir(cls):
            # Skip all include '_' method
            if member_name.startswith("_"):
                continue
            member = getattr(cls, member_name)
            # Include 'type' attr should be collected
            if (inspect.ismethod(member) or inspect.isfunction(member)) and hasattr(member, "type"):
                funcs.append(member)
        return funcs

    def _collect_completer_and_validator(self, funcs):
        if self.console is None:
            raise ConsoleInitException("Console is None")
        for func in funcs:
            command_info: CommandInfo = func.info
            self._map_components(command_info.func_name, func, command_info.completer, command_info.validator)
            if len(command_info.alias) > 0:
                for alia in command_info.alias:
                    self._map_components(alia, func, command_info.completer, command_info.validator)

    def _map_components(self, command_name, func, completer, validator):
        self.command_funcs[command_name] = func
        if completer is None:
            self.command_completers[command_name] = None
        else:
            self.command_completers[command_name] = completer(self.console)
        if validator is None:
            self.command_validators[command_name] = DummyValidator()
        else:
            self.command_validators[command_name] = validator(self.console, func)

    @register_command("quit", "Quit Console", "exit", validator=NoneArgumentValidator)
    def run_quit(self):
        raise ConsoleExit

    @register_command("help", "Display help information", ["?"], validator=NoneArgumentValidator)
    def run_help(self):
        header = ["Command", "Description"]
        base_funcs = []
        customer_funcs = []
        base_commands_funcs = [member[1] for member in inspect.getmembers(BaseCommands, inspect.isfunction)]
        for name, func in self.command_funcs.items():
            if func in base_commands_funcs:
                base_funcs.append([name, func.info.func_description])
            else:
                customer_funcs.append([name, func.info.func_description])
        proxy_print("")
        proxy_print(Table(header, base_funcs, "Core Commands"))
        proxy_print("")
        proxy_print(Table(header, customer_funcs, "Customer Commands"))
        proxy_print("")
