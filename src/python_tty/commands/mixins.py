import inspect

from python_tty.runtime.router import proxy_print
from python_tty.commands import BaseCommands
from python_tty.commands.decorators import register_command
from python_tty.commands.general import GeneralValidator
from python_tty.exceptions.console_exception import ConsoleExit, SubConsoleExit
from python_tty.utils.table import Table


class CommandMixin:
    pass


class BackMixin(CommandMixin):
    @register_command("back", "Back to forward tty", validator=GeneralValidator)
    def run_back(self):
        raise SubConsoleExit


class QuitMixin(CommandMixin):
    @register_command("quit", "Quit Console", ["exit", "q"], validator=GeneralValidator)
    def run_quit(self):
        raise ConsoleExit


class HelpMixin(CommandMixin):
    @register_command("help", "Display help information", ["?"], validator=GeneralValidator)
    def run_help(self):
        header = ["Command", "Description"]
        base_funcs = []
        custom_funcs = []
        base_commands_funcs = []
        for cls in self.__class__.mro():
            if cls is CommandMixin:
                continue
            if issubclass(cls, CommandMixin) and not issubclass(cls, BaseCommands):
                base_commands_funcs.extend([member[1] for member in inspect.getmembers(cls, inspect.isfunction)])
        for name, func in self.command_funcs.items():
            row = [name, func.info.func_description]
            if func in base_commands_funcs:
                base_funcs.append(row)
            else:
                custom_funcs.append(row)
        if base_funcs:
            proxy_print(Table(header, base_funcs, "Core Commands"), source="tty")
        if custom_funcs:
            proxy_print(Table(header, custom_funcs, "Custom Commands"), source="tty")

class DefaultCommands(BaseCommands, HelpMixin, QuitMixin):
    pass
