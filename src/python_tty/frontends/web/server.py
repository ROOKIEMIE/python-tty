from typing import Optional

import uvicorn

from python_tty.config import WebConfig
from python_tty.frontends.web.core import create_app


def build_web_app(executor=None, config: Optional[WebConfig] = None):
    config = config or WebConfig()
    return create_app(executor=executor, config=config)


def build_web_server(executor=None, config: Optional[WebConfig] = None) -> uvicorn.Server:
    config = config or WebConfig()
    app = build_web_app(executor=executor, config=config)
    uvicorn_config = uvicorn.Config(
        app,
        host=config.bind_host,
        port=config.port,
        root_path=config.root_path,
        loop="asyncio",
        log_level="info",
    )
    return uvicorn.Server(uvicorn_config)


async def start_web_server(executor=None, config: Optional[WebConfig] = None) -> uvicorn.Server:
    server = build_web_server(executor=executor, config=config)
    await server.serve()
    return server
