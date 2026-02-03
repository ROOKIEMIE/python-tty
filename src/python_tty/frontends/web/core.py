from fastapi import FastAPI, Request, Response, WebSocket

from python_tty.executor.models import RunStatus
from python_tty.meta import export_meta


def create_app(executor=None, include_job_summary: bool = False):
    app = FastAPI()

    @app.get("/meta")
    async def get_meta(request: Request, response: Response):
        meta = export_meta()
        revision = meta.get("revision")
        if revision:
            if request.headers.get("if-none-match") == revision:
                return Response(status_code=304)
            response.headers["ETag"] = revision
        return meta

    @app.websocket("/meta/snapshot")
    async def meta_snapshot(ws: WebSocket):
        await ws.accept()
        payload = {"meta": export_meta()}
        if include_job_summary and executor is not None:
            payload["jobs"] = executor.job_store.list(
                filters={"status": [RunStatus.PENDING, RunStatus.RUNNING]}
            )
        await ws.send_json(payload)
        await ws.close()

    return app
