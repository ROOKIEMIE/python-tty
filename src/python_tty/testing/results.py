from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class TestRunResult:
    """Structured test execution result for the testing harnesses."""

    ok: bool
    command_id: Optional[str]
    return_value: Any = None
    exception: Optional[BaseException] = None
    outputs: List[Dict[str, Any]] = field(default_factory=list)
    runtime_events: List[object] = field(default_factory=list)
    validator_ran: bool = False
    invocation: Optional[object] = None
    run_id: Optional[str] = None
