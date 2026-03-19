import sys
import unittest
import types
from contextlib import contextmanager
from types import SimpleNamespace


def _install_prompt_toolkit_stub():
    if "prompt_toolkit" in sys.modules:
        return

    root = types.ModuleType("prompt_toolkit")

    class PromptSession:
        def __init__(self, *args, **kwargs):
            self.app = None
            self.output = None

        def prompt(self):
            return ""

    def print_formatted_text(*args, **kwargs):
        return None

    root.PromptSession = PromptSession
    root.print_formatted_text = print_formatted_text

    completion = types.ModuleType("prompt_toolkit.completion")

    class Completer:
        def get_completions(self, document, complete_event):
            return []

    class WordCompleter(Completer):
        def __init__(self, *args, **kwargs):
            super().__init__()

    class NestedCompleter(Completer):
        @classmethod
        def from_nested_dict(cls, mapping):
            return cls()

    completion.Completer = Completer
    completion.WordCompleter = WordCompleter
    completion.NestedCompleter = NestedCompleter

    document = types.ModuleType("prompt_toolkit.document")

    class Document:
        def __init__(self, text=""):
            self.text = text
            self.text_before_cursor = text

    document.Document = Document

    validation = types.ModuleType("prompt_toolkit.validation")

    class ValidationError(Exception):
        pass

    class Validator:
        def validate(self, document):
            return None

    class DummyValidator(Validator):
        pass

    validation.ValidationError = ValidationError
    validation.Validator = Validator
    validation.DummyValidator = DummyValidator

    formatted_text = types.ModuleType("prompt_toolkit.formatted_text")
    formatted_text.FormattedText = list

    styles = types.ModuleType("prompt_toolkit.styles")

    class Style:
        @classmethod
        def from_dict(cls, mapping):
            return mapping

    styles.Style = Style

    patch_stdout_mod = types.ModuleType("prompt_toolkit.patch_stdout")

    @contextmanager
    def patch_stdout():
        yield

    patch_stdout_mod.patch_stdout = patch_stdout

    sys.modules["prompt_toolkit"] = root
    sys.modules["prompt_toolkit.completion"] = completion
    sys.modules["prompt_toolkit.document"] = document
    sys.modules["prompt_toolkit.validation"] = validation
    sys.modules["prompt_toolkit.formatted_text"] = formatted_text
    sys.modules["prompt_toolkit.styles"] = styles
    sys.modules["prompt_toolkit.patch_stdout"] = patch_stdout_mod


_install_prompt_toolkit_stub()

from python_tty.commands import ArgSpec, BaseCommands
from python_tty.commands.decorators import register_command
from python_tty.commands.general import GeneralValidator
from python_tty.consoles.registry import REGISTRY
from python_tty.exceptions.console_exception import ConsoleInitException
from python_tty.runtime.events import RuntimeEventKind
from python_tty.runtime.router import proxy_print
from python_tty.testing import (
    CommandHarness,
    InvocationHarness,
    TestRunResult,
    discover_tests,
    tty_testable,
)


@tty_testable(component="class")
class ClassMarkedCommands(BaseCommands):
    @register_command("alpha", "alpha")
    def run_alpha(self):
        return "alpha"

    @register_command("beta", "beta")
    def run_beta(self):
        return "beta"


class MethodMarkedCommands(BaseCommands):
    @tty_testable(component="method")
    @register_command("only", "only")
    def run_only(self):
        return "only"

    @register_command("hidden", "hidden")
    def run_hidden(self):
        return "hidden"


class ExplicitOnlyCommands(BaseCommands):
    @register_command("service", "service")
    def run_service(self):
        return getattr(self.console.service, "name", None)

    @register_command(
        "needs",
        "needs",
        validator=GeneralValidator,
        arg_spec=ArgSpec(min_args=1, max_args=1),
    )
    def run_needs(self, *args):
        return len(args)

    @register_command(
        "echo",
        "echo",
        validator=GeneralValidator,
        arg_spec=ArgSpec(min_args=1, max_args=1),
    )
    def run_echo(self, *args):
        return ",".join(args)

    @register_command("speak", "speak")
    def run_speak(self, text="hello"):
        proxy_print(f"speak:{text}")
        return f"return:{text}"


class TestingApiMVPTests(unittest.TestCase):
    def test_tty_testable_on_basecommands_subclass(self):
        self.assertTrue(getattr(ClassMarkedCommands, "__tty_testable__", False))
        self.assertEqual(
            getattr(ClassMarkedCommands, "__tty_test_meta__", {}).get("component"),
            "class",
        )

    def test_tty_testable_on_registered_command_method(self):
        self.assertTrue(getattr(MethodMarkedCommands.run_only, "__tty_testable__", False))
        self.assertEqual(
            getattr(MethodMarkedCommands.run_only, "__tty_test_meta__", {}).get("component"),
            "method",
        )

    def test_invalid_tty_testable_usage_raises_clear_error(self):
        with self.assertRaisesRegex(ConsoleInitException, "registered command method"):
            tty_testable(lambda: None)

    def test_explicit_discovery_by_command_id_without_startup_side_effects(self):
        before = len(list(REGISTRY.iter_consoles()))
        command_id = "cmd:explicitonlycommands:needs"
        suite = discover_tests(sys.modules[__name__], command_ids=[command_id])
        after = len(list(REGISTRY.iter_consoles()))

        self.assertIsNotNone(suite.get_case(command_id))
        self.assertEqual(before, after)

    def test_class_level_discovery_collects_all_registered_commands(self):
        suite = discover_tests(ClassMarkedCommands)
        ids = set(suite.ids())
        self.assertEqual(
            ids,
            {
                "cmd:classmarkedcommands:alpha",
                "cmd:classmarkedcommands:beta",
            },
        )

    def test_method_level_discovery_collects_only_marked_command(self):
        suite = discover_tests(sys.modules[__name__])
        method_marked_ids = {
            case.command_id
            for case in suite
            if case.commands_cls is MethodMarkedCommands
        }
        self.assertEqual(method_marked_ids, {"cmd:methodmarkedcommands:only"})

    def test_command_harness_runs_single_command_with_injected_service(self):
        command_id = "cmd:explicitonlycommands:service"
        suite = discover_tests(ExplicitOnlyCommands, command_ids=[command_id])
        case = suite.get_case(command_id)

        harness = CommandHarness(service=SimpleNamespace(name="svc-value"), suite=suite)
        result = harness.run(case)

        self.assertIsInstance(result, TestRunResult)
        self.assertTrue(result.ok)
        self.assertEqual(result.return_value, "svc-value")

    def test_command_harness_validator_can_be_toggled(self):
        command_id = "cmd:explicitonlycommands:needs"
        suite = discover_tests(ExplicitOnlyCommands, command_ids=[command_id])
        case = suite.get_case(command_id)
        harness = CommandHarness(suite=suite)

        with_validator = harness.run(case, validate=True, argv=[])
        without_validator = harness.run(case, validate=False, argv=[])

        self.assertFalse(with_validator.ok)
        self.assertTrue(with_validator.validator_ran)
        self.assertTrue(without_validator.ok)
        self.assertFalse(without_validator.validator_ran)
        self.assertEqual(without_validator.return_value, 0)

    def test_invocation_harness_executes_through_runtime_path(self):
        command_id = "cmd:explicitonlycommands:echo"
        suite = discover_tests(ExplicitOnlyCommands, command_ids=[command_id])
        case = suite.get_case(command_id)

        harness = InvocationHarness(suite=suite)
        result = harness.run(case, through_executor=False, argv=["payload"])

        self.assertTrue(result.ok)
        self.assertEqual(result.return_value, "payload")
        self.assertIsNotNone(result.invocation)

    def test_outputs_and_runtime_events_are_captured_in_test_run_result(self):
        command_id = "cmd:explicitonlycommands:speak"
        suite = discover_tests(ExplicitOnlyCommands, command_ids=[command_id])
        case = suite.get_case(command_id)

        harness = InvocationHarness(suite=suite)
        result = harness.run(case, through_executor=True, argv=["hi"])

        self.assertTrue(result.ok)
        self.assertEqual(result.return_value, "return:hi")
        self.assertIsNotNone(result.run_id)

        event_kinds = [getattr(event, "kind", None) for event in result.runtime_events]
        self.assertIn(RuntimeEventKind.STATE, event_kinds)
        self.assertIn(RuntimeEventKind.STDOUT, event_kinds)

        messages = [output.get("message") for output in result.outputs]
        self.assertIn("speak:hi", messages)


if __name__ == "__main__":
    unittest.main()
