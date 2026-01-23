from abc import ABC, abstractmethod

from prompt_toolkit.completion import Completer, WordCompleter
from prompt_toolkit.document import Document
from prompt_toolkit.validation import ValidationError, Validator

from python_tty.commands.registry import ArgSpec


class GeneralValidator(Validator):
    """Default validator that checks argument count and allows custom validation."""
    def __init__(self, console, func, arg_spec=None):
        self.console = console
        self.func = func
        self.arg_spec = arg_spec or ArgSpec.from_signature(func)
        super().__init__()

    def validate(self, document: Document) -> None:
        try:
            args = self.arg_spec.parse(document.text)
            self.arg_spec.validate_count(len(args))
        except ValidationError:
            raise
        except ValueError as exc:
            raise ValidationError(message=str(exc)) from exc
        try:
            self.custom_validate(args, document.text)
        except TypeError:
            self.custom_validate(document.text)

    def custom_validate(self, args, text: str):
        pass


def _allow_complete_for_spec(arg_spec, text, args):
    if arg_spec.max_args is None:
        return True
    if text != "" and text[-1].isspace():
        return len(args) < arg_spec.max_args
    return len(args) <= arg_spec.max_args


class GeneralCompleter(Completer, ABC):
    """Base completer with ArgSpec-aware completion and console injection."""
    def __init__(self, console, arg_spec=None, ignore_case=True):
        self.console = console
        self.arg_spec = arg_spec or ArgSpec()
        self.ignore_case = ignore_case
        super().__init__()

    @abstractmethod
    def get_candidates(self, args, text: str):
        pass

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        try:
            args = self.arg_spec.parse(text)
        except ValueError:
            return
        if not _allow_complete_for_spec(self.arg_spec, text, args):
            return
        words = self.get_candidates(args, text)
        if not words:
            return
        completer = WordCompleter(words, ignore_case=self.ignore_case)
        yield from completer.get_completions(document, complete_event)

    def _allow_complete(self, text, args):
        return _allow_complete_for_spec(self.arg_spec, text, args)


class PromptToolkitCompleterAdapter(Completer):
    completer_cls = None
    completer_kwargs = {}

    def __init__(self, console, arg_spec=None):
        self.console = console
        self.arg_spec = arg_spec or ArgSpec()
        if self.completer_cls is None:
            raise ValueError("completer_cls must be set for adapter")
        self._inner = self.completer_cls(**self.get_completer_kwargs())
        super().__init__()

    def get_completer_kwargs(self):
        return dict(self.completer_kwargs)

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        try:
            args = self.arg_spec.parse(text)
        except ValueError:
            return
        if not _allow_complete_for_spec(self.arg_spec, text, args):
            return
        yield from self._inner.get_completions(document, complete_event)


def completer_from(completer_cls, **kwargs):
    """Build a completer adapter class for a prompt_toolkit completer."""
    class _Adapter(PromptToolkitCompleterAdapter):
        pass

    _Adapter.completer_cls = completer_cls
    _Adapter.completer_kwargs = kwargs
    return _Adapter

