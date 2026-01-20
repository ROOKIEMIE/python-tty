from src.commands import BaseCommands, GeneralValidator, register_command
from src.exceptions.console_exception import SubConsoleExit


class SubCommands(BaseCommands):
    @register_command("back", "Back to forward tty", validator=GeneralValidator)
    def run_back(self):
        raise SubConsoleExit

    @register_command("debug", "Debug command, display some information", [], validator=GeneralValidator)
    def run_debug(self):
        pass
