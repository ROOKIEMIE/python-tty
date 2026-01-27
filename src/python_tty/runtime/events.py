import enum
import time


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


class RuntimeEventKind(enum.Enum):
    STATE = "state"
    STDOUT = "stdout"
    LOG = "log"


def _normalize_runtime_kind(kind):
    if isinstance(kind, RuntimeEventKind):
        return kind
    if kind is None:
        return None
    try:
        return RuntimeEventKind(kind)
    except ValueError:
        return None


class EventBase:
    """Common event fields shared by RuntimeEvent and UIEvent."""
    def __init__(self, msg, level=UIEventLevel.TEXT, run_id=None, event_type=None,
                 payload=None, source=None, ts=None, seq=None):
        self.msg = msg
        self.level = level
        self.run_id = run_id
        self.event_type = event_type
        self.payload = payload
        self.source = source
        self.ts = time.time() if ts is None else ts
        self.seq = seq


class UIEvent(EventBase):
    """UI event payload for rendering.

    Fields:
        msg: Display text or structured data for the event.
        level: UIEventLevel (or int) that drives rendering style.
        run_id: Run identifier when the event is tied to a command invocation.
        event_type: A short event type label (e.g., "start", "success").
        payload: Structured payload for downstream consumers.
        source: Event origin (framework should pass "tty"/"rpc" explicitly;
            external callers via proxy_print default to "custom").
        ts: Unix timestamp (seconds) when the event was created.
        seq: Per-run sequence number when emitted by the executor.
    """
    def __init__(self, msg, level=UIEventLevel.TEXT, run_id=None, event_type=None,
                 payload=None, source=None, ts=None, seq=None):
        super().__init__(
            msg=msg,
            level=level,
            run_id=run_id,
            event_type=event_type,
            payload=payload,
            source=source,
            ts=ts,
            seq=seq,
        )


class RuntimeEvent(EventBase):
    """Runtime event payload for executor/audit pipelines.

    Fields:
        kind: RuntimeEventKind (state/stdout/log).
        msg: Text or payload for stdout/log events.
        level: UIEventLevel or int for log/stdout severity.
        run_id: Run identifier for correlation.
        event_type: State label for state events (e.g., "start", "success").
        payload: Structured payload for downstream consumers.
        source: Event origin (framework should pass "tty"/"rpc").
        ts: Unix timestamp (seconds) when the event was created.
        seq: Per-run sequence number assigned by the executor.
    """
    def __init__(self, kind, msg=None, level=UIEventLevel.TEXT, run_id=None, event_type=None,
                 payload=None, source=None, ts=None, seq=None):
        self.kind = _normalize_runtime_kind(kind)
        super().__init__(
            msg=msg,
            level=level,
            run_id=run_id,
            event_type=event_type,
            payload=payload,
            source=source,
            ts=ts,
            seq=seq,
        )

    def to_ui_event(self):
        return UIEvent(
            msg=self.msg,
            level=self.level,
            run_id=self.run_id,
            event_type=self.event_type,
            payload=self.payload,
            source=self.source,
            ts=self.ts,
            seq=self.seq,
        )


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
