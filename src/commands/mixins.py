import inspect

from src import UIEventLevel, proxy_print
from src.commands import GeneralValidator, register_command
from src.exceptions.console_exception import ConsoleExit
from src.utils.table import Table


BASE_COMMAND_CLASSES = []


class QuitMixin:
    @register_command("quit", "Quit Console", ["exit", "q"], validator=GeneralValidator)
    def run_quit(self):
        raise ConsoleExit


class HelpMixin:
    @register_command("help", "Display help information", ["?"], validator=GeneralValidator)
    def run_help(self):
        header = ["Command", "Description"]
        base_funcs = []
        custom_funcs = []
        base_commands_funcs = []
        for cls in BASE_COMMAND_CLASSES:
            base_commands_funcs.extend([member[1] for member in inspect.getmembers(cls, inspect.isfunction)])
        for name, func in self.command_funcs.items():
            row = [name, func.info.func_description]
            if func in base_commands_funcs:
                base_funcs.append(row)
            else:
                custom_funcs.append(row)
        if base_funcs:
            proxy_print(Table(header, base_funcs, "Core Commands"))
        if custom_funcs:
            proxy_print(Table(header, custom_funcs, "Custom Commands"))


BASE_COMMAND_CLASSES = [HelpMixin, QuitMixin]
