from prompt_toolkit.styles import Style

from src.commands.decorators import commands
from src.commands.root_commands import RootCommands
from src.consoles import MainConsole, root

message = [
    ('class:host', 'vef1'),
    ('class:prompt', ' '),
    ('class:symbol', '>'),
    ('class:prompt', ' ')
]
style = Style.from_dict({
    # User input(default text)
    '': '',
    'host': '#00aa00 underline',
    'symbol': '#00ffff'
})


@root
@commands(RootCommands)
class RootConsole(MainConsole):
    console_name = "root"

    def __init__(self, parent=None, manager=None):
        super().__init__(message, style, parent=parent, manager=manager)

    def cmd_invoke_miss(self, cmd: str):
        print(f"Invoke os shell command [{cmd}]")

    def clean_console(self):
        super().clean_console()
