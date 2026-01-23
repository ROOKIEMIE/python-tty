import asyncio
import threading

from src.config import Config
from src.consoles.loader import load_consoles
from src.consoles.manager import ConsoleManager
from src.consoles.registry import REGISTRY
from src.executor import CommandExecutor


class ConsoleFactory:
    """Bootstrap console system by loading modules and registering consoles.

    Example:
        # Pass your business core instance here to make it available
        # to all console/commands classes via the manager service.
        factory = ConsoleFactory(object())
        factory.start()

    Notes:
        - To auto-load consoles, update DEFAULT_CONSOLE_MODULES in
          src.consoles.loader with the modules that define your console classes.
        - Or call load_consoles(...) yourself before starting to register
          consoles via their decorators.
    """
    def __init__(self, service=None, config: Config = None):
        if config is None:
            config = Config()
        self.config = config
        self.executor = CommandExecutor(config=config.executor)
        self._executor_loop = None
        self._executor_thread = None
        self.manager = ConsoleManager(
            service=service,
            executor=self.executor,
            on_shutdown=self.shutdown,
            config=config.console_manager,
        )
        load_consoles()
        REGISTRY.register_all(self.manager)

    def start(self):
        """Start the console loop with the registered root console."""
        self._start_executor_if_needed()
        self.manager.run()

    def start_executor(self, loop=None):
        """Start executor workers on the provided asyncio loop."""
        self.executor.start(loop=loop)

    def shutdown_executor(self, wait=True, timeout=None):
        """Shutdown executor workers after RPC/TTY stop."""
        loop = self._executor_loop
        if loop is not None and loop.is_running():
            self.executor.shutdown_threadsafe(wait=wait, timeout=timeout)
            loop.call_soon_threadsafe(loop.stop)
            if self._executor_thread is not None and wait:
                self._executor_thread.join(timeout)
            return None
        return self.executor.shutdown_threadsafe(wait=wait, timeout=timeout)

    def shutdown(self):
        """Shutdown all resources owned by the factory."""
        if self.config.console_factory.shutdown_executor:
            self.shutdown_executor()

    def _start_executor_if_needed(self):
        if not self.config.console_factory.start_executor:
            return
        if self._executor_thread is not None and self._executor_thread.is_alive():
            return
        if self.config.console_factory.executor_in_thread:
            self._start_executor_thread()
        else:
            self.start_executor()

    def _start_executor_thread(self):
        if self._executor_thread is not None and self._executor_thread.is_alive():
            return
        loop = asyncio.new_event_loop()
        self._executor_loop = loop

        def _run_loop():
            asyncio.set_event_loop(loop)
            self.start_executor(loop=loop)
            loop.run_forever()
            pending = asyncio.all_tasks(loop)
            if pending:
                for task in pending:
                    task.cancel()
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            loop.close()

        self._executor_thread = threading.Thread(
            target=_run_loop,
            name=self.config.console_factory.executor_thread_name,
            daemon=True,
        )
        self._executor_thread.start()
