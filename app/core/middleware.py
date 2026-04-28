import logging
import time
import uuid

from fastapi import Request

logger = logging.getLogger(__name__)


async def logging_middleware(request: Request, call_next):
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id

    start_time = time.perf_counter()
    response = await call_next(request)
    duration = time.perf_counter() - start_time

    logger.info(
        "%s %s completed in %.3fs — status %s [request_id=%s]",
        request.method,
        request.url.path,
        duration,
        response.status_code,
        request_id,
    )
    response.headers["X-Request-ID"] = request_id
    return response
