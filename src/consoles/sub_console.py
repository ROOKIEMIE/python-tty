from prompt_toolkit.styles import Style

from src.commands.sub_commands import SubCommands
from src.consoles import BaseConsole


style = Style.from_dict({
    # User input(default text)
    '': '',

    'host': '#00aaaa',
    'symbol': '#00ffaa'
})


class ModuleConsole(BaseConsole):
    def __init__(self, module_name, parent):
        message = [
            ('class:host', module_name),
            ('class:prompt', ' '),
            ('class:symbol', '>'),
            ('class:prompt', ' ')
        ]
        super().__init__(message, style, parent)

    def init_commands(self):
        return SubCommands(self)

    def clean_console(self):
        super().clean_console()
