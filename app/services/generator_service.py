"""Generator service — QR codes, barcodes, invoices, resumes, certificates."""
import io
import json
import os
from pathlib import Path


def generate_qr_code(data: str, output_path: str, size: int = 300, fill_color: str = "black", back_color: str = "white") -> None:
    import qrcode
    qr = qrcode.QRCode(box_size=10, border=4)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color=fill_color, back_color=back_color)
    img = img.resize((size, size))
    img.save(output_path)


def generate_barcode(data: str, output_path: str, barcode_type: str = "code128") -> None:
    import barcode as bc
    from barcode.writer import ImageWriter
    try:
        barcode_cls = bc.get_barcode_class(barcode_type)
    except Exception:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=f"Unknown barcode type: {barcode_type}")
    bar = barcode_cls(data, writer=ImageWriter())
    stem = str(Path(output_path).with_suffix(""))
    bar.save(stem)


def generate_invoice(data: dict, output_path: str) -> None:
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet

    doc = SimpleDocTemplate(output_path, pagesize=A4)
    styles = getSampleStyleSheet()
    story = []

    company = data.get("company", {})
    client = data.get("client", {})
    items = data.get("items", [])
    tax_rate = data.get("tax_rate", 0)

    story.append(Paragraph(company.get("name", "Company Name"), styles["Title"]))
    story.append(Paragraph(f"Invoice to: {client.get('name', '')}", styles["Normal"]))
    story.append(Spacer(1, 20))

    table_data = [["Description", "Qty", "Unit Price", "Total"]]
    subtotal = 0
    for item in items:
        qty = item.get("qty", 1)
        price = item.get("price", 0)
        total = qty * price
        subtotal += total
        table_data.append([item.get("description", ""), str(qty), f"${price:.2f}", f"${total:.2f}"])

    tax = subtotal * tax_rate / 100
    table_data.append(["", "", "Subtotal", f"${subtotal:.2f}"])
    table_data.append(["", "", f"Tax ({tax_rate}%)", f"${tax:.2f}"])
    table_data.append(["", "", "Total", f"${subtotal + tax:.2f}"])

    table = Table(table_data, colWidths=[250, 50, 100, 100])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2563EB")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
        ("FONTNAME", (-2, -3), (-1, -1), "Helvetica-Bold"),
    ]))
    story.append(table)
    doc.build(story)


def generate_resume(data: dict, output_path: str) -> None:
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER

    doc = SimpleDocTemplate(output_path, pagesize=A4)
    styles = getSampleStyleSheet()
    center = ParagraphStyle("center", parent=styles["Normal"], alignment=TA_CENTER)
    story = []

    story.append(Paragraph(data.get("name", "Your Name"), styles["Title"]))
    story.append(Paragraph(data.get("email", ""), center))
    story.append(Paragraph(data.get("phone", ""), center))
    story.append(Spacer(1, 12))

    for section, items in [
        ("Experience", data.get("experience", [])),
        ("Education", data.get("education", [])),
        ("Skills", data.get("skills", [])),
    ]:
        story.append(Paragraph(section, styles["Heading2"]))
        for item in items:
            if isinstance(item, dict):
                story.append(Paragraph(f"<b>{item.get('title', '')}</b> — {item.get('company', item.get('school', ''))}", styles["Normal"]))
                story.append(Paragraph(item.get("description", ""), styles["Normal"]))
            else:
                story.append(Paragraph(str(item), styles["Normal"]))
        story.append(Spacer(1, 8))

    doc.build(story)


def generate_certificate(data: dict, output_path: str) -> None:
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib import colors

    doc = SimpleDocTemplate(output_path, pagesize=landscape(A4))
    styles = getSampleStyleSheet()
    center = ParagraphStyle("center", parent=styles["Normal"], alignment=TA_CENTER, fontSize=14)
    title_style = ParagraphStyle("title", parent=styles["Title"], alignment=TA_CENTER, fontSize=36)

    story = [
        Spacer(1, 60),
        Paragraph("Certificate of Achievement", title_style),
        Spacer(1, 30),
        Paragraph("This is to certify that", center),
        Spacer(1, 10),
        Paragraph(f"<b>{data.get('name', '')}</b>", ParagraphStyle("name", alignment=TA_CENTER, fontSize=28)),
        Spacer(1, 10),
        Paragraph(data.get("title", ""), center),
        Spacer(1, 20),
        Paragraph(f"Date: {data.get('date', '')}", center),
    ]
    doc.build(story)


def convert_color(value: str, source_format: str) -> dict:
    """Convert between HEX, RGB, and HSL."""
    if source_format == "hex":
        value = value.lstrip("#")
        r, g, b = int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)
    elif source_format == "rgb":
        parts = value.split(",")
        r, g, b = int(parts[0]), int(parts[1]), int(parts[2])
    else:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="source_format must be 'hex' or 'rgb'")

    hex_val = f"#{r:02x}{g:02x}{b:02x}"
    r_, g_, b_ = r / 255, g / 255, b / 255
    cmax, cmin = max(r_, g_, b_), min(r_, g_, b_)
    delta = cmax - cmin
    l = (cmax + cmin) / 2
    s = 0 if delta == 0 else delta / (1 - abs(2 * l - 1))
    h = 0
    if delta:
        if cmax == r_:
            h = 60 * (((g_ - b_) / delta) % 6)
        elif cmax == g_:
            h = 60 * ((b_ - r_) / delta + 2)
        else:
            h = 60 * ((r_ - g_) / delta + 4)
    return {
        "hex": hex_val,
        "rgb": {"r": r, "g": g, "b": b},
        "hsl": {"h": round(h), "s": round(s * 100), "l": round(l * 100)},
    }


def generate_lorem_ipsum(count: int = 5, unit: str = "sentences") -> str:
    word_pool = (
        "lorem ipsum dolor sit amet consectetur adipiscing elit sed do eiusmod tempor "
        "incididunt ut labore et dolore magna aliqua enim ad minim veniam quis nostrud "
        "exercitation ullamco laboris nisi aliquip ex ea commodo consequat"
    ).split()
    import random
    words = word_pool[:]
    if unit == "words":
        return " ".join(random.choices(words, k=count))
    sentences = []
    for _ in range(count):
        n = random.randint(8, 16)
        s = " ".join(random.choices(words, k=n))
        sentences.append(s.capitalize() + ".")
    if unit == "sentences":
        return " ".join(sentences)
    paragraphs = []
    for _ in range(count):
        n = random.randint(3, 6)
        p = " ".join(
            " ".join(random.choices(words, k=random.randint(8, 16))).capitalize() + "."
            for _ in range(n)
        )
        paragraphs.append(p)
    return "\n\n".join(paragraphs)


# ---------------------------------------------------------------------------
# Favicon generator
# ---------------------------------------------------------------------------

_FAVICON_SIZES = [16, 32, 48, 64, 128, 180, 192, 512]
_ICO_SIZES = [(16, 16), (32, 32), (48, 48)]

# Font search paths (tried in order)
_FONT_PATHS = [
    "C:/Windows/Fonts/segoeui.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/verdana.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/Library/Fonts/Arial.ttf",
]


def _get_font(size: int):
    from PIL import ImageFont
    for path in _FONT_PATHS:
        try:
            return ImageFont.truetype(path, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def _hex_to_rgba(hex_color: str, alpha: int = 255) -> tuple:
    hex_color = hex_color.lstrip("#")
    if len(hex_color) == 3:
        hex_color = "".join(c * 2 for c in hex_color)
    r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    return (r, g, b, alpha)


def _draw_background(draw, size: int, bg_rgba: tuple, shape: str) -> None:
    from PIL import ImageDraw
    if shape == "circle":
        draw.ellipse([0, 0, size, size], fill=bg_rgba)
    elif shape == "rounded":
        radius = size // 5
        draw.rounded_rectangle([0, 0, size, size], radius=radius, fill=bg_rgba)
    else:
        draw.rectangle([0, 0, size, size], fill=bg_rgba)


def _save_favicon_pack(base_img, output_dir: str) -> list[str]:
    """Resize base_img to all favicon sizes and save PNG + ICO."""
    from PIL import Image
    paths = []

    # Individual PNGs
    for sz in _FAVICON_SIZES:
        resized = base_img.resize((sz, sz), Image.LANCZOS)
        path = os.path.join(output_dir, f"favicon-{sz}x{sz}.png")
        resized.save(path, "PNG")
        paths.append(path)

    # Multi-size ICO
    ico_path = os.path.join(output_dir, "favicon.ico")
    base_img.save(ico_path, format="ICO", sizes=_ICO_SIZES)
    paths.insert(0, ico_path)

    # web.manifest snippet
    manifest = {
        "icons": [
            {"src": f"favicon-{sz}x{sz}.png", "sizes": f"{sz}x{sz}", "type": "image/png"}
            for sz in _FAVICON_SIZES
        ]
    }
    manifest_path = os.path.join(output_dir, "site.webmanifest")
    with open(manifest_path, "w") as f:
        import json as _json
        _json.dump(manifest, f, indent=2)
    paths.append(manifest_path)

    return paths


def generate_favicon_from_text(
    text: str,
    bg_color: str = "#4F46E5",
    text_color: str = "#FFFFFF",
    shape: str = "square",
    output_dir: str = ".",
) -> list[str]:
    """Generate favicon pack from text or emoji.

    Args:
        text:       1–3 characters or an emoji shown on the icon
        bg_color:   background hex color, e.g. "#4F46E5"
        text_color: foreground hex color, e.g. "#FFFFFF"
        shape:      "square" | "circle" | "rounded"
        output_dir: directory to write files into

    Returns:
        List of file paths (favicon.ico, favicon-NxN.png …, site.webmanifest)
    """
    from PIL import Image, ImageDraw

    BASE = 512
    img = Image.new("RGBA", (BASE, BASE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    bg_rgba = _hex_to_rgba(bg_color)
    fg_rgba = _hex_to_rgba(text_color)
    _draw_background(draw, BASE, bg_rgba, shape)

    # Auto-scale font to fit ~55 % of the canvas
    font_size = int(BASE * 0.55)
    font = _get_font(font_size)
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (BASE - tw) // 2 - bbox[0]
    y = (BASE - th) // 2 - bbox[1]
    draw.text((x, y), text, fill=fg_rgba, font=font)

    return _save_favicon_pack(img, output_dir)


def generate_favicon_from_image(input_path: str, output_dir: str) -> list[str]:
    """Generate favicon pack from an uploaded image.

    The image is center-cropped to a square before resizing.
    """
    from PIL import Image

    img = Image.open(input_path).convert("RGBA")
    w, h = img.size
    sq = min(w, h)
    left = (w - sq) // 2
    top = (h - sq) // 2
    img = img.crop((left, top, left + sq, top + sq))

    return _save_favicon_pack(img, output_dir)


def compute_file_hash(input_path: str) -> dict:
    import hashlib
    md5 = hashlib.md5()
    sha1 = hashlib.sha1()
    sha256 = hashlib.sha256()
    with open(input_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            md5.update(chunk)
            sha1.update(chunk)
            sha256.update(chunk)
    return {
        "md5": md5.hexdigest(),
        "sha1": sha1.hexdigest(),
        "sha256": sha256.hexdigest(),
        "file_size_bytes": os.path.getsize(input_path),
    }
