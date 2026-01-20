import logging

from src import proxy_print, UIEventLevel


class ConsoleHandler(logging.Handler):
    def __init__(self):
        super().__init__()

    def emit(self, record):
        try:
            log = self.format(record)
            proxy_print(log, UIEventLevel.DEBUG)
        except Exception:
            self.handleError(record)

