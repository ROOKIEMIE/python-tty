from src.core.events import UIEventLevel, UIEventSpeaker
from src.exceptions.console_exception import ConsoleExit, ConsoleInitException, SubConsoleExit
from src.ui.output import proxy_print


class ConsoleEntry:
    def __init__(self, console_cls, kwargs):
        self.console_cls = console_cls
        self.kwargs = kwargs


class ConsoleManager:
    def __init__(self, service=None):
        self._registry = {}
        self._stack = []
        self._console_tree = None
        self._root_name = None
        self._service = service
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

    def _warn_service_if_needed(self, service):
        if service is not None and not isinstance(service, UIEventSpeaker):
            msg = f"The Service core[{service.__class__}] doesn't extend the [UIEventSpeaker],"\
                  " which may affect the output of the Service core on the UI!"
            proxy_print(msg, UIEventLevel.WARNING)

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
        self._stack.append(console)
        return console

    def pop(self):
        if not self._stack:
            return None
        console = self._stack.pop()
        console.clean_console()
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
        self._stack.append(root_console)
        self._loop()

    def _loop(self):
        while self._stack:
            try:
                cmd = self.current.session.prompt()
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
