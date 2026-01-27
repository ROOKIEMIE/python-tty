import contextvars
import threading
from contextlib import contextmanager
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from python_tty.runtime.router import BaseRouter


class RouterProvider:
    def __init__(self):
        self._default_router: Optional["BaseRouter"] = None
        self._lock = threading.Lock()
        self._current_router = contextvars.ContextVar("python_tty_current_router", default=None)

    def set_default_router(self, router: Optional["BaseRouter"]):
        with self._lock:
            self._default_router = router
        return router

    def get_default_router(self) -> Optional["BaseRouter"]:
        with self._lock:
            return self._default_router

    def get_router(self) -> Optional["BaseRouter"]:
        current = self._current_router.get()
        if current is not None:
            return current
        return self.get_default_router()

    def set_current_router(self, router: Optional["BaseRouter"]):
        return self._current_router.set(router)

    def reset_current_router(self, token):
        self._current_router.reset(token)

    @contextmanager
    def use_router(self, router: Optional["BaseRouter"]):
        token = self._current_router.set(router)
        try:
            yield router
        finally:
            self._current_router.reset(token)


_PROVIDER = RouterProvider()


def set_default_router(router):
    return _PROVIDER.set_default_router(router)


def get_default_router():
    return _PROVIDER.get_default_router()


def get_router():
    return _PROVIDER.get_router()


def use_router(router):
    return _PROVIDER.use_router(router)
