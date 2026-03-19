import inspect
from typing import Any, Dict

from python_tty.commands import BaseCommands
from python_tty.commands.registry import CommandInfo
from python_tty.exceptions.console_exception import ConsoleInitException


TESTABLE_ATTR = "__tty_testable__"
TEST_META_ATTR = "__tty_test_meta__"
TEST_SCOPE_ATTR = "__tty_test_scope__"


def tty_testable(target=None, **meta):
    """Mark command classes/methods as discoverable by python_tty.testing."""

    if target is None:
        return lambda real_target: tty_testable(real_target, **meta)

    if inspect.isclass(target):
        if not issubclass(target, BaseCommands):
            raise ConsoleInitException(
                "@tty_testable class target must inherit BaseCommands"
            )
        _mark_testable(target, scope="class", meta=meta)
        return target

    if callable(target):
        func = _unwrap_callable(target)
        if not _is_registered_command_method(func):
            raise ConsoleInitException(
                "@tty_testable method target must be a registered command method "
                "(decorate with @register_command first)"
            )
        _mark_testable(func, scope="method", meta=meta)
        return target

    raise ConsoleInitException(
        "@tty_testable target must be a BaseCommands subclass or registered command method"
    )


def _unwrap_callable(value):
    return getattr(value, "__func__", value)


def _is_registered_command_method(func) -> bool:
    if not callable(func):
        return False
    info = getattr(func, "info", None)
    return isinstance(info, CommandInfo)


def _mark_testable(target, scope: str, meta: Dict[str, Any]):
    existing_meta = _read_meta(target)
    merged_meta = dict(existing_meta)
    merged_meta.update(meta)
    setattr(target, TESTABLE_ATTR, True)
    setattr(target, TEST_META_ATTR, merged_meta)
    setattr(target, TEST_SCOPE_ATTR, scope)


def _read_meta(target):
    meta = getattr(target, TEST_META_ATTR, None)
    if isinstance(meta, dict):
        return meta
    return {}
