from src import UIEventLevel, proxy_print
from src.commands import BaseCommands, GeneralValidator, register_command
from src.commands.mixins import HelpMixin, QuitMixin


class RootCommands(BaseCommands, HelpMixin, QuitMixin):
    @property
    def enable_undefined_command(self):
        return True
    
    @register_command("use", "Enter sub console", validator=GeneralValidator)
    def run_use(self, console_name):
        manager = getattr(self.console, "manager", None)
        if manager is None:
            proxy_print("Console manager not configured", UIEventLevel.WARNING)
            return
        if not manager.is_registered(console_name):
            proxy_print(f"Console [{console_name}] not registered", UIEventLevel.ERROR)
            return
        manager.push(console_name)

    @register_command("debug", "Debug root console, display some information", validator=GeneralValidator)
    def run_debug(self, *args):
        framework = self.console.service
        proxy_print(str(framework))


if __name__ == '__main__':
    pass
