from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING, TextIO, Tuple, Type

if TYPE_CHECKING:
    from python_tty.audit.sink import AuditSink
    from python_tty.runtime.router import OutputRouter


@dataclass
class AuditConfig:
    """Audit sink configuration.

    Attributes:
        enabled: Toggle audit recording.
        file_path: File path to append JSONL audit records.
        stream: File-like stream to write audit records.
        async_mode: Enable async background writer when stream is set.
        flush_interval: Flush interval (seconds) for async writer.
        keep_in_memory: Keep records in memory buffer for testing.
        sink: Custom AuditSink instance to use instead of file/stream.
    """
    enabled: bool = False
    file_path: Optional[str] = None
    stream: Optional[TextIO] = None
    async_mode: bool = False
    flush_interval: float = 1.0
    keep_in_memory: bool = False
    sink: Optional["AuditSink"] = None


@dataclass
class ExecutorConfig:
    """Executor runtime configuration.

    Attributes:
        workers: Number of worker tasks to consume invocations.
        retain_last_n: Keep only the last N completed runs in memory.
        ttl_seconds: Time-to-live for completed runs.
        pop_on_wait: Drop run state after wait_result completion.
        exempt_exceptions: Exceptions treated as cancellations.
        emit_run_events: Emit start/success/failure RuntimeEvent state.
        audit: Audit sink configuration.
    """
    workers: int = 1
    retain_last_n: Optional[int] = None
    ttl_seconds: Optional[float] = None
    pop_on_wait: bool = False
    exempt_exceptions: Optional[Tuple[Type[BaseException], ...]] = None
    emit_run_events: bool = False
    audit: AuditConfig = field(default_factory=AuditConfig)


@dataclass
class ConsoleManagerConfig:
    """Console manager configuration.

    Attributes:
        use_patch_stdout: Patch stdout for prompt_toolkit rendering.
        output_router: Output router instance for UI events.
    """
    use_patch_stdout: bool = True
    output_router: Optional["OutputRouter"] = None


@dataclass
class ConsoleFactoryConfig:
    """Console factory bootstrap configuration.

    Attributes:
        run_mode: "tty" for single-thread TTY mode, "concurrent" for
            main-thread asyncio loop with TTY in a background thread.
        start_executor: Auto-start the executor when the factory starts.
        executor_in_thread: Start executor in a background thread (tty mode).
        executor_thread_name: Thread name for the executor loop thread.
        tty_thread_name: Thread name for the TTY loop (concurrent mode).
        shutdown_executor: Shutdown executor when the factory stops.
    """
    run_mode: str = "tty"
    start_executor: bool = True
    executor_in_thread: bool = True
    executor_thread_name: str = "ExecutorLoop"
    tty_thread_name: str = "TTYLoop"
    shutdown_executor: bool = True


@dataclass
class Config:
    """Top-level configuration for python-tty."""
    console_manager: ConsoleManagerConfig = field(default_factory=ConsoleManagerConfig)
    executor: ExecutorConfig = field(default_factory=ExecutorConfig)
    console_factory: ConsoleFactoryConfig = field(default_factory=ConsoleFactoryConfig)

