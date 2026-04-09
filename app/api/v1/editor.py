"""PDF live-editor router.

Endpoints
---------
POST /editor/load           Upload PDF → JSON structure (pages + text blocks + thumbnails)
POST /editor/apply          Upload PDF + operations JSON → modified PDF
POST /editor/page-thumbnail Upload PDF + page number → PNG image
"""
import json

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response

from app.services import editor_service
from app.utils.file_handler import (
    ALLOWED_PDF,
    cleanup,
    make_job_dirs,
    read_file,
    read_upload,
    save_bytes,
    validate_file_type,
)
from app.utils.rate_limiter import get_client_ip, rate_limiter

router = APIRouter(prefix="/editor", tags=["PDF Editor"])


def _rl(request: Request):
    rate_limiter.check(get_client_ip(request))


# ---------------------------------------------------------------------------
# Load — parse PDF structure
# ---------------------------------------------------------------------------

@router.post("/load")
async def load_pdf(
    request: Request,
    file: UploadFile = File(...),
    thumbnail_scale: float = Form(1.5),
):
    """Upload a PDF and receive its page structure.

    Returns JSON:
    ```json
    {
      "page_count": 3,
      "pages": [
        {
          "page_number": 0,
          "width": 595.0,
          "height": 842.0,
          "thumbnail": "<base64 PNG>",
          "text_blocks": [
            { "text": "Hello", "x0": 72, "y0": 50, "x1": 120, "y1": 62,
              "font_size": 12, "font": "Helvetica", "color": [0,0,0] }
          ]
        }
      ]
    }
    ```
    """
    _rl(request)
    validate_file_type(file, ALLOWED_PDF)
    _, up, _ = make_job_dirs()
    try:
        content = await read_upload(file)
        input_path = save_bytes(content, up, "input.pdf")
        result = editor_service.load_pdf(input_path, thumbnail_scale=thumbnail_scale)
        return result
    finally:
        cleanup(up)


# ---------------------------------------------------------------------------
# Page thumbnail — high-res render of a single page
# ---------------------------------------------------------------------------

@router.post("/page-thumbnail")
async def page_thumbnail(
    request: Request,
    file: UploadFile = File(...),
    page: int = Form(0),
    scale: float = Form(2.0),
):
    """Render a specific page at the requested zoom and return PNG bytes."""
    _rl(request)
    validate_file_type(file, ALLOWED_PDF)
    _, up, _ = make_job_dirs()
    try:
        content = await read_upload(file)
        input_path = save_bytes(content, up, "input.pdf")
        png_bytes = editor_service.render_page(input_path, page_number=page, scale=scale)
        return Response(
            content=png_bytes,
            media_type="image/png",
            headers={"Content-Disposition": f'inline; filename="page_{page}.png"'},
        )
    finally:
        cleanup(up)


# ---------------------------------------------------------------------------
# Apply — execute edit operations → return modified PDF
# ---------------------------------------------------------------------------

@router.post("/apply")
async def apply_edits(
    request: Request,
    file: UploadFile = File(...),
    operations: str = Form(...),
):
    """Apply a list of edit operations to a PDF and download the result.

    `operations` is a JSON string — array of operation objects.

    **Operation types**

    | type | required fields | optional fields |
    |---|---|---|
    | `replace_text` | `page`, `original_text`, `text` | `font_size`, `color` |
    | `add_text` | `page`, `x`, `y`, `text` | `font_size`, `color` |
    | `add_image` | `page`, `x`, `y`, `width`, `height`, `image_b64` | — |
    | `add_highlight` | `page`, `x`, `y`, `width`, `height` | `color` (default yellow) |
    | `add_rectangle` | `page`, `x`, `y`, `width`, `height` | `color`, `stroke_width` |
    | `add_line` | `page`, `x1`, `y1`, `x2`, `y2` | `color`, `stroke_width` |
    | `whiteout` | `page`, `x`, `y`, `width`, `height` | — |
    | `delete_page` | `page` | — |
    | `add_blank_page` | — | `after_page` |

    `color` is `[R, G, B]` with values **0–255** or **0.0–1.0** (both accepted).

    **Example body (multipart)**
    ```
    file=<pdf binary>
    operations=[
      {"type":"replace_text","page":0,"original_text":"Draft","text":"Final"},
      {"type":"add_text","page":0,"x":50,"y":750,"text":"Approved","font_size":14,"color":[0,128,0]},
      {"type":"add_highlight","page":0,"x":72,"y":100,"width":200,"height":20},
      {"type":"add_rectangle","page":1,"x":50,"y":50,"width":300,"height":200,"color":[1,0,0]},
      {"type":"delete_page","page":2}
    ]
    ```
    """
    _rl(request)
    validate_file_type(file, ALLOWED_PDF)

    try:
        ops: list = json.loads(operations)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail=f"operations is not valid JSON: {exc}") from exc

    if not isinstance(ops, list):
        raise HTTPException(status_code=422, detail="operations must be a JSON array")

    _, up, out = make_job_dirs()
    try:
        content = await read_upload(file)
        input_path = save_bytes(content, up, "input.pdf")
        output_path = f"{out}/edited.pdf"
        editor_service.apply_edits(input_path, output_path, ops)
        data = read_file(output_path)
        return Response(
            content=data,
            media_type="application/pdf",
            headers={"Content-Disposition": 'attachment; filename="edited.pdf"'},
        )
    finally:
        cleanup(up, out)
