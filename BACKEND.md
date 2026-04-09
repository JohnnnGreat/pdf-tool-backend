# DocForge Backend API

> FastAPI-powered backend for document processing. Handles PDF manipulation, format conversion,
> image processing, OCR, and more.

---

## Quick Start

```bash
# Clone and enter the project
cd pdf-tool-backend

# Create virtual environment
python -m venv venv

# Activate it
source venv/bin/activate         # Mac/Linux
venv\Scripts\activate            # Windows

# Install dependencies
pip install -r requirements.txt

# Run the server
uvicorn main:app --reload --port 8000
```

Open `http://localhost:8000/docs` for the interactive API playground.

---

## Tech Stack

| Component          | Technology                | Purpose                                             |
| ------------------ | ------------------------- | --------------------------------------------------- |
| Framework          | FastAPI                   | Async API framework with auto-generated docs        |
| Server             | Uvicorn                   | ASGI server to run the app                          |
| PDF Engine         | PyMuPDF (fitz)            | Merge, split, compress, rotate, watermark, extract  |
| PDF Extended       | pypdf                     | Encrypt, decrypt, permissions, metadata             |
| PDF Creator        | reportlab                 | Generate PDFs from scratch (invoices, certificates) |
| Image Engine       | Pillow (PIL)              | Resize, crop, compress, convert, filters, watermark |
| Background Removal | rembg                     | AI-powered image background removal                 |
| OCR Engine         | pytesseract + pdf2image   | Extract text from images and scanned PDFs           |
| Word Engine        | python-docx               | Read, create, edit .docx files                      |
| Excel Engine       | openpyxl                  | Read, create, edit .xlsx files                      |
| PowerPoint Engine  | python-pptx               | Read, create, edit .pptx files                      |
| Format Conversion  | LibreOffice (headless)    | High-fidelity DOC/XLS/PPT to PDF conversion         |
| QR/Barcode         | qrcode, python-barcode    | Generate QR codes and barcodes                      |
| Task Queue         | Celery + Redis (optional) | Background processing for large files               |
| Archiving          | zipfile (stdlib)          | ZIP creation and extraction                         |

---

## Project Structure

```
pdf-tool-backend/
├── main.py                      # App entry point, CORS, router registration
├── config.py                    # Settings, env variables, file size limits
├── requirements.txt             # Python dependencies
│
├── routers/                     # API endpoint handlers
│   ├── __init__.py
│   ├── merge.py                 # POST /api/merge
│   ├── split.py                 # POST /api/split
│   ├── compress.py              # POST /api/compress
│   ├── rotate.py                # POST /api/rotate
│   ├── pages.py                 # POST /api/delete-pages, /api/reorder, /api/extract-pages
│   ├── watermark.py             # POST /api/watermark
│   ├── page_numbers.py          # POST /api/page-numbers
│   ├── header_footer.py         # POST /api/header-footer
│   ├── metadata.py              # POST /api/metadata
│   ├── convert.py               # All format conversion endpoints
│   ├── image.py                 # All image processing endpoints
│   ├── ocr.py                   # All OCR endpoints
│   ├── security.py              # Encrypt, decrypt, permissions
│   ├── signature.py             # Signature and stamp endpoints
│   ├── generator.py             # QR code, barcode, invoice, resume
│   ├── document.py              # Word, Excel, PowerPoint operations
│   ├── batch.py                 # Batch processing endpoints
│   └── utility.py               # ZIP, hash, text tools
│
├── services/                    # Business logic (actual processing)
│   ├── __init__.py
│   ├── pdf_service.py           # All PDF processing functions
│   ├── image_service.py         # All image processing functions
│   ├── convert_service.py       # Format conversion functions
│   ├── ocr_service.py           # OCR processing functions
│   ├── security_service.py      # Encryption/decryption functions
│   ├── generator_service.py     # QR, barcode, invoice generation
│   ├── document_service.py      # Word/Excel/PowerPoint functions
│   └── batch_service.py         # Batch processing functions
│
├── utils/
│   ├── file_handler.py          # Save, validate, cleanup uploaded files
│   ├── rate_limiter.py          # Rate limiting middleware
│   └── cleanup.py               # Scheduled temp file cleanup (cron)
│
├── templates/                   # Templates for generators
│   ├── invoice_default.json
│   ├── resume_modern.json
│   └── certificate_basic.json
│
├── uploads/                     # Temp storage for uploaded files
└── outputs/                     # Temp storage for processed files
```

---

## Dependencies

### requirements.txt

```
# Core
fastapi==0.115.0
uvicorn==0.30.0
python-multipart==0.0.9

# PDF Processing
PyMuPDF==1.24.0
pypdf==4.0.0
reportlab==4.1.0
pdfplumber==0.11.0
pdf2image==1.17.0

# Image Processing
Pillow==10.4.0
rembg==2.0.57

# OCR
pytesseract==0.3.10

# Document Processing
python-docx==1.1.0
openpyxl==3.1.5
python-pptx==0.6.23

# Generators
qrcode==7.4.2
python-barcode==0.15.1

# Utilities
python-dotenv==1.0.0
aiofiles==23.2.1
```

### System Dependencies (install separately)

```bash
# Ubuntu/Debian
sudo apt install tesseract-ocr libreoffice poppler-utils

# macOS
brew install tesseract libreoffice poppler

# Windows
# Download Tesseract from: https://github.com/tesseract-ocr/tesseract
# Download LibreOffice from: https://www.libreoffice.org/download
# Download Poppler from: https://github.com/osber/poppler-windows
```

---

## API Endpoints

### Request Format

All endpoints accept `multipart/form-data` for file uploads.

```bash
# Single file upload
curl -X POST http://localhost:8000/api/compress \
  -F "file=@document.pdf"

# Multiple file upload
curl -X POST http://localhost:8000/api/merge \
  -F "files=@file1.pdf" \
  -F "files=@file2.pdf"

# File upload with options
curl -X POST http://localhost:8000/api/rotate \
  -F "file=@document.pdf" \
  -F "angle=90" \
  -F "pages=1,3,5"
```

### Response Format

**File download:**

```
HTTP 200
Content-Type: application/pdf
Content-Disposition: attachment; filename="output.pdf"
```

**Multiple files (ZIP):**

```
HTTP 200
Content-Type: application/zip
Content-Disposition: attachment; filename="output.zip"
```

**JSON response (info endpoints):**

```json
{
  "status": "success",
  "data": { ... }
}
```

**Error response:**

```json
{
   "detail": "File must be a PDF"
}
```

---

### PDF Tools

| Method | Endpoint             | Description                               | Input                                           | Output                       |
| ------ | -------------------- | ----------------------------------------- | ----------------------------------------------- | ---------------------------- |
| POST   | `/api/merge`         | Merge multiple PDFs into one              | Multiple PDF files                              | Single PDF                   |
| POST   | `/api/split`         | Split PDF into individual pages           | Single PDF                                      | ZIP of PDFs                  |
| POST   | `/api/split-range`   | Split by page ranges (e.g., 1-3, 5, 7-10) | PDF + ranges string                             | ZIP of PDFs                  |
| POST   | `/api/compress`      | Compress PDF to reduce size               | PDF + quality level                             | Compressed PDF               |
| POST   | `/api/rotate`        | Rotate pages by 90/180/270 degrees        | PDF + angle + page selection                    | Rotated PDF                  |
| POST   | `/api/delete-pages`  | Remove specific pages                     | PDF + page numbers                              | Modified PDF                 |
| POST   | `/api/reorder`       | Rearrange page order                      | PDF + new order array                           | Reordered PDF                |
| POST   | `/api/extract-pages` | Extract specific pages to new PDF         | PDF + page numbers                              | New PDF                      |
| POST   | `/api/page-numbers`  | Add page numbers                          | PDF + position + format + font                  | Numbered PDF                 |
| POST   | `/api/watermark`     | Add text or image watermark               | PDF + watermark text/image + opacity + position | Watermarked PDF              |
| POST   | `/api/header-footer` | Add headers and footers                   | PDF + header text + footer text + font          | Modified PDF                 |
| POST   | `/api/crop`          | Crop pages to region                      | PDF + crop box coordinates                      | Cropped PDF                  |
| POST   | `/api/flatten`       | Flatten form fields and annotations       | PDF                                             | Flattened PDF                |
| POST   | `/api/repair`        | Repair corrupted PDF                      | Corrupted PDF                                   | Repaired PDF                 |
| POST   | `/api/metadata`      | View/edit PDF metadata                    | PDF + new metadata (optional)                   | JSON or modified PDF         |
| POST   | `/api/redact`        | Redact text or areas                      | PDF + redaction targets                         | Redacted PDF                 |
| POST   | `/api/compare`       | Compare two PDFs                          | Two PDF files                                   | Diff report (JSON/PDF)       |
| POST   | `/api/pdf-to-pdfa`   | Convert to PDF/A archival format          | PDF                                             | PDF/A file                   |
| POST   | `/api/bookmarks`     | Add/edit bookmarks                        | PDF + bookmark structure                        | Bookmarked PDF               |
| POST   | `/api/overlay`       | Overlay one PDF on another                | Two PDF files                                   | Combined PDF                 |
| POST   | `/api/fill-form`     | Fill PDF form fields                      | PDF + field values (JSON)                       | Filled PDF                   |
| POST   | `/api/pdf-info`      | Get PDF file information                  | PDF                                             | JSON (pages, size, metadata) |

---

### Conversion Tools

| Method | Endpoint             | Description                | Input                                 | Output        |
| ------ | -------------------- | -------------------------- | ------------------------------------- | ------------- |
| POST   | `/api/pdf-to-word`   | PDF to Word                | PDF                                   | .docx         |
| POST   | `/api/word-to-pdf`   | Word to PDF                | .doc/.docx                            | PDF           |
| POST   | `/api/pdf-to-excel`  | PDF tables to Excel        | PDF                                   | .xlsx         |
| POST   | `/api/excel-to-pdf`  | Excel to PDF               | .xlsx/.xls                            | PDF           |
| POST   | `/api/pdf-to-pptx`   | PDF to PowerPoint          | PDF                                   | .pptx         |
| POST   | `/api/pptx-to-pdf`   | PowerPoint to PDF          | .pptx                                 | PDF           |
| POST   | `/api/pdf-to-image`  | PDF pages to images        | PDF + format (png/jpg) + DPI          | ZIP of images |
| POST   | `/api/image-to-pdf`  | Images to PDF              | Image files + page size + orientation | PDF           |
| POST   | `/api/html-to-pdf`   | HTML/URL to PDF            | HTML string or URL                    | PDF           |
| POST   | `/api/pdf-to-html`   | PDF to HTML                | PDF                                   | .html         |
| POST   | `/api/md-to-pdf`     | Markdown to PDF            | .md file or text                      | PDF           |
| POST   | `/api/csv-to-pdf`    | CSV to formatted PDF table | .csv                                  | PDF           |
| POST   | `/api/csv-to-excel`  | CSV to Excel               | .csv                                  | .xlsx         |
| POST   | `/api/excel-to-csv`  | Excel to CSV               | .xlsx                                 | .csv          |
| POST   | `/api/text-to-pdf`   | Plain text to PDF          | .txt + font options                   | PDF           |
| POST   | `/api/svg-convert`   | SVG to PNG or PDF          | .svg + target format                  | PNG or PDF    |
| POST   | `/api/epub-to-pdf`   | EPUB to PDF                | .epub                                 | PDF           |
| POST   | `/api/json-to-table` | JSON to CSV or Excel       | .json + target format                 | .csv or .xlsx |

---

### Image Tools

| Method | Endpoint               | Description               | Input                                   | Output                       |
| ------ | ---------------------- | ------------------------- | --------------------------------------- | ---------------------------- |
| POST   | `/api/compress-image`  | Compress image            | Image + quality (1-100)                 | Compressed image             |
| POST   | `/api/resize-image`    | Resize image              | Image + width + height + maintain ratio | Resized image                |
| POST   | `/api/crop-image`      | Crop image                | Image + x + y + width + height          | Cropped image                |
| POST   | `/api/rotate-image`    | Rotate/flip image         | Image + angle + flip direction          | Rotated image                |
| POST   | `/api/convert-image`   | Convert image format      | Image + target format                   | Converted image              |
| POST   | `/api/remove-bg`       | Remove background         | Image                                   | PNG with transparency        |
| POST   | `/api/image-watermark` | Add watermark to image    | Image + watermark text/image + opacity  | Watermarked image            |
| POST   | `/api/image-to-base64` | Image to Base64 string    | Image                                   | JSON with Base64 string      |
| POST   | `/api/base64-to-image` | Base64 to image           | JSON with Base64 string                 | Image file                   |
| POST   | `/api/exif-viewer`     | View EXIF metadata        | Image                                   | JSON with EXIF data          |
| POST   | `/api/exif-remover`    | Remove EXIF metadata      | Image                                   | Clean image                  |
| POST   | `/api/bulk-resize`     | Resize multiple images    | Multiple images + dimensions            | ZIP of resized images        |
| POST   | `/api/color-picker`    | Extract colors from image | Image                                   | JSON with HEX/RGB/HSL values |
| POST   | `/api/image-filter`    | Apply filters             | Image + filter type                     | Filtered image               |

---

### OCR Tools

| Method | Endpoint               | Description                   | Input                     | Output                            |
| ------ | ---------------------- | ----------------------------- | ------------------------- | --------------------------------- |
| POST   | `/api/ocr-image`       | Extract text from image       | Image                     | JSON with extracted text          |
| POST   | `/api/ocr-pdf`         | Scanned PDF to searchable PDF | Scanned PDF               | Searchable PDF                    |
| POST   | `/api/ocr-multilang`   | OCR with language selection   | Image/PDF + language code | Text/searchable PDF               |
| POST   | `/api/ocr-table`       | Extract tables from scans     | Image/PDF                 | .csv or .xlsx                     |
| POST   | `/api/ocr-handwriting` | Handwriting to text           | Image                     | JSON with text                    |
| POST   | `/api/ocr-receipt`     | Extract receipt data          | Receipt image             | JSON (vendor, date, total, items) |

---

### Security Tools

| Method | Endpoint               | Description                | Input                                | Output        |
| ------ | ---------------------- | -------------------------- | ------------------------------------ | ------------- |
| POST   | `/api/encrypt-pdf`     | Add password protection    | PDF + user password + owner password | Encrypted PDF |
| POST   | `/api/decrypt-pdf`     | Remove password            | PDF + password                       | Decrypted PDF |
| POST   | `/api/pdf-permissions` | Set permissions            | PDF + permission flags               | Protected PDF |
| POST   | `/api/auto-redact`     | Auto-detect and redact PII | PDF + patterns (email/phone/ssn)     | Redacted PDF  |
| POST   | `/api/sanitize-pdf`    | Remove hidden data         | PDF                                  | Sanitized PDF |

---

### Signature & Stamp Tools

| Method | Endpoint             | Description             | Input                                    | Output               |
| ------ | -------------------- | ----------------------- | ---------------------------------------- | -------------------- |
| POST   | `/api/add-signature` | Place signature on PDF  | PDF + signature image + position         | Signed PDF           |
| POST   | `/api/add-stamp`     | Add text stamp          | PDF + stamp type/text + position + color | Stamped PDF          |
| POST   | `/api/date-stamp`    | Add date stamp          | PDF + date format + position             | Stamped PDF          |
| POST   | `/api/digital-sign`  | Cryptographic signature | PDF + .p12 certificate + password        | Digitally signed PDF |

---

### Document Tools

| Method | Endpoint                 | Description               | Input                       | Output             |
| ------ | ------------------------ | ------------------------- | --------------------------- | ------------------ |
| POST   | `/api/create-docx`       | Create Word document      | JSON with content structure | .docx              |
| POST   | `/api/find-replace-docx` | Find and replace in Word  | .docx + search + replace    | Modified .docx     |
| POST   | `/api/docx-to-md`        | Word to Markdown          | .docx                       | .md                |
| POST   | `/api/merge-docx`        | Merge Word documents      | Multiple .docx files        | Single .docx       |
| POST   | `/api/compare-docx`      | Compare two Word files    | Two .docx files             | Diff report        |
| POST   | `/api/extract-text`      | Extract text from any doc | PDF/.docx/.pptx             | JSON with text     |
| POST   | `/api/mail-merge`        | Template + data merge     | .docx template + .csv data  | ZIP of .docx files |
| POST   | `/api/merge-pptx`        | Merge presentations       | Multiple .pptx files        | Single .pptx       |
| POST   | `/api/pptx-to-images`    | Slides to images          | .pptx                       | ZIP of images      |
| POST   | `/api/extract-notes`     | Extract slide notes       | .pptx                       | JSON with notes    |
| POST   | `/api/images-to-pptx`    | Images to presentation    | Multiple images             | .pptx              |
| POST   | `/api/merge-excel`       | Merge Excel files         | Multiple .xlsx files        | Single .xlsx       |
| POST   | `/api/split-excel`       | Split sheets to files     | .xlsx                       | ZIP of .xlsx files |
| POST   | `/api/clean-excel`       | Clean spreadsheet data    | .xlsx                       | Cleaned .xlsx      |
| POST   | `/api/json-to-excel`     | JSON to Excel             | .json                       | .xlsx              |
| POST   | `/api/excel-to-json`     | Excel to JSON             | .xlsx                       | .json              |

---

### Generator Tools

| Method | Endpoint                    | Description               | Input                                     | Output                   |
| ------ | --------------------------- | ------------------------- | ----------------------------------------- | ------------------------ |
| POST   | `/api/generate-qr`          | Generate QR code          | Text/URL + size + color + format          | PNG/SVG/PDF              |
| POST   | `/api/generate-barcode`     | Generate barcode          | Data + barcode type                       | PNG/SVG                  |
| POST   | `/api/generate-invoice`     | Generate PDF invoice      | JSON (company, client, items, tax)        | PDF invoice              |
| POST   | `/api/generate-resume`      | Generate PDF resume       | JSON (name, experience, skills)           | PDF resume               |
| POST   | `/api/generate-certificate` | Generate certificate      | JSON (name, title, date)                  | PDF certificate          |
| POST   | `/api/color-convert`        | Convert color values      | Color value + source format               | JSON with all formats    |
| POST   | `/api/lorem-ipsum`          | Generate placeholder text | Count + type (words/sentences/paragraphs) | JSON with text           |
| POST   | `/api/file-hash`            | Calculate file hash       | Any file                                  | JSON (MD5, SHA1, SHA256) |

---

### Utility Tools

| Method | Endpoint            | Description        | Input                 | Output                         |
| ------ | ------------------- | ------------------ | --------------------- | ------------------------------ |
| POST   | `/api/create-zip`   | Create ZIP archive | Multiple files        | .zip                           |
| POST   | `/api/extract-zip`  | Extract archive    | .zip/.rar/.7z/.tar.gz | ZIP of extracted files         |
| POST   | `/api/file-size`    | Get file size info | Any file              | JSON (bytes, KB, MB)           |
| POST   | `/api/text-diff`    | Compare two texts  | Two text strings      | JSON with differences          |
| POST   | `/api/word-counter` | Count words/chars  | Text or document      | JSON (words, chars, sentences) |
| POST   | `/api/case-convert` | Convert text case  | Text + target case    | JSON with converted text       |

---

### Batch Tools

| Method | Endpoint               | Description              | Input                             | Output                   |
| ------ | ---------------------- | ------------------------ | --------------------------------- | ------------------------ |
| POST   | `/api/batch-convert`   | Convert multiple files   | Multiple files + target format    | ZIP of converted files   |
| POST   | `/api/batch-compress`  | Compress multiple files  | Multiple PDFs/images              | ZIP of compressed files  |
| POST   | `/api/batch-rename`    | Rename multiple files    | Multiple files + naming pattern   | ZIP of renamed files     |
| POST   | `/api/batch-watermark` | Watermark multiple files | Multiple files + watermark config | ZIP of watermarked files |

---

### System Endpoints

| Method | Endpoint                 | Description                                |
| ------ | ------------------------ | ------------------------------------------ |
| GET    | `/`                      | Health check — returns API status          |
| GET    | `/api/health`            | Detailed health check                      |
| GET    | `/api/supported-formats` | List all supported file formats            |
| GET    | `/api/tools`             | List all available tools with descriptions |
| GET    | `/docs`                  | Interactive Swagger UI (auto-generated)    |
| GET    | `/redoc`                 | Alternative API documentation              |

---

## Configuration

### Environment Variables (.env)

```env
# Server
HOST=0.0.0.0
PORT=8000
DEBUG=true
ALLOWED_ORIGINS=http://localhost:3000,https://yourdomain.com

# File Limits
MAX_FILE_SIZE_MB=50
MAX_FILES_PER_REQUEST=20
TEMP_FILE_RETENTION_MINUTES=60

# Paths
UPLOAD_DIR=./uploads
OUTPUT_DIR=./outputs

# Rate Limiting
RATE_LIMIT_PER_MINUTE=30
RATE_LIMIT_PER_HOUR=200

# OCR
TESSERACT_PATH=/usr/bin/tesseract
TESSERACT_LANG=eng

# LibreOffice
LIBREOFFICE_PATH=/usr/bin/libreoffice

# Redis (optional — for task queue)
REDIS_URL=redis://localhost:6379/0

# S3 Storage (optional — for production)
S3_BUCKET=
S3_REGION=
S3_ACCESS_KEY=
S3_SECRET_KEY=
```

---

## File Handling

### Upload Flow

```
1. Client sends file via multipart/form-data
2. Server validates file type and size
3. File saved to uploads/{job_id}/ with unique ID
4. Service processes the file
5. Result saved to outputs/{job_id}/
6. Response sent with file download
7. Cleanup: uploads/ deleted immediately, outputs/ deleted after 1 hour
```

### File Size Limits

| Tier     | Max File Size | Max Files Per Request |
| -------- | ------------- | --------------------- |
| Free     | 15 MB         | 5                     |
| Pro      | 500 MB        | 50                    |
| Business | 2 GB          | 100                   |

### Supported Input Formats

| Category      | Formats                                                 |
| ------------- | ------------------------------------------------------- |
| PDF           | .pdf                                                    |
| Documents     | .doc, .docx, .odt, .rtf, .txt                           |
| Spreadsheets  | .xls, .xlsx, .csv, .tsv, .ods                           |
| Presentations | .ppt, .pptx, .odp                                       |
| Images        | .png, .jpg, .jpeg, .gif, .bmp, .tiff, .webp, .svg, .ico |
| eBooks        | .epub                                                   |
| Archives      | .zip, .rar, .7z, .tar, .tar.gz                          |
| Data          | .json, .xml                                             |
| Web           | .html, .htm                                             |
| Markdown      | .md                                                     |

---

## Error Handling

All errors return consistent JSON:

```json
{
   "detail": "Human-readable error message"
}
```

### Error Codes

| HTTP Code | Meaning          | Example                                                |
| --------- | ---------------- | ------------------------------------------------------ |
| 400       | Bad request      | "File must be a PDF", "Need at least 2 files to merge" |
| 413       | File too large   | "File exceeds 50MB limit"                              |
| 415       | Unsupported type | "Unsupported file format: .exe"                        |
| 422       | Validation error | "Invalid page range: 5-3"                              |
| 429       | Rate limited     | "Rate limit exceeded. Try again in 60 seconds."        |
| 500       | Server error     | "Processing failed: corrupted file"                    |

---

## Adding a New Tool

Follow this pattern every time:

### Step 1 — Add the processing function in services/

```python
# services/pdf_service.py

def new_tool_function(file_path: str, output_path: str, options: dict) -> dict:
    """Description of what this tool does."""
    pdf = fitz.open(file_path)
    # ... do the processing ...
    pdf.save(output_path)
    pdf.close()
    return {"output_path": output_path, "pages": len(pdf)}
```

### Step 2 — Create the router in routers/

```python
# routers/new_tool.py

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from services.pdf_service import new_tool_function
import os, uuid, shutil

router = APIRouter()

@router.post("/new-tool")
async def new_tool(file: UploadFile = File(...)):
    job_id = str(uuid.uuid4())
    job_dir = os.path.join("uploads", job_id)
    os.makedirs(job_dir, exist_ok=True)

    try:
        input_path = os.path.join(job_dir, "input.pdf")
        with open(input_path, "wb") as f:
            f.write(await file.read())

        output_path = os.path.join("outputs", f"result_{job_id}.pdf")
        result = new_tool_function(input_path, output_path, {})

        return FileResponse(path=output_path, filename="result.pdf")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        shutil.rmtree(job_dir, ignore_errors=True)
```

### Step 3 — Register in main.py

```python
from routers import new_tool

app.include_router(new_tool.router, prefix="/api", tags=["New Tool"])
```

### Step 4 — Test it

```bash
# Restart server (happens automatically with --reload)
# Go to http://localhost:8000/docs
# Find your new endpoint and test with a real file
```

---

## Testing

### Manual Testing (Swagger UI)

Visit `http://localhost:8000/docs` — click any endpoint, upload a file, and execute.

### cURL Testing

```bash
# Health check
curl http://localhost:8000/

# Merge
curl -X POST http://localhost:8000/api/merge \
  -F "files=@file1.pdf" -F "files=@file2.pdf" \
  --output merged.pdf

# Split
curl -X POST http://localhost:8000/api/split \
  -F "file=@document.pdf" \
  --output pages.zip

# Compress
curl -X POST http://localhost:8000/api/compress \
  -F "file=@large.pdf" \
  --output compressed.pdf

# Rotate
curl -X POST http://localhost:8000/api/rotate \
  -F "file=@document.pdf" -F "angle=90" \
  --output rotated.pdf

# Convert PDF to images
curl -X POST http://localhost:8000/api/pdf-to-image \
  -F "file=@document.pdf" -F "format=png" -F "dpi=300" \
  --output pages.zip

# OCR
curl -X POST http://localhost:8000/api/ocr-image \
  -F "file=@scanned.png"

# Encrypt
curl -X POST http://localhost:8000/api/encrypt-pdf \
  -F "file=@document.pdf" -F "password=secret123" \
  --output encrypted.pdf

# Generate QR Code
curl -X POST http://localhost:8000/api/generate-qr \
  -F "data=https://example.com" -F "size=300" \
  --output qrcode.png
```

### Automated Testing (pytest)

```bash
pip install pytest httpx
pytest tests/ -v
```

---

## Deployment

### Docker

```dockerfile
FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    libreoffice \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

```bash
docker build -t docforge-backend .
docker run -p 8000:8000 docforge-backend
```

### Production (Gunicorn + Uvicorn)

```bash
pip install gunicorn
gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

---

## Connecting to Frontend

Your Next.js (or any) frontend calls these endpoints like this:

```javascript
// Upload and process a file
const formData = new FormData();
formData.append("file", selectedFile);

const response = await fetch("http://localhost:8000/api/compress", {
   method: "POST",
   body: formData,
});

// Download the result
const blob = await response.blob();
const url = URL.createObjectURL(blob);
const link = document.createElement("a");
link.href = url;
link.download = "compressed.pdf";
link.click();
```

```javascript
// Upload multiple files
const formData = new FormData();
files.forEach((file) => formData.append("files", file));

const response = await fetch("http://localhost:8000/api/merge", {
   method: "POST",
   body: formData,
});
```

---

## Total Tool Count: 102

| Category                | Count   |
| ----------------------- | ------- |
| PDF Tools               | 22      |
| Conversion Tools        | 18      |
| Image Tools             | 14      |
| OCR Tools               | 6       |
| Security Tools          | 5       |
| Signature & Stamp Tools | 4       |
| Document Tools          | 16      |
| Generator Tools         | 8       |
| Utility Tools           | 6       |
| Batch Tools             | 4       |
| **Total**               | **102** |

---

## License

MIT
