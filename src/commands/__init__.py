from prompt_toolkit.completion import NestedCompleter
from prompt_toolkit.document import Document
from prompt_toolkit.validation import DummyValidator, Validator, ValidationError

from src.commands.registry import COMMAND_REGISTRY, ArgSpec
from src.exceptions.console_exception import ConsoleInitException
from src.utils import get_command_token


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
    def __init__(self, console, registry=None):
        self.console = console
        self.registry = registry if registry is not None else COMMAND_REGISTRY
        self.command_defs = []
        self.command_defs_by_name = {}
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
        if self.console is None:
            raise ConsoleInitException("Console is None")
        defs = self.registry.get_command_defs_for_console(self.console.__class__)
        if len(defs) == 0:
            defs = self.registry.collect_from_commands_cls(self.__class__)
        self.command_defs = defs
        self._collect_completer_and_validator(defs)

    def _collect_completer_and_validator(self, defs):
        for command_def in defs:
            self._map_components(command_def)

    def _map_components(self, command_def):
        for command_name in command_def.all_names():
            self.command_funcs[command_name] = command_def.func
            self.command_defs_by_name[command_name] = command_def
            if command_def.completer is None:
                self.command_completers[command_name] = None
            else:
                self.command_completers[command_name] = command_def.completer(self.console)
            self.command_validators[command_name] = self._build_validator(command_def)

    def _build_validator(self, command_def):
        if command_def.validator is None:
            return DummyValidator()
        try:
            return command_def.validator(self.console, command_def.func, command_def.arg_spec)
        except TypeError:
            return command_def.validator(self.console, command_def.func)

    def get_command_def(self, command_name):
        return self.command_defs_by_name.get(command_name)

    def deserialize_args(self, command_def, raw_text):
        if command_def.arg_spec is None:
            arg_spec = ArgSpec.from_signature(command_def.func)
            return arg_spec.parse(raw_text)
        return command_def.arg_spec.parse(raw_text)


