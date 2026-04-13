import weasyprint
try:
    print("Testing weasyprint...")
    weasyprint.HTML(string="<h1>Test</h1>").write_pdf("test.pdf")
    print("weasyprint success")
except Exception as e:
    print(f"weasyprint error: {e}")

try:
    print("Testing cairosvg...")
    import cairosvg
    svg = '<svg height="100" width="100"><circle cx="50" cy="50" r="40" stroke="black" stroke-width="3" fill="red" /></svg>'
    cairosvg.svg2png(bytestring=svg.encode('utf-8'), write_to="test.png")
    print("cairosvg success")
except Exception as e:
    print(f"cairosvg error: {e}")
