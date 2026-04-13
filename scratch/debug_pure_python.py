import xhtml2pdf.pisa as pisa
import io

try:
    print("Testing xhtml2pdf...")
    buf = io.BytesIO()
    html = "<h1>Test</h1>"
    pisa_status = pisa.CreatePDF(html, dest=buf)
    if pisa_status.err:
        print(f"xhtml2pdf error status: {pisa_status.err}")
    else:
        print("xhtml2pdf success")
except Exception as e:
    print(f"xhtml2pdf exception: {e}")

try:
    print("Testing svglib...")
    from svglib.svglib import svg2rlg
    from reportlab.graphics import renderPM
    svg_data = '<svg height="100" width="100"><circle cx="50" cy="50" r="40" stroke="black" stroke-width="3" fill="red" /></svg>'
    with open("test.svg", "w") as f:
        f.write(svg_data)
    drawing = svg2rlg("test.svg")
    renderPM.drawToFile(drawing, "test.png", fmt="PNG")
    print("svglib success")
except Exception as e:
    print(f"svglib error: {e}")
