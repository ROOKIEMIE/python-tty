import contextvars
import threading
from contextlib import contextmanager


class RouterProvider:
    def __init__(self):
        self._default_router = None
        self._lock = threading.Lock()
        self._current_router = contextvars.ContextVar("python_tty_current_router", default=None)

    def set_default_router(self, router):
        with self._lock:
            self._default_router = router
        return router

    def get_default_router(self):
        with self._lock:
            return self._default_router

    def get_router(self):
        current = self._current_router.get()
        if current is not None:
            return current
        return self.get_default_router()

    def set_current_router(self, router):
        return self._current_router.set(router)

    def reset_current_router(self, token):
        self._current_router.reset(token)

    @contextmanager
    def use_router(self, router):
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
