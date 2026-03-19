import uuid
from typing import Dict, Iterable, List, Optional

from prompt_toolkit.document import Document

from python_tty.config import ExecutorConfig
from python_tty.executor import CommandExecutor, Invocation
from python_tty.executor.execution import ExecutionBinding, ExecutionContext
from python_tty.runtime.context import use_run_context
from python_tty.runtime.provider import use_router
from python_tty.testing.capture import CollectingRouter, build_output_records, capture_executor_events
from python_tty.testing.discovery import DiscoveredTestCase, DiscoveredTestSuite, discover_tests
from python_tty.testing.results import TestRunResult


class CommandHarness:
    """Lightweight harness for directly invoking a single command method."""

    def __init__(self, service=None, manager=None, suite: Optional[DiscoveredTestSuite] = None, source: str = "test"):
        self._service = service
        self._manager = manager
        self._suite = suite
        self._source = source

    def run(
        self,
        target,
        *,
        command_id: Optional[str] = None,
        argv: Optional[Iterable[str]] = None,
        kwargs: Optional[Dict[str, object]] = None,
        raw_text: Optional[str] = None,
        validate: bool = True,
        service=None,
        manager=None,
        raise_exceptions: bool = False,
        run_id: Optional[str] = None,
    ) -> TestRunResult:
        """Execute one discovered command and return a structured TestRunResult."""

        case = _resolve_case(target, command_id=command_id, suite=self._suite)
        resolved_service = self._service if service is None else service
        resolved_manager = self._manager if manager is None else manager
        resolved_kwargs = dict(kwargs or {})

        console = _build_console_stub(case, resolved_service, resolved_manager)
        commands = case.commands_cls(console)
        console.commands = commands
        command_def = _resolve_command_def(commands, case)

        resolved_argv = _resolve_argv(commands, command_def, argv=argv, raw_text=raw_text)
        invocation = _build_invocation(case, resolved_argv, resolved_kwargs, raw_text, self._source, run_id)

        runtime_events: List[object] = []
        router = CollectingRouter()
        return_value = None
        exception = None
        validator_ran = False

        try:
            with use_router(router):
                with use_run_context(
                    run_id=invocation.run_id,
                    source=invocation.source,
                    emitter=lambda event: runtime_events.append(event),
                    command_id=invocation.command_id,
                ):
                    if validate and command_def.validator is not None:
                        validator_ran = True
                        _run_validator(commands, command_def, raw_text, resolved_argv)
                    return_value = _invoke(commands, command_def, resolved_argv, resolved_kwargs)
        except Exception as exc:  # pragma: no cover - exercised via tests
            exception = exc
            if raise_exceptions:
                raise

        outputs = build_output_records(runtime_events, router.events)
        return TestRunResult(
            ok=exception is None,
            command_id=case.command_id,
            return_value=return_value,
            exception=exception,
            outputs=outputs,
            runtime_events=list(runtime_events),
            validator_ran=validator_ran,
            invocation=invocation,
            run_id=invocation.run_id,
        )


class InvocationHarness:
    """Harness for testing command invocation via ExecutionContext/ExecutionBinding."""

    def __init__(
        self,
        service=None,
        manager=None,
        suite: Optional[DiscoveredTestSuite] = None,
        source: str = "test",
        executor: Optional[CommandExecutor] = None,
    ):
        self._service = service
        self._manager = manager
        self._suite = suite
        self._source = source
        self._executor = executor

    def run(
        self,
        target,
        *,
        command_id: Optional[str] = None,
        argv: Optional[Iterable[str]] = None,
        kwargs: Optional[Dict[str, object]] = None,
        raw_text: Optional[str] = None,
        through_executor: bool = False,
        validate: bool = True,
        service=None,
        manager=None,
        executor: Optional[CommandExecutor] = None,
        raise_exceptions: bool = False,
        run_id: Optional[str] = None,
    ) -> TestRunResult:
        """Run one command through the framework invocation path."""

        case = _resolve_case(target, command_id=command_id, suite=self._suite)
        resolved_service = self._service if service is None else service
        resolved_manager = self._manager if manager is None else manager
        resolved_kwargs = dict(kwargs or {})

        console = _build_console_stub(case, resolved_service, resolved_manager)
        commands = case.commands_cls(console)
        console.commands = commands
        command_def = _resolve_command_def(commands, case)
        resolved_argv = _resolve_argv(commands, command_def, argv=argv, raw_text=raw_text)

        invocation = _build_invocation(case, resolved_argv, resolved_kwargs, raw_text, self._source, run_id)
        ctx = ExecutionContext(
            source=invocation.source,
            console_name=case.console_name,
            command_name=case.command_name,
            command_id=case.command_id,
            argv=list(resolved_argv),
            kwargs=dict(resolved_kwargs),
            raw_cmd=raw_text,
            run_id=invocation.run_id,
        )
        binding = ExecutionBinding(service=resolved_service, manager=resolved_manager, ctx=ctx, console=console)

        runtime_events: List[object] = []
        router = CollectingRouter()
        return_value = None
        exception = None
        validator_ran = False

        try:
            with use_router(router):
                if validate and command_def.validator is not None:
                    validator_ran = True
                    _run_validator(commands, command_def, raw_text, resolved_argv)

                if through_executor:
                    active_executor, owns_executor = _resolve_executor(executor or self._executor)
                    with capture_executor_events(active_executor, runtime_events):
                        run_ref = active_executor.submit_threadsafe(invocation, handler=lambda inv: binding.execute(inv))
                        invocation.run_id = run_ref
                        return_value = active_executor.wait_result_sync(run_ref)
                    if owns_executor:
                        active_executor.shutdown_threadsafe(wait=False)
                else:
                    with use_run_context(
                        run_id=invocation.run_id,
                        source=invocation.source,
                        emitter=lambda event: runtime_events.append(event),
                        command_id=invocation.command_id,
                    ):
                        return_value = binding.execute(invocation)
        except Exception as exc:  # pragma: no cover - exercised via tests
            exception = exc
            if raise_exceptions:
                raise

        outputs = build_output_records(runtime_events, router.events)
        return TestRunResult(
            ok=exception is None,
            command_id=case.command_id,
            return_value=return_value,
            exception=exception,
            outputs=outputs,
            runtime_events=list(runtime_events),
            validator_ran=validator_ran,
            invocation=invocation,
            run_id=invocation.run_id,
        )


def _resolve_case(target, command_id: Optional[str], suite: Optional[DiscoveredTestSuite]) -> DiscoveredTestCase:
    if isinstance(target, DiscoveredTestCase):
        return target

    if isinstance(target, str):
        if suite is None:
            raise ValueError("Command id target requires a discovery suite")
        case = suite.get_case(target)
        if case is None:
            raise ValueError(f"Command id not found in suite: {target}")
        return case

    if suite is not None and command_id is not None:
        case = suite.get_case(command_id)
        if case is not None:
            return case

    command_ids = [command_id] if command_id is not None else None
    discovered = discover_tests(target, command_ids=command_ids)

    if command_id is not None:
        case = discovered.get_case(command_id)
        if case is None:
            raise ValueError(f"Command id not discovered: {command_id}")
        return case

    if len(discovered) != 1:
        raise ValueError(
            "Target resolves to multiple cases; pass command_id or a DiscoveredTestCase"
        )
    return discovered.cases[0]


def _build_console_stub(case: DiscoveredTestCase, service, manager):
    class _ConsoleStub:
        pass

    stub = _ConsoleStub()
    stub.service = service
    stub.manager = manager
    stub.console_name = case.console_name
    return stub


def _resolve_command_def(commands, case: DiscoveredTestCase):
    command_def = commands.get_command_def_by_id(case.command_id)
    if command_def is None:
        command_def = commands.get_command_def(case.command_name)
    if command_def is None:
        raise ValueError(f"Command definition not found for {case.command_id}")
    return command_def


def _resolve_argv(commands, command_def, argv: Optional[Iterable[str]], raw_text: Optional[str]) -> List[str]:
    if argv is not None:
        return [str(value) for value in argv]
    if raw_text is None:
        return []
    return list(commands.deserialize_args(command_def, raw_text))


def _run_validator(commands, command_def, raw_text: Optional[str], argv: List[str]):
    text = raw_text if raw_text is not None else " ".join(argv)
    validator = commands._build_validator(command_def)
    validator.validate(Document(text=text))


def _invoke(commands, command_def, argv: List[str], kwargs: Dict[str, object]):
    if argv or kwargs:
        return command_def.func(commands, *argv, **kwargs)
    return command_def.func(commands)


def _build_invocation(
    case: DiscoveredTestCase,
    argv: List[str],
    kwargs: Dict[str, object],
    raw_text: Optional[str],
    source: str,
    run_id: Optional[str],
):
    resolved_run_id = run_id or str(uuid.uuid4())
    return Invocation(
        run_id=resolved_run_id,
        source=source,
        console_id=case.console_name,
        command_id=case.command_id,
        command_name=case.command_name,
        argv=list(argv),
        kwargs=dict(kwargs),
        raw_cmd=raw_text,
    )


def _resolve_executor(executor: Optional[CommandExecutor]):
    if executor is not None:
        return executor, False
    config = ExecutorConfig(workers=1, sync_in_threadpool=False, emit_run_events=True)
    return CommandExecutor(config=config), True
