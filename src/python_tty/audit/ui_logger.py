import logging

from python_tty.runtime.events import UIEventLevel
from src.python_tty.runtime.router import proxy_print


class ConsoleHandler(logging.Handler):
    def __init__(self):
        super().__init__()

    def emit(self, record):
        try:
            log = self.format(record)
            proxy_print(log, UIEventLevel.DEBUG, source="tty")
        except Exception:
            self.handleError(record)
