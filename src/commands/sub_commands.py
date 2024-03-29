from src.commands import BaseCommands, register_command, NoneArgumentValidator
from src.exceptions.console_exception import SubConsoleExit


class SubCommands(BaseCommands):
    @register_command("back", "Back to forward console", validator=NoneArgumentValidator)
    def back(self):
        raise SubConsoleExit
