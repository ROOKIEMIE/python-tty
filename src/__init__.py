import enum

from prompt_toolkit import print_formatted_text
from prompt_toolkit.application import get_app_session
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.styles import Style


class UIEventLevel(enum.Enum):
    TEXT = -1
    INFO = 0
    WARNING = 1
    ERROR = 2
    SUCCESS = 3
    FAILURE = 4
    DEBUG = 5

    @staticmethod
    def map_level(code):
        if code == 0:
            return UIEventLevel.INFO
        elif code == 1:
            return UIEventLevel.WARNING
        elif code == 2:
            return UIEventLevel.ERROR
        elif code == 3:
            return UIEventLevel.SUCCESS
        elif code == 4:
            return UIEventLevel.FAILURE
        elif code == 5:
            return UIEventLevel.DEBUG


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


def proxy_print(text="", text_type=UIEventLevel.TEXT):
    session = get_app_session()
    if text_type == UIEventLevel.TEXT:
        print_formatted_text(text, output=session.output)
        return
    formatted_text = FormattedText([
        ('class:level', MSG_LEVEL_SYMBOL[text_type.value]),
        ('class:text', text)
    ])
    style = Style.from_dict({
        'level': MSG_LEVEL_SYMBOL_STYLE[text_type.value]
    })
    print_formatted_text(formatted_text, style=style, output=session.output)


class UIEvent:
    def __init__(self, msg, level=UIEventLevel.TEXT):
        self.msg = msg
        self.level = level


class UIEventListener:
    def handler_event(self, event: UIEvent):
        pass


class UIEventSpeaker:
    def __init__(self):
        self._event_listener = []

    def add_event_listener(self, listener: UIEventListener):
        self._event_listener.append(listener)

    def remove_event_listener(self, listener: UIEventListener):
        self._event_listener.remove(listener)

    def notify_event_listeners(self, event: UIEvent):
        for listener in self._event_listener:
            listener.handler_event(event)


def injector(service):
    def class_decorator(cls):
        original_init = cls.__init__

        def modified_init(self, *args, **kwargs):
            self.service = service
            original_init(self, *args, **kwargs)
            if not isinstance(service, UIEventSpeaker):
                msg = f"The Service core[{service.__class__}] doesn't extend the [UIEventSpeaker],"\
                      " which may affect the output of the Service core on the UI!"
                proxy_print(msg, UIEventLevel.WARNING)
        cls.__init__ = modified_init
        return cls
    return class_decorator
