import logging

from src.core.events import UIEventLevel
from src.ui.output import proxy_print


class ConsoleHandler(logging.Handler):
    def __init__(self):
        super().__init__()

    def emit(self, record):
        try:
            log = self.format(record)
            proxy_print(log, UIEventLevel.DEBUG)
        except Exception:
            self.handleError(record)

