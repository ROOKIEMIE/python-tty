import shlex
import uuid
from abc import ABC, abstractmethod

from prompt_toolkit import PromptSession, print_formatted_text
from prompt_toolkit.application import get_app_session

from demos.file_manager import injector
from demos.file_manager.core.file_manager import Manager

from demos.file_manager.exceptions.console_exception import ConsoleExit, SubConsoleExit


def proxy_print(text=""):
    session = get_app_session()
    return print_formatted_text(text, output=session.output)


@injector(Manager())
class BaseConsole(ABC):
    is_base_console = True

    def __init__(self, console_message, console_style):
        self.uid = str(uuid.uuid4())
        self.commands = self.init_commands()
        self.session = PromptSession(console_message, style=console_style,
                                     completer=self.commands.completer,
                                     validator=self.commands.validator)

    @abstractmethod
    def init_commands(self):
        pass

    def run(self, cmd):
        args_l = shlex.split(cmd)
        if len(args_l) <= 0:
            return
        cmd = args_l[0]
        cmd_invoke_status = False
        for command_name, command_func in self.commands.command_funcs.items():
            if cmd == command_name:
                cmd_invoke_status = True
                if len(args_l) > 1:
                    command_func(self.commands, *args_l[1:])
                else:
                    command_func(self.commands)
        if not cmd_invoke_status:
            self.cmd_invoke_miss(cmd, args_l[1:])

    def execute(self, cmd):
        self.run(cmd)

    def cmd_invoke_miss(self, cmd: str, args):
        pass

    def clean_console(self):
        pass

    def start(self):
        while True:
            try:
                cmd = self.session.prompt()
                self.execute(cmd)
            except ConsoleExit:
                if self.__class__.is_base_console:
                    break
                else:
                    raise ConsoleExit
            except SubConsoleExit:
                break
            except (KeyboardInterrupt, ValueError):
                # FIXME: Careful deal this!
                # continue
                break
        self.clean_console()
