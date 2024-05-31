from src.consoles.root_console import RootConsole


class ConsoleFactory:
    pass


factory = ConsoleFactory()


if __name__ == '__main__':
    root = RootConsole()
    root.start()
