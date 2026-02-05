from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from python_tty.executor.executor import CommandExecutor
    from python_tty.executor.models import Invocation, RunState, RunStatus

__all__ = [
    "CommandExecutor",
    "Invocation",
    "RunState",
    "RunStatus",
]


def __getattr__(name):
    if name == "CommandExecutor":
        from python_tty.executor.executor import CommandExecutor
        return CommandExecutor
    if name == "Invocation":
        from python_tty.executor.models import Invocation
        return Invocation
    if name == "RunState":
        from python_tty.executor.models import RunState
        return RunState
    if name == "RunStatus":
        from python_tty.executor.models import RunStatus
        return RunStatus
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

