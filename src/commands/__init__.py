import enum
import inspect
import re
from functools import wraps


from prompt_toolkit.completion import NestedCompleter
from prompt_toolkit.document import Document
from prompt_toolkit.validation import DummyValidator, Validator, ValidationError

from src.exceptions.console_exception import ConsoleInitException
from src.utils import get_command_token


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


class GeneralValidator(Validator):
    def __init__(self, console, func):
        self.console = console
        self.func = func
        super().__init__()

    def validate(self, document: Document) -> None:
        self.argument_count_validate(document.text)
        self.custom_validate(document.text)

    def custom_validate(self, text: str):
        pass

    def argument_count_validate(self, text):
        sig = inspect.signature(self.func)
        func_param_count = len(sig.parameters) - 1
        try:
            if func_param_count <= 0 and text != "":
                raise ValidationError(message=f"Too many parameters set!")
        except ValueError:
            return


class CommandValidator(Validator):
    def __init__(self, command_validators: dict, enable_undefined_command=False):
        self.command_validators = command_validators
        self.enable_undefined_command = enable_undefined_command
        super().__init__()

    def validate(self, document: Document) -> None:
        try:
            cmd = document.text.strip()
            token = get_command_token(cmd)
            if token in self.command_validators.keys():
                cmd_validator = self.command_validators[token]
                cmd_validator.validate(Document(text=cmd[len(token)+1:]))
            else:
                if not self.enable_undefined_command:
                    raise ValidationError(message="Bad command")
        except ValueError:
            return


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
        funcs = self._get_funcs()
        self._collect_completer_and_validator(funcs)

    def _get_funcs(self):
        cls = self.__class__
        funcs = []
        for member_name in dir(cls):
            if member_name.startswith("_"):
                continue
            member = getattr(cls, member_name)
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

