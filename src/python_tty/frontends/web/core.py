import asyncio

from fastapi import FastAPI, Request, Response, WebSocket
from fastapi import WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from python_tty.config import WebConfig
from python_tty.executor.models import RunStatus
from python_tty.meta import export_meta


def create_app(executor=None, config: WebConfig = None):
    config = config or WebConfig()
    app = FastAPI(root_path=config.root_path)
    app.state.ws_connections = 0

    if config.cors_allow_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=config.cors_allow_origins,
            allow_credentials=config.cors_allow_credentials,
            allow_methods=config.cors_allow_methods,
            allow_headers=config.cors_allow_headers,
        )

    if config.meta_enabled:
        @app.get("/meta")
        async def get_meta(request: Request, response: Response):
            meta = export_meta()
            revision = meta.get("revision")
            if revision:
                if request.headers.get("if-none-match") == revision:
                    return Response(status_code=304)
                response.headers["ETag"] = revision
            if config.meta_cache_control_max_age >= 0:
                response.headers["Cache-Control"] = f"max-age={config.meta_cache_control_max_age}"
            return meta

    if config.ws_snapshot_enabled:
        @app.websocket("/meta/snapshot")
        async def meta_snapshot(ws: WebSocket):
            if app.state.ws_connections >= config.ws_max_connections:
                await ws.close(code=1008)
                return
            app.state.ws_connections += 1
            try:
                await ws.accept()
                payload = {"meta": export_meta()}
                if config.ws_snapshot_include_jobs and executor is not None:
                    payload["jobs"] = executor.job_store.list(
                        filters={"status": [RunStatus.PENDING, RunStatus.RUNNING]}
                    )
                await ws.send_json(payload)
                if config.ws_heartbeat_interval > 0:
                    while True:
                        await asyncio.sleep(config.ws_heartbeat_interval)
                        await ws.send_text("ping")
                else:
                    await ws.close()
            except WebSocketDisconnect:
                return
            finally:
                app.state.ws_connections -= 1

    return app
