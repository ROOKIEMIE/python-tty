from src.consoles.loader import load_consoles
from src.consoles.manager import ConsoleManager
from src.consoles.registry import REGISTRY


class ConsoleFactory:
    """Bootstrap console system by loading modules and registering consoles."""
    def __init__(self, service=None):
        self.manager = ConsoleManager(service=service)
        load_consoles()
        REGISTRY.register_all(self.manager)

    def start(self):
        """Start the console loop with the registered root console."""
        self.manager.run()


factory = ConsoleFactory()


if __name__ == '__main__':
    factory.start()
