"""Structured JSON logging and request tracing shared by every ShopStack service.

Each service ships an identical copy of this module so that images stay
independently buildable (no cross-service build context).
"""

import json
import logging
import sys
import time
import uuid
from contextvars import ContextVar

from fastapi import FastAPI, Request

REQUEST_ID_HEADER = "X-Request-ID"
_request_id: ContextVar[str] = ContextVar("request_id", default="-")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": _request_id.get(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        extra = getattr(record, "extra_fields", None)
        if extra:
            payload.update(extra)
        return json.dumps(payload)


def configure_logging(service: str, level: str = "INFO") -> logging.Logger:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
    # uvicorn's default access log is replaced by the middleware below
    logging.getLogger("uvicorn.access").disabled = True
    # outbound calls are already visible in the callee's request log
    logging.getLogger("httpx").setLevel(logging.WARNING)
    return logging.getLogger(service)


def current_request_id() -> str:
    return _request_id.get()


def install_request_logging(app: FastAPI, log: logging.Logger) -> None:
    @app.middleware("http")
    async def _log_requests(request: Request, call_next):
        rid = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex[:16]
        token = _request_id.set(rid)
        start = time.perf_counter()
        try:
            response = await call_next(request)
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            response.headers[REQUEST_ID_HEADER] = rid
            if request.url.path not in ("/healthz", "/ready"):
                log.info(
                    "request",
                    extra={
                        "extra_fields": {
                            "method": request.method,
                            "path": request.url.path,
                            "status": response.status_code,
                            "duration_ms": duration_ms,
                        }
                    },
                )
            return response
        except Exception:
            log.exception(
                "unhandled error", extra={"extra_fields": {"method": request.method, "path": request.url.path}}
            )
            raise
        finally:
            _request_id.reset(token)
