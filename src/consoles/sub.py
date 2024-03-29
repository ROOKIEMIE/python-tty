from prompt_toolkit.styles import Style
from src.commands import BaseCommands
from src.commands.sub_commands import SubCommands
from src.consoles import BaseConsole

message = [
    ('class:host', 'SubConsole'),
    ('class:prompt', ' '),
    ('class:symbol', '>'),
    ('class:prompt', ' ')
]
style = Style.from_dict({
    # User input(default text)
    '': '',

    'host': '#00aaaa',
    'symbol': '#00ffaa'
})


class SubConsole(BaseConsole):
    is_base_console = False

    def __init__(self):
        print("Init subconsole...")
        super().__init__(message, style)

    def init_commands(self) -> BaseCommands:
        return SubCommands(self)
