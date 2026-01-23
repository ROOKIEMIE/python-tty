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
    def __init__(self, service=None, executor=None):
        if executor is None:
            executor = CommandExecutor()
        self.executor = executor
        self.manager = ConsoleManager(service=service, executor=executor, on_shutdown=self.shutdown)
        load_consoles()
        REGISTRY.register_all(self.manager)

    def start(self):
        """Start the console loop with the registered root console."""
        self.manager.run()

    def start_executor(self, loop=None):
        """Start executor workers on the provided asyncio loop."""
        self.executor.start(loop=loop)

    def shutdown_executor(self, wait=True, timeout=None):
        """Shutdown executor workers after RPC/TTY stop."""
        return self.executor.shutdown_threadsafe(wait=wait, timeout=timeout)

    def shutdown(self):
        """Shutdown all resources owned by the factory."""
        self.shutdown_executor()

