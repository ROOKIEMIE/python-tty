import contextvars
from contextlib import contextmanager
from typing import Callable, Optional


_CURRENT_RUN_ID = contextvars.ContextVar("python_tty_current_run_id", default=None)
_CURRENT_SOURCE = contextvars.ContextVar("python_tty_current_source", default=None)
_CURRENT_EMITTER = contextvars.ContextVar("python_tty_current_emitter", default=None)
_CURRENT_CANCEL_FLAG = contextvars.ContextVar("python_tty_current_cancel_flag", default=None)
_CURRENT_SESSION_ID = contextvars.ContextVar("python_tty_current_session_id", default=None)
_CURRENT_PARENT_RUN_ID = contextvars.ContextVar("python_tty_current_parent_run_id", default=None)
_CURRENT_DEPTH = contextvars.ContextVar("python_tty_current_depth", default=None)
_CURRENT_ORIGIN_SOURCE = contextvars.ContextVar("python_tty_current_origin_source", default=None)
_CURRENT_PRINCIPAL = contextvars.ContextVar("python_tty_current_principal", default=None)
_CURRENT_LOCK_KEY = contextvars.ContextVar("python_tty_current_lock_key", default=None)
_CURRENT_COMMAND_ID = contextvars.ContextVar("python_tty_current_command_id", default=None)
_CURRENT_CALLABLE_META = contextvars.ContextVar("python_tty_current_callable_meta", default=None)


def get_current_run_id() -> Optional[str]:
    return _CURRENT_RUN_ID.get()


def get_current_source() -> Optional[str]:
    return _CURRENT_SOURCE.get()


def get_current_emitter() -> Optional[Callable[[object], None]]:
    return _CURRENT_EMITTER.get()


def get_current_cancel_flag():
    return _CURRENT_CANCEL_FLAG.get()


def get_current_session_id():
    return _CURRENT_SESSION_ID.get()


def get_current_parent_run_id():
    return _CURRENT_PARENT_RUN_ID.get()


def get_current_depth():
    return _CURRENT_DEPTH.get()


def get_current_origin_source():
    return _CURRENT_ORIGIN_SOURCE.get()


def get_current_principal():
    return _CURRENT_PRINCIPAL.get()


def get_current_lock_key():
    return _CURRENT_LOCK_KEY.get()


def get_current_command_id():
    return _CURRENT_COMMAND_ID.get()


def get_current_callable_meta():
    return _CURRENT_CALLABLE_META.get()


def is_cancelled() -> bool:
    flag = get_current_cancel_flag()
    return bool(flag.is_set()) if flag is not None else False


@contextmanager
def use_run_context(run_id: Optional[str] = None,
                    source: Optional[str] = None,
                    emitter: Optional[Callable[[object], None]] = None,
                    cancel_flag=None,
                    session_id: Optional[str] = None,
                    parent_run_id: Optional[str] = None,
                    depth: Optional[int] = None,
                    origin_source: Optional[str] = None,
                    principal: Optional[str] = None,
                    lock_key: Optional[str] = None,
                    command_id: Optional[str] = None,
                    callable_meta=None):
    run_token = _CURRENT_RUN_ID.set(run_id)
    source_token = _CURRENT_SOURCE.set(source)
    emitter_token = _CURRENT_EMITTER.set(emitter)
    cancel_token = _CURRENT_CANCEL_FLAG.set(cancel_flag)
    session_token = _CURRENT_SESSION_ID.set(session_id)
    parent_token = _CURRENT_PARENT_RUN_ID.set(parent_run_id)
    depth_token = _CURRENT_DEPTH.set(depth)
    origin_token = _CURRENT_ORIGIN_SOURCE.set(origin_source)
    principal_token = _CURRENT_PRINCIPAL.set(principal)
    lock_token = _CURRENT_LOCK_KEY.set(lock_key)
    command_token = _CURRENT_COMMAND_ID.set(command_id)
    callable_token = _CURRENT_CALLABLE_META.set(callable_meta)
    try:
        yield
    finally:
        _CURRENT_RUN_ID.reset(run_token)
        _CURRENT_SOURCE.reset(source_token)
        _CURRENT_EMITTER.reset(emitter_token)
        _CURRENT_CANCEL_FLAG.reset(cancel_token)
        _CURRENT_SESSION_ID.reset(session_token)
        _CURRENT_PARENT_RUN_ID.reset(parent_token)
        _CURRENT_DEPTH.reset(depth_token)
        _CURRENT_ORIGIN_SOURCE.reset(origin_token)
        _CURRENT_PRINCIPAL.reset(principal_token)
        _CURRENT_LOCK_KEY.reset(lock_token)
        _CURRENT_COMMAND_ID.reset(command_token)
        _CURRENT_CALLABLE_META.reset(callable_token)
