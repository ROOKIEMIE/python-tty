import threading

from prompt_toolkit import print_formatted_text
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.styles import Style

from src.ui.events import UIEvent, UIEventLevel


MSG_LEVEL_SYMBOL = {
    0: "[*] ",
    1: "[!] ",
    2: "[x] ",
    3: "[+] ",
    4: "[-] ",
    5: "[@] "
}

MSG_LEVEL_SYMBOL_STYLE = {
    0: "fg:green",
    1: "fg:yellow",
    2: "fg:red",
    3: "fg:blue",
    4: "fg:white",
    5: "fg:pink"
}


class OutputRouter:
    def __init__(self):
        self._lock = threading.Lock()
        self._app = None
        self._output = None

    def bind_session(self, session):
        if session is None:
            return
        with self._lock:
            self._app = getattr(session, "app", None)
            self._output = getattr(session, "output", None)

    def clear_session(self, session=None):
        with self._lock:
            if session is None or getattr(session, "app", None) == self._app:
                self._app = None
                self._output = None

    def emit(self, event: UIEvent):
        with self._lock:
            app = self._app
            output = self._output

        def _render():
            text, style = _format_event(event)
            if output is not None:
                print_formatted_text(text, style=style, output=output)
            else:
                print_formatted_text(text, style=style)

        if app is not None and getattr(app, "is_running", False):
            if hasattr(app, "call_from_executor") and hasattr(app, "run_in_terminal"):
                app.call_from_executor(lambda: app.run_in_terminal(_render))
                return
        _render()


def _normalize_level(level):
    if isinstance(level, UIEventLevel):
        return level
    if level is None:
        return UIEventLevel.TEXT
    if level == UIEventLevel.TEXT.value:
        return UIEventLevel.TEXT
    mapped = UIEventLevel.map_level(level)
    return UIEventLevel.TEXT if mapped is None else mapped


def _format_event(event: UIEvent):
    level = _normalize_level(event.level)
    if level == UIEventLevel.TEXT:
        return event.msg, None
    formatted_text = FormattedText([
        ("class:level", MSG_LEVEL_SYMBOL[level.value]),
        ("class:text", str(event.msg)),
    ])
    style = Style.from_dict({
        "level": MSG_LEVEL_SYMBOL_STYLE[level.value]
    })
    return formatted_text, style


_OUTPUT_ROUTER = OutputRouter()


def get_output_router() -> OutputRouter:
    return _OUTPUT_ROUTER


def proxy_print(text="", text_type=UIEventLevel.TEXT):
    event = UIEvent(msg=text, level=_normalize_level(text_type))
    get_output_router().emit(event)
