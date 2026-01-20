import inspect
import uuid
from abc import ABC, abstractmethod

from prompt_toolkit import PromptSession

from src import UIEventLevel, UIEventListener, proxy_print, UIEventSpeaker
from src.exceptions.console_exception import ConsoleExit, ConsoleInitException, SubConsoleExit
from src.utils import get_command_token, get_func_param_strs


class BaseConsole(ABC, UIEventListener):
    forward_console = None

    def __init__(self, console_message, console_style, parent=None, manager=None):
        self.uid = str(uuid.uuid4())
        self.parent = parent
        self.manager = manager if manager is not None else getattr(parent, "manager", None)
        if self.manager is not None:
            self.service = self.manager.service
        else:
            self.service = getattr(parent, "service", None)
        BaseConsole.forward_console = self
        self.commands = self.init_commands()
        self.session = PromptSession(console_message, style=console_style,
                                     completer=self.commands.completer,
                                     validator=self.commands.validator)
        if self.service is not None and not isinstance(self.service, UIEventSpeaker):
            msg = f"The Service core[{self.service.__class__}] doesn't extend the [UIEventSpeaker],"\
                  " which may affect the output of the Service core on the UI!"
            proxy_print(msg, UIEventLevel.WARNING)
        if isinstance(self.service, UIEventSpeaker):
            self.service.add_event_listener(self)

    @abstractmethod
    def init_commands(self):
        pass

    def handler_event(self, event):
        if BaseConsole.forward_console is not None and BaseConsole.forward_console == self:
            proxy_print(event.msg, event.level)

    def run(self, cmd):
        try:
            if len(cmd) <= 0:
                return
            token = get_command_token(cmd)
            cmd_match_status = False
            for command_name, command_func in self.commands.command_funcs.items():
                if token == command_name:
                    cmd_match_status = True
                    sig = inspect.signature(command_func)
                    func_param_count = len(sig.parameters) - 1
                    if func_param_count >= 0:
                        start_index = len(token) + 1
                        param_list = get_func_param_strs(cmd[start_index:], func_param_count)
                        if param_list is None:
                            command_func(self.commands)
                        else:
                            command_func(self.commands, *param_list)
            if not cmd_match_status:
                self.cmd_invoke_miss(cmd)
        except ValueError:
            return

    def execute(self, cmd):
        self.run(cmd)

    def cmd_invoke_miss(self, cmd: str):
        pass

    def clean_console(self):
        if isinstance(self.service, UIEventSpeaker):
            self.service.remove_event_listener(self)
        if BaseConsole.forward_console == self:
            BaseConsole.forward_console = self.parent

    def start(self):
        if self.manager is not None:
            self.manager.run_with(self)
            return
        while True:
            try:
                cmd = self.session.prompt()
                self.execute(cmd)
            except ConsoleExit:
                if self.parent is None:
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


class MainConsole(BaseConsole):
    def __init__(self, console_message, console_style, parent=None, manager=None):
        if parent is not None:
            raise ConsoleInitException("MainConsole parent must be None")
        super().__init__(console_message, console_style, parent=None, manager=manager)


class SubConsole(BaseConsole):
    def __init__(self, console_message, console_style, parent=None, manager=None):
        if parent is None:
            raise ConsoleInitException("SubConsole parent is None")
        super().__init__(console_message, console_style, parent=parent, manager=manager)


from src.consoles.decorators import root, sub, multi  # noqa: E402
from src.consoles.registry import REGISTRY  # noqa: E402

__all__ = [
    "BaseConsole",
    "MainConsole",
    "SubConsole",
    "REGISTRY",
    "root",
    "sub",
    "multi",
]
