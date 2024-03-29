import inspect
import shlex

from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.document import Document
from prompt_toolkit.validation import ValidationError

from demos.file_manager.commands import BaseCommands, register_command, GeneralValidator
from demos.file_manager.consoles import proxy_print


class RootCommands(BaseCommands):
    # def enable_undefined_command(self):
    #     return True

    class EnvValidator(GeneralValidator):
        def __init__(self, console, func):
            super().__init__(console, func)

        def validate(self, document: Document) -> None:
            sig = inspect.signature(self.func)
            name_list = []
            for name, param in sig.parameters.items():
                name_list.append(name)
            name_list = name_list[1:]
            args = shlex.split(document.text)
            if len(args) <= 0:
                raise ValidationError(message="At least one parameter is missing")
            elif len(args) > len(name_list):
                raise ValidationError(message="Too many parameter to get")

    class EnvCompleter(WordCompleter):
        def __init__(self, console):
            super().__init__(console.service.env_keys)

    @register_command("env", "Display env information", [], completer=EnvCompleter, validator=EnvValidator)
    def run_env(self, env_key):
        proxy_print()
        table = ""
        if env_key == "disk":
            table = self.console.service.display_disks()
        elif env_key == "os":
            table = self.console.service.display_os()
        elif env_key == "network":
            table = self.console.service.display_network()
        proxy_print(table)
        proxy_print()


if __name__ == '__main__':
    pass
