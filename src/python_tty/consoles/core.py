import uuid
from abc import ABC

from prompt_toolkit import PromptSession

from python_tty.runtime.events import UIEventListener, UIEventSpeaker
from python_tty.executor import Invocation
from python_tty.exceptions.console_exception import ConsoleExit, ConsoleInitException, SubConsoleExit
from src.python_tty.runtime.router import proxy_print
from python_tty.utils import split_cmd


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
        self.commands = self._build_commands()
        self.session = PromptSession(console_message, style=console_style,
                                     completer=self.commands.completer,
                                     validator=self.commands.validator)
        if isinstance(self.service, UIEventSpeaker):
            self.service.add_event_listener(self)

    def init_commands(self):
        return None

    def _build_commands(self):
        from python_tty.commands import COMMAND_REGISTRY
        commands_cls = getattr(self.__class__, "__commands_cls__", None)
        if commands_cls is None:
            commands = self.init_commands()
            if commands is not None:
                return commands
            commands_cls = COMMAND_REGISTRY.get_commands_cls(self.__class__)
        if commands_cls is None:
            from python_tty.commands.mixins import DefaultCommands
            commands_cls = DefaultCommands
        return commands_cls(self)

    def handler_event(self, event):
        if BaseConsole.forward_console is not None and BaseConsole.forward_console == self:
            proxy_print(event.msg, event.level, source=event.source or "tty")

    def run(self, invocation: Invocation):
        command_def = self.commands.get_command_def_by_id(invocation.command_id)
        if command_def is None and invocation.command_name is not None:
            command_def = self.commands.get_command_def(invocation.command_name)
        if command_def is None:
            raise ValueError(f"Command not found: {invocation.command_id}")
        if len(invocation.argv) == 0:
            return command_def.func(self.commands)
        return command_def.func(self.commands, *invocation.argv)

    def execute(self, cmd):
        try:
            invocation, token = self._build_invocation(cmd)
            if invocation is None:
                if token != "":
                    self.cmd_invoke_miss(cmd)
                return
            executor = getattr(self.manager, "executor", None) if self.manager is not None else None
            if executor is None:
                self.run(invocation)
                return
            run_id = executor.submit_threadsafe(invocation, handler=self.run)
            executor.wait_result_sync(run_id)
        except ValueError:
            return

    def _build_invocation(self, cmd):
        token, arg_text, _ = split_cmd(cmd)
        if token == "":
            return None, token
        command_def = self.commands.get_command_def(token)
        if command_def is None:
            return None, token
        param_list = self.commands.deserialize_args(command_def, arg_text)
        command_id = self.commands.get_command_id(token)
        invocation = Invocation(
            run_id=str(uuid.uuid4()),
            source="tty",
            console_id=self.uid,
            command_id=command_id,
            command_name=token,
            argv=param_list,
            raw_cmd=cmd,
        )
        return invocation, token

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

