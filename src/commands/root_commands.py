from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.document import Document

from src.commands import BaseCommands, register_command, GeneralValidator
from src.consoles.sub import SubConsole


class RootCommands(BaseCommands):
    def enable_undefined_command(self):
        return True

    class SearchValidator(GeneralValidator):
        def __init__(self, console, func):
            super().__init__(console, func)

        def validate(self, document: Document) -> None:
            pass

    class SearchCompleter(WordCompleter):
        def __init__(self, console):
            self.console = console
            super().__init__([])

    @register_command("search", "Search loaded module", [], completer=SearchCompleter, validator=SearchValidator)
    def run_search(self, *args, **kwargs):
        pass

    class UseValidator(GeneralValidator):
        def __init__(self, console, func):
            super().__init__(console, func)

        def validate(self, document: Document) -> None:
            pass

    class UseCompleter(WordCompleter):
        def __init__(self, console):
            self.console = console
            super().__init__(["sub1", "sub2", "sub3"])

    @register_command("use", "Active a module", [], completer=UseCompleter, validator=UseValidator)
    def run_use(self, console_name):
        if console_name == "sub1":
            SubConsole().start()


if __name__ == '__main__':
    pass
