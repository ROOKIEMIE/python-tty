from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from python_tty.config import Config
    from python_tty.console_factory import ConsoleFactory
    from python_tty.runtime.events import (
        EventBase,
        RuntimeEvent,
        RuntimeEventKind,
        UIEvent,
        UIEventLevel,
        UIEventListener,
        UIEventSpeaker,
    )
    from python_tty.runtime.router import proxy_print

__all__ = [
    "UIEvent",
    "UIEventLevel",
    "EventBase",
    "RuntimeEvent",
    "RuntimeEventKind",
    "UIEventListener",
    "UIEventSpeaker",
    "ConsoleFactory",
    "Config",
    "proxy_print",
]


def __getattr__(name):
    if name == "Config":
        from python_tty.config import Config
        return Config
    if name == "ConsoleFactory":
        from python_tty.console_factory import ConsoleFactory
        return ConsoleFactory
    if name == "proxy_print":
        from python_tty.runtime.router import proxy_print
        return proxy_print
    if name in {
        "UIEvent",
        "UIEventLevel",
        "EventBase",
        "RuntimeEvent",
        "RuntimeEventKind",
        "UIEventListener",
        "UIEventSpeaker",
    }:
        from python_tty.runtime.events import (
            EventBase,
            RuntimeEvent,
            RuntimeEventKind,
            UIEvent,
            UIEventLevel,
            UIEventListener,
            UIEventSpeaker,
        )
        mapping = {
            "UIEvent": UIEvent,
            "UIEventLevel": UIEventLevel,
            "EventBase": EventBase,
            "RuntimeEvent": RuntimeEvent,
            "RuntimeEventKind": RuntimeEventKind,
            "UIEventListener": UIEventListener,
            "UIEventSpeaker": UIEventSpeaker,
        }
        return mapping[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
