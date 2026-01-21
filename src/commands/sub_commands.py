from src.commands import BaseCommands
from src.commands.decorators import register_command
from src.commands.general import GeneralValidator
from src.commands.mixins import HelpMixin, QuitMixin
from src.exceptions.console_exception import SubConsoleExit


class SubCommands(BaseCommands, HelpMixin, QuitMixin):
    @register_command("back", "Back to forward tty", validator=GeneralValidator)
    def run_back(self):
        raise SubConsoleExit

    @register_command("debug", "Debug command, display some information", [], validator=GeneralValidator)
    def run_debug(self):
        pass
