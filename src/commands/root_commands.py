from prompt_toolkit.completion import FuzzyCompleter, WordCompleter

from src import proxy_print
from src.commands import BaseCommands, register_command


class RootCommands(BaseCommands):
    def enable_undefined_command(self):
        return True

    @register_command("debug", "Debug root console, display some information", validator=GeneralValidator)
    def run_debug(self, *args):
        framework = self.console.service
        proxy_print(str(framework))


if __name__ == '__main__':
    pass
