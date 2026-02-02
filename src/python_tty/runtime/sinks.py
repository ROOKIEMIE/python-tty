import asyncio

class TTYEventSink:
    def __init__(self, job_store, router):
        self._job_store = job_store
        self._router = router
        self._task: asyncio.Task | None = None

    async def _run(self):
        queue = self._job_store.subscribe_all()
        while True:
            event = await queue.get()
            if self._router is None:
                continue
            self._router.emit(event)

    def start(self, loop):
        if self._task is not None:
            return
        self._task = loop.create_task(self._run())

    def stop(self):
        if self._task is None:
            return
        self._task.cancel()
        self._task = None
