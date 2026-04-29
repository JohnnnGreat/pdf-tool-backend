use anyhow::{Context, Result};
use image::ImageFormat;
use pdfium_auto::bind_pdfium_silent;
use pdfium_render::prelude::*;
use pyo3::create_exception;
use pyo3::exceptions::PyException;
use pyo3::prelude::*;
use std::fs::{self, File};
use std::io::{Cursor, Write};
use std::path::Path;
use thiserror::Error;
use zip::write::FileOptions;
use zip::CompressionMethod;
use zip::ZipWriter;

create_exception!(_rust_converter, RustConversionError, PyException);
create_exception!(_rust_converter, InvalidPdfError, RustConversionError);
create_exception!(
    _rust_converter,
    UnsupportedScannedPdfError,
    RustConversionError
);
create_exception!(_rust_converter, DocxGenerationError, RustConversionError);

#[derive(Debug, Error)]
enum ConverterError {
    #[error("Invalid PDF: {0}")]
    InvalidPdf(String),
    #[error("Unsupported scanned PDF: {0}")]
    UnsupportedScannedPdf(String),
    #[error("DOCX generation failed: {0}")]
    DocxGeneration(String),
    #[error("Conversion failed: {0}")]
    Conversion(String),
    #[error("Output file was not created at {0}")]
    MissingOutput(String),
}

#[derive(Debug, Clone)]
struct PageReplica {
    width_pt: f32,
    height_pt: f32,
    background_png: Vec<u8>,
    text_boxes: Vec<TextBox>,
}

#[derive(Debug, Clone)]
struct TextBox {
    text: String,
    x_pt: f32,
    y_pt: f32,
    width_pt: f32,
    height_pt: f32,
    font_family: String,
    font_size_pt: f32,
    bold: bool,
    italic: bool,
    color_hex: String,
    rotation_deg: f32,
}

#[pyfunction]
fn convert_pdf_to_docx(input_path: &str, output_path: &str) -> PyResult<bool> {
    match convert_pdf_to_docx_impl(Path::new(input_path), Path::new(output_path)) {
        Ok(()) => Ok(true),
        Err(ConverterError::InvalidPdf(message)) => Err(InvalidPdfError::new_err(message)),
        Err(ConverterError::UnsupportedScannedPdf(message)) => {
            Err(UnsupportedScannedPdfError::new_err(message))
        }
        Err(ConverterError::DocxGeneration(message)) => Err(DocxGenerationError::new_err(message)),
        Err(ConverterError::MissingOutput(message)) => Err(DocxGenerationError::new_err(message)),
        Err(ConverterError::Conversion(message)) => Err(RustConversionError::new_err(message)),
    }
}

#[pymodule]
fn _rust_converter(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add(
        "RustConversionError",
        module.py().get_type::<RustConversionError>(),
    )?;
    module.add("InvalidPdfError", module.py().get_type::<InvalidPdfError>())?;
    module.add(
        "UnsupportedScannedPdfError",
        module.py().get_type::<UnsupportedScannedPdfError>(),
    )?;
    module.add(
        "DocxGenerationError",
        module.py().get_type::<DocxGenerationError>(),
    )?;
    module.add_function(wrap_pyfunction!(convert_pdf_to_docx, module)?)?;
    Ok(())
}

fn convert_pdf_to_docx_impl(
    input_path: &Path,
    output_path: &Path,
) -> std::result::Result<(), ConverterError> {
    if !input_path.exists() {
        return Err(ConverterError::InvalidPdf(format!(
            "Input PDF does not exist: {}",
            input_path.display()
        )));
    }

    if let Some(parent) = output_path.parent() {
        fs::create_dir_all(parent).map_err(|err| {
            ConverterError::DocxGeneration(format!(
                "Unable to create output directory {}: {err}",
                parent.display()
            ))
        })?;
    }

    let pdfium = bind_pdfium_silent()
        .map_err(|err| ConverterError::Conversion(format!("Unable to initialize PDFium: {err}")))?;

    let document = pdfium
        .load_pdf_from_file(input_path, None)
        .map_err(|err| ConverterError::InvalidPdf(err.to_string()))?;

    let replicas = extract_pages(&document).map_err(|err| match err {
        ConverterError::UnsupportedScannedPdf(message) => {
            ConverterError::UnsupportedScannedPdf(message)
        }
        ConverterError::InvalidPdf(message) => ConverterError::InvalidPdf(message),
        ConverterError::DocxGeneration(message) => ConverterError::DocxGeneration(message),
        ConverterError::MissingOutput(message) => ConverterError::MissingOutput(message),
        ConverterError::Conversion(message) => ConverterError::Conversion(message),
    })?;

    write_docx(output_path, &replicas)?;

    if !output_path.exists() {
        return Err(ConverterError::MissingOutput(
            output_path.display().to_string(),
        ));
    }

    Ok(())
}

fn extract_pages(
    document: &PdfDocument<'_>,
) -> std::result::Result<Vec<PageReplica>, ConverterError> {
    let mut replicas = Vec::new();
    let mut total_text_boxes = 0usize;

    for page in document.pages().iter() {
        let background_png = render_page_background(&page).map_err(|err| {
            ConverterError::Conversion(format!("Failed to render page background: {err}"))
        })?;

        let page_height_pt = page.height().value;
        let text_page = page
            .text()
            .map_err(|err| ConverterError::InvalidPdf(err.to_string()))?;

        let mut text_boxes = Vec::new();

        for object in page.objects().iter() {
            let Some(text_object) = object.as_text_object() else {
                continue;
            };

            let raw_text = text_page.for_object(&text_object);
            let text = normalize_text(&raw_text);

            if text.is_empty() {
                continue;
            }

            let bounds = text_object.bounds().map_err(|err| {
                ConverterError::Conversion(format!("Failed to read text bounds: {err}"))
            })?;

            let font = text_object.font();
            let font_family = sanitize_font_family(&font.family());
            let font_hint = format!("{} {}", font.name(), font.family()).to_lowercase();
            let chars = text_page.chars_for_object(&text_object).ok();
            let first_char = chars
                .as_ref()
                .and_then(|collection| collection.iter().next());
            let color_hex = first_char
                .as_ref()
                .and_then(|ch| ch.fill_color().ok())
                .map(|color| color.to_hex())
                .unwrap_or_else(|| "000000".to_string());

            let rotation_deg = text_object.get_rotation_clockwise_degrees().abs();

            let font_size_pt = text_object.scaled_font_size().value.max(6.0);
            let bold = font_hint.contains("bold");
            let italic = font_hint.contains("italic") || font_hint.contains("oblique");

            let width_pt = bounds.width().value.max(8.0);
            let height_pt = bounds.height().value.max(font_size_pt + 2.0);
            let x_pt = bounds.left().value.max(0.0);
            let y_pt = (page_height_pt - bounds.top().value).max(0.0);

            text_boxes.push(TextBox {
                text,
                x_pt,
                y_pt,
                width_pt,
                height_pt,
                font_family,
                font_size_pt,
                bold,
                italic,
                color_hex,
                rotation_deg,
            });
        }

        total_text_boxes += text_boxes.len();

        replicas.push(PageReplica {
            width_pt: page.width().value,
            height_pt: page.height().value,
            background_png,
            text_boxes,
        });
    }

    if total_text_boxes == 0 {
        return Err(ConverterError::UnsupportedScannedPdf(
            "This PDF has no extractable text layer. OCR-backed scanned PDF support is planned for a future version.".to_string(),
        ));
    }

    Ok(replicas)
}

fn render_page_background(page: &PdfPage<'_>) -> Result<Vec<u8>> {
    let target_width = ((page.width().value * 2.0).ceil() as i32).max(1);
    let bitmap = page
        .render_with_config(
            &PdfRenderConfig::new()
                .set_target_width(target_width)
                .render_form_data(true),
        )
        .context("unable to render page with PDFium")?;

    let image = bitmap.as_image();
    let mut cursor = Cursor::new(Vec::new());
    image
        .write_to(&mut cursor, ImageFormat::Png)
        .context("unable to encode background image as PNG")?;
    Ok(cursor.into_inner())
}

fn write_docx(
    output_path: &Path,
    pages: &[PageReplica],
) -> std::result::Result<(), ConverterError> {
    let file = File::create(output_path).map_err(|err| {
        ConverterError::DocxGeneration(format!("Unable to create {}: {err}", output_path.display()))
    })?;

    let mut zip = ZipWriter::new(file);
    let options = FileOptions::default().compression_method(CompressionMethod::Deflated);

    write_zip_entry(
        &mut zip,
        "[Content_Types].xml",
        &content_types_xml(pages),
        options,
    )?;
    write_zip_entry(&mut zip, "_rels/.rels", ROOT_RELS_XML, options)?;
    write_zip_entry(&mut zip, "docProps/app.xml", APP_XML, options)?;
    write_zip_entry(&mut zip, "docProps/core.xml", CORE_XML, options)?;
    write_zip_entry(&mut zip, "word/styles.xml", STYLES_XML, options)?;
    write_zip_entry(
        &mut zip,
        "word/_rels/document.xml.rels",
        &document_rels_xml(pages),
        options,
    )?;
    write_zip_entry(&mut zip, "word/document.xml", &document_xml(pages), options)?;

    for (index, page) in pages.iter().enumerate() {
        write_binary_zip_entry(
            &mut zip,
            &format!("word/media/page-{}.png", index + 1),
            &page.background_png,
            options,
        )?;
    }

    zip.finish().map_err(|err| {
        ConverterError::DocxGeneration(format!("Unable to finalize DOCX archive: {err}"))
    })?;

    Ok(())
}

fn write_zip_entry(
    zip: &mut ZipWriter<File>,
    path: &str,
    contents: &str,
    options: FileOptions,
) -> std::result::Result<(), ConverterError> {
    zip.start_file(path, options).map_err(|err| {
        ConverterError::DocxGeneration(format!("Unable to add {path} to DOCX: {err}"))
    })?;
    zip.write_all(contents.as_bytes()).map_err(|err| {
        ConverterError::DocxGeneration(format!("Unable to write {path} to DOCX: {err}"))
    })
}

fn write_binary_zip_entry(
    zip: &mut ZipWriter<File>,
    path: &str,
    contents: &[u8],
    options: FileOptions,
) -> std::result::Result<(), ConverterError> {
    zip.start_file(path, options).map_err(|err| {
        ConverterError::DocxGeneration(format!("Unable to add {path} to DOCX: {err}"))
    })?;
    zip.write_all(contents).map_err(|err| {
        ConverterError::DocxGeneration(format!("Unable to write binary {path} to DOCX: {err}"))
    })
}

fn content_types_xml(pages: &[PageReplica]) -> String {
    let png_override = if pages.is_empty() {
        ""
    } else {
        r#"<Default Extension="png" ContentType="image/png"/>"#
    };

    format!(
        r#"<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  {png_override}
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
</Types>"#
    )
}

fn document_rels_xml(pages: &[PageReplica]) -> String {
    let mut xml = String::from(
        r#"<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>"#,
    );

    for (index, _) in pages.iter().enumerate() {
        xml.push_str(&format!(
            r#"<Relationship Id="rId{}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/page-{}.png"/>"#,
            index + 2,
            index + 1
        ));
    }

    xml.push_str("</Relationships>");
    xml
}

fn document_xml(pages: &[PageReplica]) -> String {
    let mut body = String::new();

    for (page_index, page) in pages.iter().enumerate() {
        let image_rel_id = format!("rId{}", page_index + 2);
        body.push_str(&background_paragraph(page_index, page, &image_rel_id));

        for (text_index, text_box) in page.text_boxes.iter().enumerate() {
            body.push_str(&textbox_paragraph(page_index, text_index, text_box));
        }

        body.push_str(&section_break_paragraph(
            page.width_pt,
            page.height_pt,
            page_index < pages.len() - 1,
        ));
    }

    format!(
        r#"<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document
  xmlns:o="urn:schemas-microsoft-com:office:office"
  xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
  xmlns:v="urn:schemas-microsoft-com:vml"
  xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
  xmlns:w10="urn:schemas-microsoft-com:office:word">
  <w:body>{body}</w:body>
</w:document>"#
    )
}

fn background_paragraph(page_index: usize, page: &PageReplica, rel_id: &str) -> String {
    format!(
        r#"<w:p><w:pPr><w:spacing w:before="0" w:after="0"/></w:pPr><w:r><w:pict><v:rect id="page-bg-{page_index}" o:allowincell="f" stroked="f" style="position:absolute;margin-left:0pt;margin-top:0pt;width:{width:.2}pt;height:{height:.2}pt;z-index:-251658240;mso-wrap-style:none"><v:imagedata r:id="{rel_id}" o:title="page-{page_number}"/></v:rect></w:pict></w:r></w:p>"#,
        width = page.width_pt,
        height = page.height_pt,
        rel_id = rel_id,
        page_number = page_index + 1,
    )
}

fn textbox_paragraph(page_index: usize, text_index: usize, text_box: &TextBox) -> String {
    let font_size_half_points = (text_box.font_size_pt * 2.0).round().max(2.0) as i32;
    let line_twips = (text_box.height_pt * 20.0).round().max(20.0) as i32;
    let rotation_attr = if text_box.rotation_deg.abs() > 0.01 {
        format!(r#" rotation="{:.2}""#, text_box.rotation_deg)
    } else {
        String::new()
    };
    let bold_xml = if text_box.bold { "<w:b/>" } else { "" };
    let italic_xml = if text_box.italic { "<w:i/>" } else { "" };

    format!(
        r#"<w:p><w:pPr><w:spacing w:before="0" w:after="0"/></w:pPr><w:r><w:pict><v:rect id="textbox-{page_index}-{text_index}" filled="f" stroked="f" o:allowincell="f" style="position:absolute;margin-left:{x:.2}pt;margin-top:{y:.2}pt;width:{width:.2}pt;height:{height:.2}pt;z-index:{z_index};mso-wrap-style:none"{rotation_attr}><v:textbox inset="0,0,0,0"><w:txbxContent><w:p><w:pPr><w:spacing w:before="0" w:after="0" w:line="{line_twips}" w:lineRule="exact"/></w:pPr><w:r><w:rPr><w:rFonts w:ascii="{font}" w:hAnsi="{font}" w:cs="{font}"/><w:color w:val="{color}"/><w:sz w:val="{font_size}"/>{bold_xml}{italic_xml}</w:rPr><w:t xml:space="preserve">{text}</w:t></w:r></w:p></w:txbxContent></v:textbox></v:rect></w:pict></w:r></w:p>"#,
        page_index = page_index,
        text_index = text_index,
        x = text_box.x_pt,
        y = text_box.y_pt,
        width = text_box.width_pt,
        height = text_box.height_pt,
        z_index = 1000 + text_index,
        rotation_attr = rotation_attr,
        line_twips = line_twips,
        font = escape_xml_attr(&text_box.font_family),
        color = escape_xml_attr(&text_box.color_hex),
        font_size = font_size_half_points,
        bold_xml = bold_xml,
        italic_xml = italic_xml,
        text = escape_xml_text(&text_box.text),
    )
}

fn section_break_paragraph(width_pt: f32, height_pt: f32, next_page: bool) -> String {
    let width_twips = points_to_twips(width_pt);
    let height_twips = points_to_twips(height_pt);
    let break_type = if next_page {
        r#"<w:type w:val="nextPage"/>"#
    } else {
        ""
    };

    format!(
        r#"<w:p><w:pPr><w:sectPr>{break_type}<w:pgSz w:w="{width_twips}" w:h="{height_twips}"/><w:pgMar w:top="0" w:right="0" w:bottom="0" w:left="0" w:header="0" w:footer="0" w:gutter="0"/></w:sectPr></w:pPr></w:p>"#
    )
}

fn points_to_twips(points: f32) -> i32 {
    (points * 20.0).round() as i32
}

fn normalize_text(raw: &str) -> String {
    raw.replace('\u{0}', "")
        .replace('\r', "")
        .replace('\n', " ")
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
}

fn sanitize_font_family(font: &str) -> String {
    let trimmed = font.trim();
    if trimmed.is_empty() {
        "Arial".to_string()
    } else {
        trimmed.to_string()
    }
}

fn escape_xml_text(text: &str) -> String {
    text.replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
}

fn escape_xml_attr(text: &str) -> String {
    escape_xml_text(text).replace('"', "&quot;")
}

const ROOT_RELS_XML: &str = r#"<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>"#;

const APP_XML: &str = r#"<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>DocForge Rust Converter</Application>
</Properties>"#;

const CORE_XML: &str = r#"<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>DocForge PDF Replica</dc:title>
  <dc:creator>DocForge Rust Converter</dc:creator>
  <cp:lastModifiedBy>DocForge Rust Converter</cp:lastModifiedBy>
  <dcterms:created xsi:type="dcterms:W3CDTF">2026-04-29T00:00:00Z</dcterms:created>
  <dcterms:modified xsi:type="dcterms:W3CDTF">2026-04-29T00:00:00Z</dcterms:modified>
</cp:coreProperties>"#;

const STYLES_XML: &str = r#"<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:docDefaults>
    <w:rPrDefault>
      <w:rPr>
        <w:rFonts w:ascii="Arial" w:hAnsi="Arial" w:cs="Arial"/>
        <w:sz w:val="22"/>
        <w:color w:val="000000"/>
      </w:rPr>
    </w:rPrDefault>
    <w:pPrDefault>
      <w:pPr>
        <w:spacing w:before="0" w:after="0"/>
      </w:pPr>
    </w:pPrDefault>
  </w:docDefaults>
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal">
    <w:name w:val="Normal"/>
    <w:qFormat/>
  </w:style>
</w:styles>"#;
