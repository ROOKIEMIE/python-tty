from python_tty.commands import BaseCommands
from python_tty.commands.decorators import register_command
from python_tty.commands.general import GeneralValidator
from python_tty.commands.mixins import BackMixin, HelpMixin, QuitMixin


class SubCommands(BaseCommands, HelpMixin, QuitMixin, BackMixin):
    @register_command("debug", "Debug command, display some information", [], validator=GeneralValidator)
    def run_debug(self):
        pass

