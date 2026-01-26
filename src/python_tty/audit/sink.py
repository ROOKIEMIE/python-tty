import json
import queue
import threading
import time
from dataclasses import asdict, is_dataclass
from enum import Enum
from typing import Any, Iterable, Optional, TextIO


class AuditSink:
    def __init__(self, file_path: Optional[str] = None, stream: Optional[TextIO] = None,
                 keep_in_memory: bool = False, async_mode: bool = False,
                 flush_interval: float = 1.0):
        if file_path is not None and stream is not None:
            raise ValueError("Only one of file_path or stream can be set")
        self._path = file_path
        self._stream = stream
        self._owns_stream = False
        if self._stream is None and self._path is not None:
            self._stream = open(self._path, "a", encoding="utf-8")
            self._owns_stream = True
        self._buffer = [] if keep_in_memory else None
        self._async_mode = async_mode and self._stream is not None
        self._flush_interval = max(0.1, float(flush_interval))
        self._lock = threading.Lock()
        self._queue = None
        self._stop_event = threading.Event()
        self._worker = None
        if self._async_mode:
            self._queue = queue.Queue()
            self._worker = threading.Thread(
                target=self._worker_loop,
                name="AuditSinkWriter",
                daemon=True,
            )
            self._worker.start()

    @property
    def buffer(self):
        return self._buffer

    def record_invocation(self, invocation):
        self._write("invocation", invocation)

    def record_run_state(self, run_state):
        self._write("run_state", run_state)

    def record_event(self, event):
        self._write("event", event)

    def record_bundle(self, invocation=None, run_state=None, events: Optional[Iterable[Any]] = None):
        if invocation is not None:
            self.record_invocation(invocation)
        if run_state is not None:
            self.record_run_state(run_state)
        if events:
            for event in events:
                self.record_event(event)

    def close(self):
        if self._async_mode and self._worker is not None:
            self._stop_event.set()
            self._worker.join()
        if self._owns_stream and self._stream is not None:
            self._stream.close()
        self._stream = None
        self._owns_stream = False

    def _write(self, record_type: str, data):
        record = {
            "type": record_type,
            "ts": time.time(),
            "data": self._materialize(data),
        }
        if self._buffer is not None:
            self._buffer.append(record)
        if self._stream is None:
            return
        if self._async_mode and self._queue is not None:
            self._queue.put(record)
            return
        self._write_record(record)

    def _write_record(self, record):
        payload = json.dumps(record, default=self._json_default)
        with self._lock:
            if self._stream is None:
                return
            self._stream.write(payload + "\n")
            self._stream.flush()

    def _write_batch(self, records):
        payload = "\n".join(json.dumps(record, default=self._json_default) for record in records) + "\n"
        with self._lock:
            if self._stream is None:
                return
            self._stream.write(payload)
            self._stream.flush()

    def _worker_loop(self):
        pending = []
        while not self._stop_event.is_set() or (self._queue is not None and not self._queue.empty()):
            try:
                record = self._queue.get(timeout=self._flush_interval)
                pending.append(record)
                while True:
                    try:
                        pending.append(self._queue.get_nowait())
                    except queue.Empty:
                        break
            except queue.Empty:
                pass
            if pending:
                self._write_batch(pending)
                pending.clear()

    @staticmethod
    def _materialize(value):
        if is_dataclass(value):
            return asdict(value)
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, BaseException):
            return str(value)
        if hasattr(value, "__dict__"):
            return dict(value.__dict__)
        return value

    @staticmethod
    def _json_default(value):
        if is_dataclass(value):
            return asdict(value)
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, BaseException):
            return str(value)
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        if hasattr(value, "__dict__"):
            return dict(value.__dict__)
        return str(value)
