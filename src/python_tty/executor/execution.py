from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from python_tty.commands.mixins import DefaultCommands
from python_tty.commands.registry import COMMAND_REGISTRY
from python_tty.consoles.registry import REGISTRY
from python_tty.executor.models import Invocation


@dataclass
class ExecutionContext:
    source: str
    principal: Optional[str] = None
    console_name: Optional[str] = None
    command_name: Optional[str] = None
    command_id: Optional[str] = None
    argv: List[str] = field(default_factory=list)
    kwargs: Dict[str, Any] = field(default_factory=dict)
    raw_cmd: Optional[str] = None
    run_id: Optional[str] = None
    session_id: Optional[str] = None
    timeout_ms: Optional[int] = None
    lock_key: str = "global"
    audit_policy: Optional[str] = None
    meta_revision: Optional[str] = None

    def to_invocation(self) -> Invocation:
        command_id = self.command_id
        if command_id is None and self.console_name and self.command_name:
            command_id = _build_command_id(self.console_name, self.command_name)
        return Invocation(
            run_id=self.run_id,
            source=self.source,
            principal=self.principal,
            console_id=self.console_name,
            command_id=command_id,
            command_name=self.command_name,
            argv=list(self.argv),
            kwargs=dict(self.kwargs),
            lock_key=self.lock_key,
            timeout_ms=self.timeout_ms,
            audit_policy=self.audit_policy,
            session_id=self.session_id,
            meta_revision=self.meta_revision,
            raw_cmd=self.raw_cmd,
        )


class ExecutionBinding:
    def __init__(self, service=None, manager=None, ctx: Optional[ExecutionContext] = None, console=None):
        self.service = service
        self.manager = manager
        self.ctx = ctx
        self._console = console
        self._commands = None

    def execute(self, invocation: Invocation):
        commands = self._get_commands(invocation)
        command_def = commands.get_command_def_by_id(invocation.command_id)
        if command_def is None and invocation.command_name is not None:
            command_def = commands.get_command_def(invocation.command_name)
        if command_def is None:
            raise ValueError(f"Command not found: {invocation.command_id}")
        if not invocation.argv:
            return command_def.func(commands)
        return command_def.func(commands, *invocation.argv)

    def _get_commands(self, invocation: Invocation):
        if self._commands is not None:
            return self._commands
        if self._console is not None and getattr(self._console, "commands", None) is not None:
            self._commands = self._console.commands
            return self._commands
        console_name = _resolve_console_name(self.ctx, invocation)
        console_cls = _resolve_console_cls(console_name)
        if console_cls is None:
            raise ValueError(f"Console not found: {console_name}")
        console_stub = console_cls.__new__(console_cls)
        console_stub.manager = self.manager
        console_stub.service = self.service
        console_stub.console_name = console_name
        commands_cls = COMMAND_REGISTRY.get_commands_cls(console_cls)
        if commands_cls is None:
            commands_cls = DefaultCommands
        self._commands = commands_cls(console_stub)
        return self._commands


def _resolve_console_name(ctx: Optional[ExecutionContext], invocation: Invocation) -> Optional[str]:
    if ctx is not None and ctx.console_name:
        return ctx.console_name
    return invocation.console_id


def _resolve_console_cls(console_name: Optional[str]):
    if console_name is None:
        return None
    for name, console_cls, _ in REGISTRY.iter_consoles():
        if name == console_name:
            return console_cls
    return None


def _build_command_id(console_name: str, command_name: str):
    return f"cmd:{console_name}:{command_name}"
