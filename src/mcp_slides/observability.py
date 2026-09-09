"""Allowlisted diagnostics: no prompts, credentials, URLs or exception messages."""
from contextlib import contextmanager
from contextvars import ContextVar
import logging
import time

request_id = ContextVar("request_id", default="local")
logger = logging.getLogger("uvicorn.error")


@contextmanager
def operation(stage):
    started = time.monotonic()
    try:
        yield
    except Exception as exc:
        logger.warning("operation request_id=%s stage=%s outcome=failed error_type=%s elapsed_ms=%d",
                       request_id.get(), stage, type(exc).__name__,
                       int((time.monotonic() - started) * 1000))
        raise
    else:
        logger.info("operation request_id=%s stage=%s outcome=ok elapsed_ms=%d",
                    request_id.get(), stage, int((time.monotonic() - started) * 1000))


def configure_logging():
    # HTTP clients log full OAuth/asset URLs at INFO. MCP logs tool error text,
    # which can legitimately contain a private recovery link. Use our safe events.
    for name in ("httpx", "httpx2", "httpcore", "mcp.server.mcpserver.server"):
        logging.getLogger(name).setLevel(logging.WARNING)
    # Google read retries include the private request URI and raw response body
    # in WARNING records. Our operation events report the eventual outcome.
    logging.getLogger("googleapiclient.http").setLevel(logging.ERROR)
