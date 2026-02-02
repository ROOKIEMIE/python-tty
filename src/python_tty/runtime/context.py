import contextvars
from contextlib import contextmanager
from typing import Callable, Optional


_CURRENT_RUN_ID = contextvars.ContextVar("python_tty_current_run_id", default=None)
_CURRENT_SOURCE = contextvars.ContextVar("python_tty_current_source", default=None)
_CURRENT_EMITTER = contextvars.ContextVar("python_tty_current_emitter", default=None)


def get_current_run_id() -> Optional[str]:
    return _CURRENT_RUN_ID.get()


def get_current_source() -> Optional[str]:
    return _CURRENT_SOURCE.get()


def get_current_emitter() -> Optional[Callable[[object], None]]:
    return _CURRENT_EMITTER.get()


@contextmanager
def use_run_context(run_id: Optional[str] = None,
                    source: Optional[str] = None,
                    emitter: Optional[Callable[[object], None]] = None):
    run_token = _CURRENT_RUN_ID.set(run_id)
    source_token = _CURRENT_SOURCE.set(source)
    emitter_token = _CURRENT_EMITTER.set(emitter)
    try:
        yield
    finally:
        _CURRENT_RUN_ID.reset(run_token)
        _CURRENT_SOURCE.reset(source_token)
        _CURRENT_EMITTER.reset(emitter_token)
