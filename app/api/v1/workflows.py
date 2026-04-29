import os

from fastapi import APIRouter, BackgroundTasks, Depends, File, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.models.workflow import Workflow, WorkflowRun
from app.schemas.workflow import (
    WorkflowCatalogEntry,
    WorkflowCreate,
    WorkflowResponse,
    WorkflowRunListResponse,
    WorkflowRunResponse,
    WorkflowRunStepResponse,
    WorkflowStepResponse,
    WorkflowUpdate,
)
from app.services.workflow_service import WorkflowService

router = APIRouter(prefix="/workflows", tags=["Workflows"])


def _workflow_response(workflow: Workflow) -> WorkflowResponse:
    return WorkflowResponse(
        id=workflow.id,
        name=workflow.name,
        description=workflow.description,
        is_active=workflow.is_active,
        created_at=workflow.created_at,
        updated_at=workflow.updated_at,
        steps=[
            WorkflowStepResponse.model_validate(step, from_attributes=True)
            for step in sorted(workflow.steps, key=lambda item: item.position)
        ],
    )


def _run_response(run: WorkflowRun) -> WorkflowRunResponse:
    return WorkflowRunResponse(
        id=run.id,
        workflow_id=run.workflow_id,
        workflow_name=run.workflow_name,
        input_filename=run.input_filename,
        output_filename=run.output_filename,
        output_size_bytes=run.output_size_bytes,
        status=run.status,
        error_message=run.error_message,
        steps_total=run.steps_total,
        steps_completed=run.steps_completed,
        created_at=run.created_at,
        started_at=run.started_at,
        completed_at=run.completed_at,
        download_url=f"/api/v1/workflows/runs/{run.id}/download" if run.output_file_path and run.status == "success" else None,
        steps=[
            WorkflowRunStepResponse.model_validate(step, from_attributes=True)
            for step in sorted(run.steps, key=lambda item: item.position)
        ],
    )


@router.get("/catalog", response_model=list[WorkflowCatalogEntry])
def list_workflow_catalog(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    del current_user
    return WorkflowService(db).list_catalog()


@router.get("", response_model=list[WorkflowResponse])
def list_workflows(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    workflows = WorkflowService(db).list_workflows(current_user.id)
    return [_workflow_response(workflow) for workflow in workflows]


@router.post("", response_model=WorkflowResponse, status_code=status.HTTP_201_CREATED)
def create_workflow(
    data: WorkflowCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    workflow = WorkflowService(db).create_workflow(current_user, data)
    return _workflow_response(workflow)


@router.get("/runs", response_model=WorkflowRunListResponse)
def list_workflow_runs(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    runs = WorkflowService(db).list_runs(current_user.id)
    return WorkflowRunListResponse(runs=[_run_response(run) for run in runs])


@router.get("/runs/{run_id}", response_model=WorkflowRunResponse)
def get_workflow_run(
    run_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    run = WorkflowService(db).get_run(run_id, current_user.id)
    return _run_response(run)


@router.get("/runs/{run_id}/download")
def download_workflow_run(
    run_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    run = WorkflowService(db).get_run(run_id, current_user.id)
    if run.status != "success" or not run.output_file_path or not os.path.exists(run.output_file_path):
        return Response(status_code=status.HTTP_409_CONFLICT, content="Workflow output is not ready yet.")
    return FileResponse(run.output_file_path, filename=run.output_filename or os.path.basename(run.output_file_path))


@router.get("/{workflow_id}", response_model=WorkflowResponse)
def get_workflow(
    workflow_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    workflow = WorkflowService(db).get_workflow(workflow_id, current_user.id)
    return _workflow_response(workflow)


@router.put("/{workflow_id}", response_model=WorkflowResponse)
def update_workflow(
    workflow_id: int,
    data: WorkflowUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = WorkflowService(db)
    workflow = service.get_workflow(workflow_id, current_user.id)
    workflow = service.update_workflow(workflow, data)
    return _workflow_response(workflow)


@router.delete("/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_workflow(
    workflow_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = WorkflowService(db)
    workflow = service.get_workflow(workflow_id, current_user.id)
    service.delete_workflow(workflow)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{workflow_id}/run", response_model=WorkflowRunResponse, status_code=status.HTTP_202_ACCEPTED)
async def run_workflow(
    workflow_id: int,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = WorkflowService(db)
    workflow = service.get_workflow(workflow_id, current_user.id)
    run = await service.enqueue_run(workflow, current_user, file)
    background_tasks.add_task(WorkflowService.execute_run, run.id)
    return _run_response(run)
