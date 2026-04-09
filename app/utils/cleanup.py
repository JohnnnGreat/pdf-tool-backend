import os
import shutil
import time
import logging
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger(__name__)


def cleanup_old_jobs() -> None:
    """Delete job dirs older than TEMP_FILE_RETENTION_MINUTES."""
    retention_secs = settings.TEMP_FILE_RETENTION_MINUTES * 60
    cutoff = time.time() - retention_secs

    for base_dir in [settings.OUTPUT_DIR, settings.UPLOAD_DIR]:
        if not os.path.exists(base_dir):
            continue
        for job_dir in Path(base_dir).iterdir():
            if not job_dir.is_dir():
                continue
            try:
                if job_dir.stat().st_mtime < cutoff:
                    shutil.rmtree(job_dir)
                    logger.info("Cleaned up expired job dir: %s", job_dir)
            except Exception as exc:
                logger.warning("Cleanup failed for %s: %s", job_dir, exc)
