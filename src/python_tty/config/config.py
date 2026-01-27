from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING, TextIO, Tuple, Type

if TYPE_CHECKING:
    from python_tty.audit.sink import AuditSink
    from src.python_tty.runtime.router import OutputRouter


@dataclass
class AuditConfig:
    enabled: bool = False
    file_path: Optional[str] = None
    stream: Optional[TextIO] = None
    async_mode: bool = False
    flush_interval: float = 1.0
    keep_in_memory: bool = False
    sink: Optional["AuditSink"] = None


@dataclass
class ExecutorConfig:
    workers: int = 1
    retain_last_n: Optional[int] = None
    ttl_seconds: Optional[float] = None
    pop_on_wait: bool = False
    exempt_exceptions: Optional[Tuple[Type[BaseException], ...]] = None
    emit_run_events: bool = False
    audit: AuditConfig = field(default_factory=AuditConfig)


@dataclass
class ConsoleManagerConfig:
    use_patch_stdout: bool = True
    output_router: Optional["OutputRouter"] = None


@dataclass
class ConsoleFactoryConfig:
    start_executor: bool = True
    executor_in_thread: bool = True
    executor_thread_name: str = "ExecutorLoop"
    shutdown_executor: bool = True


@dataclass
class Config:
    console_manager: ConsoleManagerConfig = field(default_factory=ConsoleManagerConfig)
    executor: ExecutorConfig = field(default_factory=ExecutorConfig)
    console_factory: ConsoleFactoryConfig = field(default_factory=ConsoleFactoryConfig)

