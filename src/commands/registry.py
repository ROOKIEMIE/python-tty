import re
import inspect
from src.commands import ArgSpec, CommandInfo, CommandStyle


class CommandDef:
    def __init__(self, func_name, func, func_description,
                 command_alias=None, completer=None, validator=None,
                 arg_spec=None):
        self.func_name = func_name
        self.func = func
        self.func_description = func_description
        self.completer = completer
        self.validator = validator
        self.arg_spec = arg_spec
        if command_alias is None:
            self.alias = []
        else:
            self.alias = command_alias

    def all_names(self):
        return [self.func_name] + list(self.alias)


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


class CommandRegistry:
    def __init__(self):
        self._console_command_classes = {}
        self._commands_defs = {}
        self._console_defs = {}

    def register_console_commands(self, console_cls, commands_cls):
        self._console_command_classes[console_cls] = commands_cls

    def get_commands_cls(self, console_cls):
        return self._console_command_classes.get(console_cls)

    def register(self, func, console_cls=None, commands_cls=None,
                 command_name=None, command_description="", command_alias=None,
                 command_style=CommandStyle.LOWERCASE,
                 completer=None, validator=None, arg_spec=None):
        if command_name is None:
            command_name = func.__name__
        info = CommandInfo(define_command_style(command_name, command_style),
                           command_description, completer, validator,
                           command_alias, arg_spec)
        func.info = info
        func.type = None
        command_def = CommandDef(info.func_name, func, info.func_description,
                                 info.alias, info.completer, info.validator,
                                 info.arg_spec)
        if commands_cls is not None:
            self._commands_defs.setdefault(commands_cls, []).append(command_def)
        if console_cls is not None:
            self._console_defs.setdefault(console_cls, []).append(command_def)
        return command_def

    def collect_from_commands_cls(self, commands_cls):
        if commands_cls in self._commands_defs:
            return self._commands_defs[commands_cls]
        defs = []
        for member_name in dir(commands_cls):
            if member_name.startswith("_"):
                continue
            member = getattr(commands_cls, member_name)
            if (inspect.ismethod(member) or inspect.isfunction(member)) and hasattr(member, "info"):
                command_info = member.info
                arg_spec = command_info.arg_spec or ArgSpec.from_signature(member)
                defs.append(CommandDef(command_info.func_name, member,
                                       command_info.func_description,
                                       command_info.alias,
                                       command_info.completer,
                                       command_info.validator,
                                       arg_spec))
        self._commands_defs[commands_cls] = defs
        return defs

    def get_command_defs_for_console(self, console_cls):
        defs = []
        commands_cls = self.get_commands_cls(console_cls)
        if commands_cls is not None:
            defs.extend(self.collect_from_commands_cls(commands_cls))
        defs.extend(self._console_defs.get(console_cls, []))
        return defs


COMMAND_REGISTRY = CommandRegistry()
