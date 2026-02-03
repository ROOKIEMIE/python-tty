from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING, TextIO, Tuple, Type, List

if TYPE_CHECKING:
    from python_tty.audit.sink import AuditSink
    from python_tty.runtime.router import OutputRouter


@dataclass
class AuditConfig:
    """Audit sink configuration.

    Attributes:
        enabled: Toggle audit recording.
        file_path: File path to append JSONL audit records.
        stream: File-like stream to write audit records.
        async_mode: Enable async background writer when stream is set.
        flush_interval: Flush interval (seconds) for async writer.
        keep_in_memory: Keep records in memory buffer for testing.
        sink: Custom AuditSink instance to use instead of file/stream.
    """
    enabled: bool = False
    file_path: Optional[str] = None
    stream: Optional[TextIO] = None
    async_mode: bool = False
    flush_interval: float = 1.0
    keep_in_memory: bool = False
    sink: Optional["AuditSink"] = None


@dataclass
class ExecutorConfig:
    """Executor runtime configuration.

    Attributes:
        workers: Number of worker tasks to consume invocations.
        retain_last_n: Keep only the last N completed runs in memory.
        ttl_seconds: Time-to-live for completed runs.
        pop_on_wait: Drop run state after wait_result completion.
        exempt_exceptions: Exceptions treated as cancellations.
        emit_run_events: Emit start/success/failure RuntimeEvent state.
        event_history_max: Max events kept per run for history replay.
        event_history_ttl: Time-to-live for per-run event history.
        audit: Audit sink configuration.
    """
    workers: int = 1
    retain_last_n: Optional[int] = None
    ttl_seconds: Optional[float] = None
    pop_on_wait: bool = False
    exempt_exceptions: Optional[Tuple[Type[BaseException], ...]] = None
    emit_run_events: bool = True
    event_history_max: Optional[int] = 1000
    event_history_ttl: Optional[float] = 3600.0
    audit: AuditConfig = field(default_factory=AuditConfig)


@dataclass
class ConsoleManagerConfig:
    """Console manager configuration.

    Attributes:
        use_patch_stdout: Patch stdout for prompt_toolkit rendering.
        output_router: Output router instance for UI events.
    """
    use_patch_stdout: bool = True
    output_router: Optional["OutputRouter"] = None


@dataclass
class ConsoleFactoryConfig:
    """Console factory bootstrap configuration.

    Attributes:
        run_mode: "tty" for single-thread TTY mode, "concurrent" for
            main-thread asyncio loop with TTY in a background thread.
        start_executor: Auto-start the executor when the factory starts.
        executor_in_thread: Start executor in a background thread (tty mode).
        executor_thread_name: Thread name for the executor loop thread.
        tty_thread_name: Thread name for the TTY loop (concurrent mode).
        shutdown_executor: Shutdown executor when the factory stops.
    """
    run_mode: str = "tty"
    start_executor: bool = True
    executor_in_thread: bool = True
    executor_thread_name: str = "ExecutorLoop"
    tty_thread_name: str = "TTYLoop"
    shutdown_executor: bool = True


@dataclass
class MTLSServerConfig:
    """mTLS configuration for the gRPC server.

    Attributes:
        enabled: Toggle mTLS on the RPC server.
        server_cert_file: Server certificate PEM file path.
        server_key_file: Server private key PEM file path.
        client_ca_file: CA bundle used to validate client certificates.
        require_client_cert: Require client certificate for all connections.
        principal_keys: Auth context keys to extract principal identity.
    """
    enabled: bool = False
    server_cert_file: Optional[str] = None
    server_key_file: Optional[str] = None
    client_ca_file: Optional[str] = None
    require_client_cert: bool = True
    principal_keys: Tuple[str, ...] = ("x509_common_name", "x509_subject")


@dataclass
class RPCConfig:
    """gRPC server configuration.

    Attributes:
        enabled: Toggle the RPC server.
        bind_host: Host/IP to bind.
        port: TCP port for gRPC.
        max_message_bytes: Max gRPC message size (recv/send).
        keepalive_time_ms: Keepalive ping interval.
        keepalive_timeout_ms: Keepalive timeout before closing.
        keepalive_permit_without_calls: Allow keepalive with no active RPCs.
        max_concurrent_rpcs: Max concurrent RPCs on server.
        max_streams_per_client: Max concurrent streams per client.
        stream_backpressure_queue_size: Per-stream queue size for events.
        default_deny: Default deny when exposure is not set.
        require_rpc_exposed: Require exposure.rpc=True for Invoke.
        allowed_principals: Allowlist of principals.
        admin_principals: Principals that bypass allowlist.
        require_audit: Require audit sink to start/Invoke.
        mtls: mTLS server configuration.
    """
    enabled: bool = False
    bind_host: str = "127.0.0.1"
    port: int = 50051
    max_message_bytes: int = 4 * 1024 * 1024
    keepalive_time_ms: int = 30000
    keepalive_timeout_ms: int = 10000
    keepalive_permit_without_calls: bool = True
    max_concurrent_rpcs: Optional[int] = None
    max_streams_per_client: Optional[int] = None
    stream_backpressure_queue_size: int = 1000
    default_deny: bool = True
    require_rpc_exposed: bool = True
    allowed_principals: Optional[List[str]] = None
    admin_principals: Optional[List[str]] = None
    require_audit: bool = True
    mtls: MTLSServerConfig = field(default_factory=MTLSServerConfig)


@dataclass
class WebConfig:
    """FastAPI server configuration.

    Attributes:
        enabled: Toggle the web server.
        bind_host: Host/IP to bind.
        port: TCP port for HTTP/WS.
        root_path: FastAPI root_path for reverse proxies.
        cors_allow_origins: Allowed CORS origins.
        cors_allow_credentials: Allow credentials in CORS.
        cors_allow_methods: Allowed CORS methods.
        cors_allow_headers: Allowed CORS headers.
        meta_enabled: Enable /meta endpoint.
        meta_cache_control_max_age: Cache-Control max-age for /meta.
        ws_snapshot_enabled: Enable /meta/snapshot websocket.
        ws_snapshot_include_jobs: Include running job summary in snapshot.
        ws_max_connections: Max concurrent websocket connections.
        ws_heartbeat_interval: Heartbeat interval (seconds); >0 keeps WS open.
        ws_send_queue_size: Send queue size for websocket backpressure.
    """
    enabled: bool = False
    bind_host: str = "127.0.0.1"
    port: int = 8000
    root_path: str = ""
    cors_allow_origins: List[str] = field(default_factory=list)
    cors_allow_credentials: bool = True
    cors_allow_methods: List[str] = field(default_factory=lambda: ["*"])
    cors_allow_headers: List[str] = field(default_factory=lambda: ["*"])
    meta_enabled: bool = True
    meta_cache_control_max_age: int = 30
    ws_snapshot_enabled: bool = True
    ws_snapshot_include_jobs: bool = False
    ws_max_connections: int = 100
    ws_heartbeat_interval: float = 0.0
    ws_send_queue_size: int = 100


@dataclass
class Config:
    """Top-level configuration for python-tty."""
    console_manager: ConsoleManagerConfig = field(default_factory=ConsoleManagerConfig)
    executor: ExecutorConfig = field(default_factory=ExecutorConfig)
    console_factory: ConsoleFactoryConfig = field(default_factory=ConsoleFactoryConfig)
    rpc: RPCConfig = field(default_factory=RPCConfig)
    web: WebConfig = field(default_factory=WebConfig)
