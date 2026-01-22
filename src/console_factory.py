from src.consoles.loader import load_consoles
from src.consoles.manager import ConsoleManager
from src.consoles.registry import REGISTRY


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
    def __init__(self, service=None):
        self.manager = ConsoleManager(service=service)
        load_consoles()
        REGISTRY.register_all(self.manager)

    def start(self):
        """Start the console loop with the registered root console."""
        self.manager.run()

