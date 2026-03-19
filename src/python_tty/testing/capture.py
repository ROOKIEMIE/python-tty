from contextlib import contextmanager
from typing import Dict, Iterable, List, Optional

from python_tty.runtime.events import RuntimeEvent, UIEvent
from python_tty.runtime.router import BaseRouter


class CollectingRouter(BaseRouter):
    """In-memory router used by test harnesses to capture UI events."""

    def __init__(self):
        self.events: List[object] = []

    def emit(self, event):
        self.events.append(event)


@contextmanager
def capture_executor_events(executor, sink: List[object]):
    """Temporarily intercept executor.publish_event and append events to sink."""

    original = executor.publish_event

    def _publish(run_id, event):
        sink.append(event)
        return original(run_id, event)

    executor.publish_event = _publish
    try:
        yield sink
    finally:
        executor.publish_event = original


def build_output_records(runtime_events: Iterable[object], ui_events: Optional[Iterable[object]] = None):
    """Normalize runtime/UI events into a lightweight output record list."""

    outputs: List[Dict[str, object]] = []
    for event in runtime_events:
        outputs.append(_event_to_record(event, channel="runtime"))
    for event in ui_events or []:
        outputs.append(_event_to_record(event, channel="ui"))
    return outputs


def _event_to_record(event: object, channel: str):
    if isinstance(event, RuntimeEvent):
        kind = getattr(event.kind, "value", event.kind)
    else:
        kind = None
    if isinstance(event, (RuntimeEvent, UIEvent)):
        level = getattr(getattr(event, "level", None), "value", getattr(event, "level", None))
        return {
            "channel": channel,
            "kind": kind,
            "message": getattr(event, "msg", None),
            "level": level,
            "source": getattr(event, "source", None),
            "event_type": getattr(event, "event_type", None),
            "run_id": getattr(event, "run_id", None),
            "seq": getattr(event, "seq", None),
        }
    return {
        "channel": channel,
        "kind": kind,
        "message": str(event),
        "level": None,
        "source": None,
        "event_type": None,
        "run_id": None,
        "seq": None,
    }
