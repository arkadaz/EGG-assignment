import json
import logging
import sys
import time
import traceback
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import Request

REQUEST_ID_HEADER = "X-Request-ID"
MAX_REQUEST_ID_LENGTH = 100

logger = logging.getLogger("egg_rag.requests")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "severity": record.levelname,
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "message": record.getMessage(),
        }
        entry.update(record.fields)
        return json.dumps(entry)


def setup_request_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False


def request_id_of(request: Request) -> str:
    request_id = request.headers.get(REQUEST_ID_HEADER, "")
    if not request_id or len(request_id) > MAX_REQUEST_ID_LENGTH:
        return str(uuid4())
    return request_id


def write_log(
    request: Request, request_id: str, started: float, status: int, error: Exception | None
) -> None:
    fields = {
        "request_id": request_id,
        "method": request.method,
        "path": request.url.path,
        "status": status,
        "duration_ms": round((time.perf_counter() - started) * 1000),
        "user": getattr(request.state, "email", None),
    }
    if error is not None:
        fields["error"] = f"{type(error).__name__}: {error}"
        fields["traceback"] = "".join(traceback.format_exception(error))

    message = f"{request.method} {request.url.path} {status}"
    if status >= 500:
        logger.error(message, extra={"fields": fields})
    else:
        logger.info(message, extra={"fields": fields})


async def log_request(request: Request, call_next):
    request_id = request_id_of(request)
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception as error:
        write_log(request, request_id, started, 500, error)
        raise
    write_log(request, request_id, started, response.status_code, None)
    response.headers[REQUEST_ID_HEADER] = request_id
    return response
