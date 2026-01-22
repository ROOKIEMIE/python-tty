from src.commands import BaseCommands
from src.commands.decorators import register_command
from src.commands.general import GeneralValidator
from src.commands.mixins import BackMixin, HelpMixin, QuitMixin


class SubCommands(BaseCommands, HelpMixin, QuitMixin, BackMixin):
    @register_command("debug", "Debug command, display some information", [], validator=GeneralValidator)
    def run_debug(self):
        pass
