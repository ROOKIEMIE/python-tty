from prompt_toolkit.styles import Style

from src.commands.sub_commands import SubCommands
from src.consoles import SubConsole, sub


style = Style.from_dict({
    # User input(default text)
    '': '',
    'host': '#00aaaa',
    'symbol': '#00ffaa'
})


@sub("root")
class ModuleConsole(SubConsole):
    console_name = "module"

    def __init__(self, module_name=None, parent=None, manager=None):
        if module_name is None:
            module_name = self.console_name
        message = [
            ('class:host', module_name),
            ('class:prompt', ' '),
            ('class:symbol', '>'),
            ('class:prompt', ' ')
        ]
        super().__init__(message, style, parent=parent, manager=manager)

    def init_commands(self):
        return SubCommands(self)

    def clean_console(self):
        super().clean_console()
