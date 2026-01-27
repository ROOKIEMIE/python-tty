from prompt_toolkit.patch_stdout import patch_stdout

from python_tty.config import ConsoleManagerConfig
from python_tty.exceptions.console_exception import ConsoleExit, ConsoleInitException, SubConsoleExit
from python_tty.runtime.events import UIEventLevel, UIEventSpeaker
from src.python_tty.runtime.router import get_output_router, proxy_print


class ConsoleEntry:
    def __init__(self, console_cls, kwargs):
        self.console_cls = console_cls
        self.kwargs = kwargs


class ConsoleManager:
    def __init__(self, service=None, executor=None, on_shutdown=None, config: ConsoleManagerConfig = None):
        self._registry = {}
        self._stack = []
        self._console_tree = None
        self._root_name = None
        self._service = service
        self._executor = executor
        self._on_shutdown = on_shutdown
        self._shutdown_called = False
        self._config = config if config is not None else ConsoleManagerConfig()
        self._output_router = self._config.output_router or get_output_router()
        self._use_patch_stdout = self._config.use_patch_stdout
        self._warn_service_if_needed(service)

    def register(self, name, console_cls, **kwargs):
        self._registry[name] = ConsoleEntry(console_cls, kwargs)

    def is_registered(self, name):
        return name in self._registry

    def set_root_name(self, root_name):
        self._root_name = root_name

    def set_console_tree(self, console_tree):
        self._console_tree = console_tree

    @property
    def console_tree(self):
        return self._console_tree

    @property
    def service(self):
        return self._service

    @property
    def executor(self):
        return self._executor

    def clean(self):
        if self._shutdown_called:
            return
        self._shutdown_called = True
        if self._output_router is not None:
            self._output_router.clear_session()
        if callable(self._on_shutdown):
            self._on_shutdown()

    def _warn_service_if_needed(self, service):
        if service is not None and not isinstance(service, UIEventSpeaker):
            msg = f"The Service core[{service.__class__}] doesn't extend the [UIEventSpeaker],"\
                  " which may affect the output of the Service core on the UI!"
            proxy_print(msg, UIEventLevel.WARNING, source="tty")

    @property
    def current(self):
        return self._stack[-1] if self._stack else None

    def push(self, name, **kwargs):
        if name not in self._registry:
            raise KeyError(f"Console [{name}] not registered")
        entry = self._registry[name]
        init_kwargs = dict(entry.kwargs)
        init_kwargs.update(kwargs)
        parent = self.current
        console = entry.console_cls(parent=parent, manager=self, **init_kwargs)
        console.console_name = name
        self._stack.append(console)
        self._bind_output_router()
        return console

    def pop(self):
        if not self._stack:
            return None
        console = self._stack.pop()
        console.clean_console()
        self._bind_output_router()
        return self.current

    def run(self, root_name=None, **kwargs):
        if root_name is None:
            root_name = self._root_name
        if root_name is None:
            raise ConsoleInitException("Root console not registered")
        self.push(root_name, **kwargs)
        self._loop()

    def run_with(self, root_console):
        if root_console.parent is not None:
            raise ConsoleInitException("Root console parent must be None")
        root_console.manager = self
        if getattr(root_console, "console_name", None) is None:
            root_console.console_name = root_console.__class__.__name__.lower()
        self._stack.append(root_console)
        self._bind_output_router()
        self._loop()

    def _loop(self):
        try:
            while self._stack:
                try:
                    self._bind_output_router()
                    cmd = self._prompt()
                    self.current.execute(cmd)
                except SubConsoleExit:
                    self.pop()
                except ConsoleExit:
                    while self._stack:
                        self.pop()
                    break
                except (KeyboardInterrupt, ValueError):
                    while self._stack:
                        self.pop()
                    break
        finally:
            self.clean()

    def _prompt(self):
        if self._use_patch_stdout:
            with patch_stdout():
                return self.current.session.prompt()
        return self.current.session.prompt()

    def _bind_output_router(self):
        if self._output_router is None:
            return
        current = self.current
        if current is None:
            self._output_router.clear_session()
            return
        self._output_router.bind_session(current.session)

