from prompt_toolkit.styles import Style

from src.commands.root_commands import RootCommands
from src.consoles import BaseConsole

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


class RootConsole(BaseConsole):
    def __init__(self):
        super().__init__(message, style)

    def init_commands(self):
        return RootCommands(self)

    def cmd_invoke_miss(self, cmd: str):
        print(f"Invoke os shell command [{cmd}]")

    def clean_console(self):
        super().clean_console()
