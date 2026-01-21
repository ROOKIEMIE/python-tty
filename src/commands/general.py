from prompt_toolkit.document import Document
from prompt_toolkit.validation import ValidationError, Validator

from src.commands.registry import ArgSpec


class GeneralValidator(Validator):
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

