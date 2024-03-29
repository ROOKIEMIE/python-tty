class ConsoleInitException(Exception):
    """ Console init exception """
    def __init__(self, message: str):
        super().__init__(message)


class ConsoleExit(Exception):
    pass


class SubConsoleExit(Exception):
    pass
