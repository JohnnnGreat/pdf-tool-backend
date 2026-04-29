from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from fastapi import HTTPException, UploadFile
from sqlalchemy import desc
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.user import User
from app.models.workflow import Workflow, WorkflowRun, WorkflowRunStep, WorkflowStep
from app.schemas.workflow import WorkflowCreate, WorkflowStepInput, WorkflowUpdate
from app.services import pdf_service, security_service, signature_service
from app.utils.file_handler import ALLOWED_PDF, output_name, validate_file_size, validate_file_type


StepRunner = Callable[[str, str, dict[str, Any]], None]


@dataclass(frozen=True)
class StepSpec:
    key: str
    label: str
    description: str
    category: str
    input_type: str
    output_type: str
    config_schema: dict[str, dict[str, Any]]
    runner: StepRunner


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "step"


def _listify(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return [str(value).strip()]


def _run_compress(input_path: str, output_path: str, config: dict[str, Any]) -> None:
    pdf_service.compress_pdf(input_path, output_path, quality=str(config.get("quality", "medium")))


def _run_rotate(input_path: str, output_path: str, config: dict[str, Any]) -> None:
    pdf_service.rotate_pdf(
        input_path,
        output_path,
        angle=int(config.get("angle", 90)),
        pages=config.get("pages"),
    )


def _run_page_numbers(input_path: str, output_path: str, config: dict[str, Any]) -> None:
    pdf_service.add_page_numbers(
        input_path,
        output_path,
        position=str(config.get("position", "bottom-center")),
        font_size=int(config.get("font_size", 12)),
        start_number=int(config.get("start_number", 1)),
    )


def _run_watermark_text(input_path: str, output_path: str, config: dict[str, Any]) -> None:
    pdf_service.add_text_watermark(
        input_path,
        output_path,
        text=str(config["text"]),
        opacity=float(config.get("opacity", 0.3)),
        font_size=int(config.get("font_size", 50)),
    )


def _run_header_footer(input_path: str, output_path: str, config: dict[str, Any]) -> None:
    pdf_service.add_header_footer(
        input_path,
        output_path,
        header=str(config.get("header", "")),
        footer=str(config.get("footer", "")),
        font_size=int(config.get("font_size", 10)),
    )


def _run_crop(input_path: str, output_path: str, config: dict[str, Any]) -> None:
    pdf_service.crop_pdf(
        input_path,
        output_path,
        x=float(config.get("x", 0)),
        y=float(config.get("y", 0)),
        width=float(config.get("width", 400)),
        height=float(config.get("height", 600)),
    )


def _run_flatten(input_path: str, output_path: str, config: dict[str, Any]) -> None:
    del config
    pdf_service.flatten_pdf(input_path, output_path)


def _run_repair(input_path: str, output_path: str, config: dict[str, Any]) -> None:
    del config
    pdf_service.repair_pdf(input_path, output_path)


def _run_redact_text(input_path: str, output_path: str, config: dict[str, Any]) -> None:
    patterns = _listify(config.get("patterns"))
    pdf_service.redact_text(input_path, output_path, patterns)


def _run_encrypt(input_path: str, output_path: str, config: dict[str, Any]) -> None:
    security_service.encrypt_pdf(
        input_path,
        output_path,
        user_password=str(config["user_password"]),
        owner_password=str(config.get("owner_password", "")),
    )


def _run_sanitize(input_path: str, output_path: str, config: dict[str, Any]) -> None:
    del config
    security_service.sanitize_pdf(input_path, output_path)


def _run_redact_pii(input_path: str, output_path: str, config: dict[str, Any]) -> None:
    patterns = _listify(config.get("patterns"))
    security_service.auto_redact_pii(input_path, output_path, patterns)


def _run_text_stamp(input_path: str, output_path: str, config: dict[str, Any]) -> None:
    signature_service.add_text_stamp(
        input_path,
        output_path,
        text=str(config["text"]),
        page_number=int(config.get("page_number", 1)),
        x=float(config.get("x", 100)),
        y=float(config.get("y", 100)),
        font_size=int(config.get("font_size", 36)),
        rotate=int(config.get("rotate", 0)),
    )


def _run_date_stamp(input_path: str, output_path: str, config: dict[str, Any]) -> None:
    signature_service.add_date_stamp(
        input_path,
        output_path,
        date_str=str(config.get("date_str") or datetime.utcnow().date().isoformat()),
        page_number=int(config.get("page_number", 1)),
        x=float(config.get("x", 400)),
        y=float(config.get("y", 750)),
        font_size=int(config.get("font_size", 14)),
    )


STEP_REGISTRY: dict[str, StepSpec] = {
    "pdf.compress": StepSpec(
        key="pdf.compress",
        label="Compress PDF",
        description="Reduce file size using the existing PDF compression service.",
        category="PDF",
        input_type="pdf",
        output_type="pdf",
        config_schema={
            "quality": {
                "type": "string",
                "label": "Quality",
                "default": "medium",
                "options": ["low", "medium", "high"],
            }
        },
        runner=_run_compress,
    ),
    "pdf.rotate": StepSpec(
        key="pdf.rotate",
        label="Rotate PDF",
        description="Rotate all pages or selected pages by 90, 180, or 270 degrees.",
        category="PDF",
        input_type="pdf",
        output_type="pdf",
        config_schema={
            "angle": {
                "type": "integer",
                "label": "Angle",
                "required": True,
                "default": 90,
                "options": [90, 180, 270],
            },
            "pages": {"type": "string", "label": "Pages", "description": "Comma-separated page numbers"},
        },
        runner=_run_rotate,
    ),
    "pdf.page_numbers": StepSpec(
        key="pdf.page_numbers",
        label="Add Page Numbers",
        description="Apply page numbering to every page in the document.",
        category="PDF",
        input_type="pdf",
        output_type="pdf",
        config_schema={
            "position": {
                "type": "string",
                "label": "Position",
                "default": "bottom-center",
                "options": ["bottom-center", "bottom-left", "bottom-right", "top-left", "top-center", "top-right"],
            },
            "font_size": {"type": "integer", "label": "Font Size", "default": 12},
            "start_number": {"type": "integer", "label": "Start Number", "default": 1},
        },
        runner=_run_page_numbers,
    ),
    "pdf.watermark_text": StepSpec(
        key="pdf.watermark_text",
        label="Text Watermark",
        description="Place a text watermark over every page.",
        category="PDF",
        input_type="pdf",
        output_type="pdf",
        config_schema={
            "text": {"type": "string", "label": "Watermark Text", "required": True},
            "opacity": {"type": "number", "label": "Opacity", "default": 0.3},
            "font_size": {"type": "integer", "label": "Font Size", "default": 50},
        },
        runner=_run_watermark_text,
    ),
    "pdf.header_footer": StepSpec(
        key="pdf.header_footer",
        label="Header/Footer",
        description="Add header and footer text to every page.",
        category="PDF",
        input_type="pdf",
        output_type="pdf",
        config_schema={
            "header": {"type": "string", "label": "Header"},
            "footer": {"type": "string", "label": "Footer"},
            "font_size": {"type": "integer", "label": "Font Size", "default": 10},
        },
        runner=_run_header_footer,
    ),
    "pdf.crop": StepSpec(
        key="pdf.crop",
        label="Crop PDF",
        description="Crop every page to a given rectangle.",
        category="PDF",
        input_type="pdf",
        output_type="pdf",
        config_schema={
            "x": {"type": "number", "label": "X", "default": 0},
            "y": {"type": "number", "label": "Y", "default": 0},
            "width": {"type": "number", "label": "Width", "default": 400},
            "height": {"type": "number", "label": "Height", "default": 600},
        },
        runner=_run_crop,
    ),
    "pdf.flatten": StepSpec(
        key="pdf.flatten",
        label="Flatten PDF",
        description="Flatten forms and annotations into the page content.",
        category="PDF",
        input_type="pdf",
        output_type="pdf",
        config_schema={},
        runner=_run_flatten,
    ),
    "pdf.repair": StepSpec(
        key="pdf.repair",
        label="Repair PDF",
        description="Attempt to repair a malformed or partially corrupted PDF.",
        category="PDF",
        input_type="pdf",
        output_type="pdf",
        config_schema={},
        runner=_run_repair,
    ),
    "pdf.redact_text": StepSpec(
        key="pdf.redact_text",
        label="Redact Text",
        description="Redact matching text patterns throughout the document.",
        category="PDF",
        input_type="pdf",
        output_type="pdf",
        config_schema={
            "patterns": {
                "type": "array",
                "label": "Patterns",
                "required": True,
                "description": "List of words or phrases to redact",
            }
        },
        runner=_run_redact_text,
    ),
    "pdf.encrypt": StepSpec(
        key="pdf.encrypt",
        label="Encrypt PDF",
        description="Protect the final document with a password.",
        category="Security",
        input_type="pdf",
        output_type="pdf",
        config_schema={
            "user_password": {"type": "string", "label": "User Password", "required": True},
            "owner_password": {"type": "string", "label": "Owner Password"},
        },
        runner=_run_encrypt,
    ),
    "pdf.sanitize": StepSpec(
        key="pdf.sanitize",
        label="Sanitize PDF",
        description="Strip metadata and potentially risky embedded data from a PDF.",
        category="Security",
        input_type="pdf",
        output_type="pdf",
        config_schema={},
        runner=_run_sanitize,
    ),
    "pdf.redact_pii": StepSpec(
        key="pdf.redact_pii",
        label="Auto-Redact PII",
        description="Redact common PII such as email addresses, phone numbers, or SSNs.",
        category="Security",
        input_type="pdf",
        output_type="pdf",
        config_schema={
            "patterns": {
                "type": "array",
                "label": "PII Patterns",
                "required": True,
                "default": ["email"],
                "options": ["email", "phone", "ssn"],
            }
        },
        runner=_run_redact_pii,
    ),
    "pdf.text_stamp": StepSpec(
        key="pdf.text_stamp",
        label="Text Stamp",
        description="Apply a text stamp on a specific page.",
        category="Signature",
        input_type="pdf",
        output_type="pdf",
        config_schema={
            "text": {"type": "string", "label": "Stamp Text", "required": True},
            "page_number": {"type": "integer", "label": "Page Number", "default": 1},
            "x": {"type": "number", "label": "X", "default": 100},
            "y": {"type": "number", "label": "Y", "default": 100},
            "font_size": {"type": "integer", "label": "Font Size", "default": 36},
            "rotate": {"type": "integer", "label": "Rotation", "default": 0},
        },
        runner=_run_text_stamp,
    ),
    "pdf.date_stamp": StepSpec(
        key="pdf.date_stamp",
        label="Date Stamp",
        description="Stamp the document with a date string.",
        category="Signature",
        input_type="pdf",
        output_type="pdf",
        config_schema={
            "date_str": {"type": "string", "label": "Date String", "description": "Defaults to today's UTC date"},
            "page_number": {"type": "integer", "label": "Page Number", "default": 1},
            "x": {"type": "number", "label": "X", "default": 400},
            "y": {"type": "number", "label": "Y", "default": 750},
            "font_size": {"type": "integer", "label": "Font Size", "default": 14},
        },
        runner=_run_date_stamp,
    ),
}


class WorkflowService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_catalog(self) -> list[dict[str, Any]]:
        return [
            {
                "step_key": spec.key,
                "label": spec.label,
                "description": spec.description,
                "category": spec.category,
                "input_type": spec.input_type,
                "output_type": spec.output_type,
                "config_schema": spec.config_schema,
            }
            for spec in STEP_REGISTRY.values()
        ]

    def list_workflows(self, user_id: int) -> list[Workflow]:
        return (
            self.db.query(Workflow)
            .options(selectinload(Workflow.steps))
            .filter(Workflow.user_id == user_id)
            .order_by(desc(Workflow.updated_at), desc(Workflow.created_at))
            .all()
        )

    def get_workflow(self, workflow_id: int, user_id: int) -> Workflow:
        workflow = (
            self.db.query(Workflow)
            .options(selectinload(Workflow.steps))
            .filter(Workflow.id == workflow_id, Workflow.user_id == user_id)
            .first()
        )
        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found.")
        return workflow

    def create_workflow(self, user: User, data: WorkflowCreate) -> Workflow:
        steps = self._build_step_models(data.steps)
        workflow = Workflow(
            user_id=user.id,
            name=data.name.strip(),
            description=data.description,
            is_active=data.is_active,
            steps=steps,
        )
        self.db.add(workflow)
        self.db.commit()
        return self.get_workflow(workflow.id, user.id)

    def update_workflow(self, workflow: Workflow, data: WorkflowUpdate) -> Workflow:
        workflow.name = data.name.strip()
        workflow.description = data.description
        workflow.is_active = data.is_active
        workflow.steps = self._build_step_models(data.steps)
        self.db.commit()
        return self.get_workflow(workflow.id, workflow.user_id)

    def delete_workflow(self, workflow: Workflow) -> None:
        self.db.delete(workflow)
        self.db.commit()

    def list_runs(self, user_id: int) -> list[WorkflowRun]:
        return (
            self.db.query(WorkflowRun)
            .options(selectinload(WorkflowRun.steps))
            .filter(WorkflowRun.user_id == user_id)
            .order_by(desc(WorkflowRun.created_at))
            .all()
        )

    def get_run(self, run_id: int, user_id: int) -> WorkflowRun:
        run = (
            self.db.query(WorkflowRun)
            .options(selectinload(WorkflowRun.steps))
            .filter(WorkflowRun.id == run_id, WorkflowRun.user_id == user_id)
            .first()
        )
        if not run:
            raise HTTPException(status_code=404, detail="Workflow run not found.")
        return run

    async def enqueue_run(self, workflow: Workflow, user: User, file: UploadFile) -> WorkflowRun:
        if not workflow.is_active:
            raise HTTPException(status_code=400, detail="Workflow is inactive.")
        if not workflow.steps:
            raise HTTPException(status_code=400, detail="Workflow has no steps.")

        validate_file_type(file, ALLOWED_PDF)
        file_bytes = await file.read()
        validate_file_size(file_bytes)

        run = WorkflowRun(
            workflow_id=workflow.id,
            user_id=user.id,
            workflow_name=workflow.name,
            input_filename=file.filename or "input.pdf",
            input_file_path="",
            status="queued",
            steps_total=len(workflow.steps),
            steps_completed=0,
            steps=[
                WorkflowRunStep(
                    workflow_step_id=step.id,
                    position=step.position,
                    step_key=step.step_key,
                    label=step.label,
                    config=dict(step.config or {}),
                    status="queued",
                )
                for step in workflow.steps
            ],
        )
        self.db.add(run)
        self.db.flush()

        run_dir = os.path.join(os.path.abspath(settings.RESULTS_DIR), "workflow-runs", str(run.id))
        os.makedirs(run_dir, exist_ok=True)
        ext = Path(file.filename or "input.pdf").suffix.lower() or ".pdf"
        input_path = os.path.join(run_dir, f"input{ext}")
        with open(input_path, "wb") as handle:
            handle.write(file_bytes)
        run.input_file_path = input_path

        self.db.commit()
        return self.get_run(run.id, user.id)

    def _build_step_models(self, steps: list[WorkflowStepInput]) -> list[WorkflowStep]:
        current_type = "pdf"
        result: list[WorkflowStep] = []

        for index, step in enumerate(steps, start=1):
            spec = STEP_REGISTRY.get(step.step_key)
            if not spec:
                raise HTTPException(status_code=422, detail=f"Unknown workflow step: {step.step_key}")
            if spec.input_type != current_type:
                raise HTTPException(
                    status_code=422,
                    detail=f"Step '{step.step_key}' expects '{spec.input_type}' input, but current pipeline output is '{current_type}'.",
                )

            config = dict(step.config or {})
            self._validate_step_config(spec, config)
            result.append(
                WorkflowStep(
                    position=index,
                    step_key=spec.key,
                    label=(step.label or spec.label).strip(),
                    config=config,
                )
            )
            current_type = spec.output_type

        return result

    def _validate_step_config(self, spec: StepSpec, config: dict[str, Any]) -> None:
        for field_name, field_schema in spec.config_schema.items():
            required = bool(field_schema.get("required"))
            if required:
                value = config.get(field_name)
                if value is None or (isinstance(value, str) and not value.strip()) or (isinstance(value, list) and not value):
                    raise HTTPException(
                        status_code=422,
                        detail=f"Step '{spec.key}' requires config field '{field_name}'.",
                    )

            if field_name not in config:
                continue

            value = config[field_name]
            field_type = field_schema.get("type")
            if field_type == "string" and value is not None and not isinstance(value, str):
                raise HTTPException(status_code=422, detail=f"Config field '{field_name}' for step '{spec.key}' must be a string.")
            if field_type == "integer" and not isinstance(value, int):
                raise HTTPException(status_code=422, detail=f"Config field '{field_name}' for step '{spec.key}' must be an integer.")
            if field_type == "number" and not isinstance(value, (int, float)):
                raise HTTPException(status_code=422, detail=f"Config field '{field_name}' for step '{spec.key}' must be a number.")
            if field_type == "boolean" and not isinstance(value, bool):
                raise HTTPException(status_code=422, detail=f"Config field '{field_name}' for step '{spec.key}' must be a boolean.")
            if field_type == "array" and not isinstance(value, (list, str)):
                raise HTTPException(status_code=422, detail=f"Config field '{field_name}' for step '{spec.key}' must be a list or comma-separated string.")

    @staticmethod
    def execute_run(run_id: int) -> None:
        db = SessionLocal()
        try:
            run = (
                db.query(WorkflowRun)
                .options(selectinload(WorkflowRun.steps))
                .filter(WorkflowRun.id == run_id)
                .first()
            )
            if not run:
                return

            run.status = "running"
            run.started_at = datetime.utcnow()
            run.error_message = None
            db.commit()

            current_path = run.input_file_path
            run_dir = os.path.dirname(current_path)

            for step in sorted(run.steps, key=lambda item: item.position):
                spec = STEP_REGISTRY.get(step.step_key)
                if not spec:
                    WorkflowService._fail_run(db, run, step, f"Unsupported workflow step: {step.step_key}")
                    return

                step.status = "running"
                step.started_at = datetime.utcnow()
                step.error_message = None
                db.commit()

                output_path = os.path.join(run_dir, f"step_{step.position:02d}_{_slug(step.step_key)}.pdf")

                try:
                    spec.runner(current_path, output_path, dict(step.config or {}))
                    step.status = "success"
                    step.completed_at = datetime.utcnow()
                    step.details = {
                        "output_filename": os.path.basename(output_path),
                        "output_size_bytes": os.path.getsize(output_path),
                    }
                    run.steps_completed = sum(1 for item in run.steps if item.status == "success")
                    current_path = output_path
                    db.commit()
                except HTTPException as exc:
                    detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
                    WorkflowService._fail_run(db, run, step, detail)
                    return
                except Exception as exc:  # pragma: no cover - safety net
                    WorkflowService._fail_run(db, run, step, str(exc))
                    return

            final_filename = output_name(run.input_filename, "workflow-result", "pdf")
            final_path = os.path.join(run_dir, final_filename)
            if os.path.abspath(current_path) != os.path.abspath(final_path):
                shutil.copyfile(current_path, final_path)

            run.output_file_path = final_path
            run.output_filename = os.path.basename(final_path)
            run.output_size_bytes = os.path.getsize(final_path)
            run.status = "success"
            run.completed_at = datetime.utcnow()
            db.commit()
        finally:
            db.close()

    @staticmethod
    def _fail_run(db: Session, run: WorkflowRun, step: WorkflowRunStep, message: str) -> None:
        step.status = "failed"
        step.completed_at = datetime.utcnow()
        step.error_message = message
        run.status = "failed"
        run.completed_at = datetime.utcnow()
        run.error_message = message
        db.commit()
