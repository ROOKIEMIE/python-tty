import asyncio
import threading

from python_tty.config import Config
from python_tty.consoles.loader import load_consoles
from python_tty.consoles.manager import ConsoleManager
from python_tty.consoles.registry import REGISTRY
from python_tty.executor import CommandExecutor
from python_tty.frontends.rpc.server import start_rpc_server
from python_tty.frontends.web.server import build_web_server
from python_tty.runtime.provider import set_default_router
from python_tty.runtime.router import OutputRouter
from python_tty.runtime.sinks import TTYEventSink
from python_tty.session import SessionManager


class ConsoleFactory:
    """Bootstrap console system by loading modules and registering consoles.

    Example:
        # Pass your business core instance here to make it available
        # to all console/commands classes via the manager service.
        factory = ConsoleFactory(object())
        factory.start()

    Notes:
        - To auto-load consoles, update DEFAULT_CONSOLE_MODULES in
          python_tty.consoles.loader with the modules that define your console classes.
        - Or call load_consoles(...) yourself before starting to register
          consoles via their decorators.
    """
    def __init__(self, service=None, config: Config = None):
        if config is None:
            config = Config()
        self.config = config
        if self.config.console_manager.output_router is None:
            self.config.console_manager.output_router = OutputRouter()
        set_default_router(self.config.console_manager.output_router)
        self.executor = CommandExecutor(config=config.executor)
        self._executor_loop = None
        self._executor_thread = None
        self._tty_sink = None
        self._rpc_server = None
        self._web_server = None
        self.manager = ConsoleManager(
            service=service,
            executor=self.executor,
            on_shutdown=self.shutdown,
            config=config.console_manager,
        )
        self.session_manager = SessionManager(
            executor=self.executor,
            service=service,
            manager=self.manager,
            rpc_config=config.rpc,
        )
        self.manager.session_manager = self.session_manager
        load_consoles()
        REGISTRY.register_all(self.manager)

    def start(self):
        """Start the console loop with the registered root console."""
        run_mode = self.config.console_factory.run_mode
        if run_mode == "tty":
            self._start_executor_if_needed()
            self.manager.run()
            return
        if run_mode == "concurrent":
            self.start_concurrent()
            return
        raise ValueError(f"Unsupported run_mode: {run_mode}")

    def start_concurrent(self):
        """Start executor on the main loop and run TTY in a background thread."""
        loop = asyncio.new_event_loop()
        self._executor_loop = loop
        asyncio.set_event_loop(loop)
        if self.config.console_factory.start_executor:
            self.start_executor(loop=loop)
        self._start_rpc_server(loop)
        self._start_web_server(loop)

        def _run_tty():
            try:
                self.manager.run()
            finally:
                if loop.is_running():
                    loop.call_soon_threadsafe(loop.stop)

        tty_thread = threading.Thread(
            target=_run_tty,
            name=self.config.console_factory.tty_thread_name,
            daemon=True,
        )
        tty_thread.start()
        loop.run_forever()
        pending = asyncio.all_tasks(loop)
        if pending:
            for task in pending:
                task.cancel()
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        if self._rpc_server is not None:
            loop.run_until_complete(self._rpc_server.stop(3.0))
        loop.close()

    def start_executor(self, loop=None):
        """Start executor workers on the provided asyncio loop."""
        self.executor.start(loop=loop)
        active_loop = loop or self._executor_loop or self.executor._loop
        if active_loop is not None:
            self._attach_tty_sink(loop=active_loop)

    def shutdown_executor(self, wait=True, timeout=None):
        """Shutdown executor workers after RPC/TTY stop."""
        loop = self._executor_loop
        if loop is not None and loop.is_running():
            self.executor.shutdown_threadsafe(wait=wait, timeout=timeout)
            loop.call_soon_threadsafe(loop.stop)
            if self._executor_thread is not None and wait:
                self._executor_thread.join(timeout)
            return None
        return self.executor.shutdown_threadsafe(wait=wait, timeout=timeout)

    def shutdown(self):
        """Shutdown all resources owned by the factory."""
        if getattr(self, "session_manager", None) is not None:
            self.session_manager.close()
        if self.config.console_factory.shutdown_executor:
            self.shutdown_executor()
        if self._rpc_server is not None:
            try:
                asyncio.run(self._rpc_server.stop(3.0))
            except RuntimeError:
                pass
        if self._web_server is not None:
            self._web_server.should_exit = True

    def _start_executor_if_needed(self):
        if not self.config.console_factory.start_executor:
            return
        if self._executor_thread is not None and self._executor_thread.is_alive():
            return
        if self.config.console_factory.executor_in_thread:
            self._start_executor_thread()
        else:
            self.start_executor()

    def _start_executor_thread(self):
        if self._executor_thread is not None and self._executor_thread.is_alive():
            return
        loop = asyncio.new_event_loop()
        self._executor_loop = loop

        def _run_loop():
            asyncio.set_event_loop(loop)
            self.start_executor(loop=loop)
            loop.run_forever()
            pending = asyncio.all_tasks(loop)
            if pending:
                for task in pending:
                    task.cancel()
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            loop.close()

        self._executor_thread = threading.Thread(
            target=_run_loop,
            name=self.config.console_factory.executor_thread_name,
            daemon=True,
        )
        self._executor_thread.start()

    def _attach_tty_sink(self, loop):
        if self._tty_sink is not None:
            return
        default_router = self.config.console_manager.output_router
        if default_router is None:
            return
        self._tty_sink = TTYEventSink(self.executor.job_store, default_router)
        self._tty_sink.start(loop)

    def _start_rpc_server(self, loop):
        rpc_config = self.config.rpc
        if rpc_config is None or not rpc_config.enabled:
            return
        async def _start():
            self._rpc_server = await start_rpc_server(
                executor=self.executor,
                config=rpc_config,
                service=self.manager.service,
                manager=self.manager,
            )
        loop.run_until_complete(_start())

    def _start_web_server(self, loop):
        web_config = self.config.web
        if web_config is None or not web_config.enabled:
            return
        self._web_server = build_web_server(executor=self.executor, config=web_config)
        loop.create_task(self._web_server.serve())
