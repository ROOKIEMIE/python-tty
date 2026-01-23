from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from python_tty.ui.output import OutputRouter


@dataclass
class ExecutorConfig:
    workers: int = 1
    retain_last_n: Optional[int] = None
    ttl_seconds: Optional[float] = None
    pop_on_wait: bool = False


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

