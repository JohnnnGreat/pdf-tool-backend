from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models.job import ProcessingJob
from app.models.user import User
from app.schemas.job import JobCreate, JobResponse

router = APIRouter(prefix="/jobs", tags=["Jobs"])


@router.post("", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
def record_job(
    data: JobCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    job = ProcessingJob(
        user_id=current_user.id,
        tool_slug=data.tool_slug,
        tool_name=data.tool_name,
        category=data.category,
        filename=data.filename,
        file_size_bytes=data.file_size_bytes,
        output_size_bytes=data.output_size_bytes,
        status=data.status,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job
