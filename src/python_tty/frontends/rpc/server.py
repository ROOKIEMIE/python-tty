import asyncio
from typing import Optional

import grpc

from python_tty.config import RPCConfig
from python_tty.frontends.rpc.core import add_runtime_service_with_config


def _build_server_options(config: RPCConfig):
    options = [
        ("grpc.keepalive_time_ms", config.keepalive_time_ms),
        ("grpc.keepalive_timeout_ms", config.keepalive_timeout_ms),
        ("grpc.keepalive_permit_without_calls", int(config.keepalive_permit_without_calls)),
        ("grpc.max_receive_message_length", config.max_message_bytes),
        ("grpc.max_send_message_length", config.max_message_bytes),
    ]
    if config.max_streams_per_client is not None:
        options.append(("grpc.max_concurrent_streams", config.max_streams_per_client))
    return options


def _load_mtls_credentials(config: RPCConfig):
    if not config.mtls.enabled:
        return None
    if not (config.mtls.server_cert_file and config.mtls.server_key_file):
        raise RuntimeError("mTLS enabled but server cert/key not configured")
    with open(config.mtls.server_cert_file, "rb") as cert_file:
        server_cert = cert_file.read()
    with open(config.mtls.server_key_file, "rb") as key_file:
        server_key = key_file.read()
    root_certs = None
    if config.mtls.client_ca_file:
        with open(config.mtls.client_ca_file, "rb") as ca_file:
            root_certs = ca_file.read()
    return grpc.ssl_server_credentials(
        ((server_key, server_cert),),
        root_certificates=root_certs,
        require_client_auth=config.mtls.require_client_cert,
    )


async def start_rpc_server(executor,
                           config: RPCConfig,
                           service=None,
                           manager=None) -> grpc.aio.Server:
    if config.require_audit and executor.audit_sink is None:
        raise RuntimeError("RPC requires audit_sink; executor.audit_sink is None")
    options = _build_server_options(config)
    server = grpc.aio.server(
        options=options,
        maximum_concurrent_rpcs=config.max_concurrent_rpcs,
    )
    add_runtime_service_with_config(server, executor, config, service=service, manager=manager)
    creds = _load_mtls_credentials(config)
    target = f"{config.bind_host}:{config.port}"
    if creds is None:
        server.add_insecure_port(target)
    else:
        server.add_secure_port(target, creds)
    await server.start()
    return server


async def stop_rpc_server(server: Optional[grpc.aio.Server], grace: float = 3.0):
    if server is None:
        return
    await server.stop(grace)
