import time
import logging

from fastapi import Request

logger = logging.getLogger(__name__)


async def logging_middleware(request: Request, call_next):
    start_time = time.perf_counter()
    response = await call_next(request)
    duration = time.perf_counter() - start_time
    logger.info(
        "%s %s completed in %.3fs — status %s",
        request.method,
        request.url.path,
        duration,
        response.status_code,
    )
    return response
