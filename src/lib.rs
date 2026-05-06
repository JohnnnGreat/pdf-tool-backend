use pdf_oxide::geometry::Rect;
use pdf_oxide::pipeline::{
    OrderedTextSpan, ReadingOrderContext, ReadingOrderStrategyType, TextPipeline,
    TextPipelineConfig,
};
use pdf_oxide::PdfDocument;
use pyo3::create_exception;
use pyo3::exceptions::PyException;
use pyo3::prelude::*;
use rdocx::paragraph::SectionBreak;
use rdocx::{Alignment, BorderStyle, Document, Length, TabAlignment};
use rdocx::table::VerticalAlignment;
use std::fs;
use std::path::Path;
use thiserror::Error;

// ──────────────────────────────────────────────────────────────
// PyO3 exceptions
// ──────────────────────────────────────────────────────────────

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

#[pyfunction]
fn convert_pdf_to_docx(input_path: &str, output_path: &str) -> PyResult<bool> {
    match convert_pdf_to_docx_impl(Path::new(input_path), Path::new(output_path)) {
        Ok(()) => Ok(true),
        Err(ConverterError::InvalidPdf(m)) => Err(InvalidPdfError::new_err(m)),
        Err(ConverterError::UnsupportedScannedPdf(m)) => {
            Err(UnsupportedScannedPdfError::new_err(m))
        }
        Err(ConverterError::DocxGeneration(m)) => Err(DocxGenerationError::new_err(m)),
        Err(ConverterError::MissingOutput(m)) => Err(DocxGenerationError::new_err(m)),
        Err(ConverterError::Conversion(m)) => Err(RustConversionError::new_err(m)),
    }
}

#[pymodule]
fn _rust_converter(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add("RustConversionError", module.py().get_type::<RustConversionError>())?;
    module.add("InvalidPdfError", module.py().get_type::<InvalidPdfError>())?;
    module.add("UnsupportedScannedPdfError", module.py().get_type::<UnsupportedScannedPdfError>())?;
    module.add("DocxGenerationError", module.py().get_type::<DocxGenerationError>())?;
    module.add_function(wrap_pyfunction!(convert_pdf_to_docx, module)?)?;
    Ok(())
}

// ──────────────────────────────────────────────────────────────
// Internal layout types
// ──────────────────────────────────────────────────────────────

/// A single styled text run with top-down page coordinates.
#[derive(Debug, Clone)]
struct RichSpan {
    text: String,
    left_pt: f32,
    right_pt: f32,
    top_pt: f32,
    bottom_pt: f32,
    /// PDF-space y-centre (bottom-up) used only for line clustering.
    center_y_pdf: f32,
    font_name: String,
    font_size_pt: f32,
    bold: bool,
    italic: bool,
    color_hex: String,
    char_spacing_pt: f32,
    width_scale_pct: u32,
    group_id: Option<usize>,
    block_id: Option<u32>,
}

/// All spans clustered onto the same visual baseline.
#[derive(Debug, Clone)]
struct TextLine {
    spans: Vec<RichSpan>,
    left_pt: f32,
    right_pt: f32,
    top_pt: f32,
    bottom_pt: f32,
    center_y_pdf: f32,
    avg_font_size_pt: f32,
    group_id: Option<usize>,
    block_id: Option<u32>,
}

impl TextLine {
    /// Split a line into column cells by detecting large horizontal gaps.
    /// Returns groups of contiguous spans; each group is one cell.
    fn detect_cells(&self) -> Vec<(f32, f32, Vec<RichSpan>)> {
        if self.spans.is_empty() {
            return vec![];
        }
        let gap_threshold = (self.avg_font_size_pt * 2.5).max(12.0);
        let mut cells: Vec<(f32, f32, Vec<RichSpan>)> = vec![];
        let mut cur: Vec<RichSpan> = vec![self.spans[0].clone()];

        for i in 1..self.spans.len() {
            let gap = self.spans[i].left_pt - self.spans[i - 1].right_pt;
            if gap > gap_threshold {
                let l = cur.first().unwrap().left_pt;
                let r = cur.last().unwrap().right_pt;
                cells.push((l, r, cur));
                cur = vec![self.spans[i].clone()];
            } else {
                cur.push(self.spans[i].clone());
            }
        }
        if !cur.is_empty() {
            let l = cur.first().unwrap().left_pt;
            let r = cur.last().unwrap().right_pt;
            cells.push((l, r, cur));
        }
        cells
    }
}

/// A detected table with uniform column grid.
#[derive(Debug, Clone)]
struct TableData {
    /// [row][col] → text runs in that cell (multiple spans = same "para" in cell)
    rows: Vec<Vec<Vec<RichSpan>>>,
    col_lefts: Vec<f32>,
    col_rights: Vec<f32>,
    top_pt: f32,
    bottom_pt: f32,
}

/// A paragraph: one or more merged lines of the same text block.
#[derive(Debug, Clone)]
struct ParaData {
    runs: Vec<RichSpan>,
    left_pt: f32,
    right_pt: f32,
    top_pt: f32,
    bottom_pt: f32,
    avg_font_size_pt: f32,
    alignment: WordAlignment,
    tab_stops_pt: Vec<f32>,
    space_before_pt: f32,
}

#[derive(Debug, Clone)]
struct ImageData {
    bytes: Vec<u8>,
    filename: String,
    left_pt: f32,
    top_pt: f32,
    width_pt: f32,
    height_pt: f32,
    page_width_pt: f32,
}

#[derive(Debug, Clone)]
enum PageBlock {
    Para(ParaData),
    Table(TableData),
    Image(ImageData),
}

#[derive(Debug)]
struct PageLayout {
    width_pt: f32,
    height_pt: f32,
    blocks: Vec<PageBlock>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum WordAlignment {
    Left,
    Center,
    Right,
    Justify,
}

// ──────────────────────────────────────────────────────────────
// Entry point
// ──────────────────────────────────────────────────────────────

fn convert_pdf_to_docx_impl(
    input_path: &Path,
    output_path: &Path,
) -> std::result::Result<(), ConverterError> {
    if !input_path.exists() {
        return Err(ConverterError::InvalidPdf(format!(
            "File not found: {}",
            input_path.display()
        )));
    }
    if let Some(p) = output_path.parent() {
        fs::create_dir_all(p).map_err(|e| {
            ConverterError::DocxGeneration(format!("Cannot create output dir: {e}"))
        })?;
    }

    let document = PdfDocument::open(input_path)
        .map_err(|e| ConverterError::InvalidPdf(e.to_string()))?;

    let page_count = document
        .page_count()
        .map_err(|e| ConverterError::InvalidPdf(e.to_string()))?;

    if page_count == 0 {
        return Err(ConverterError::InvalidPdf(
            "PDF has no readable pages.".to_string(),
        ));
    }

    let mut pages: Vec<PageLayout> = Vec::with_capacity(page_count);
    let mut total_chars = 0usize;

    for page_idx in 0..page_count {
        let page = extract_page(&document, page_idx)?;
        total_chars += count_text_chars(&page);
        pages.push(page);
    }

    if total_chars == 0 {
        return Err(ConverterError::UnsupportedScannedPdf(
            "No extractable text layer found. This PDF appears to be scanned or image-only. \
             Use the OCR pathway to convert it."
                .to_string(),
        ));
    }

    write_docx(output_path, &pages)?;

    if !output_path.exists() {
        return Err(ConverterError::MissingOutput(
            output_path.display().to_string(),
        ));
    }
    Ok(())
}

fn count_text_chars(page: &PageLayout) -> usize {
    page.blocks
        .iter()
        .map(|b| match b {
            PageBlock::Para(p) => p
                .runs
                .iter()
                .map(|r| r.text.chars().filter(|c| !c.is_whitespace()).count())
                .sum(),
            PageBlock::Table(t) => t
                .rows
                .iter()
                .flat_map(|row| row.iter())
                .flat_map(|cell| cell.iter())
                .map(|s| s.text.chars().filter(|c| !c.is_whitespace()).count())
                .sum(),
            PageBlock::Image(_) => 0,
        })
        .sum()
}

// ──────────────────────────────────────────────────────────────
// PDF extraction
// ──────────────────────────────────────────────────────────────

#[derive(Clone, Copy)]
struct PageBox {
    llx: f32,
    lly: f32,
    width: f32,
    height: f32,
}

fn extract_page(
    document: &PdfDocument,
    page_idx: usize,
) -> std::result::Result<PageLayout, ConverterError> {
    let (llx, lly, urx, ury) = document
        .get_page_media_box(page_idx)
        .map_err(|e| ConverterError::InvalidPdf(e.to_string()))?;
    let pbox = PageBox {
        llx,
        lly,
        width: (urx - llx).max(1.0),
        height: (ury - lly).max(1.0),
    };

    let ordered = extract_ordered_spans(document, page_idx, pbox)?;
    let rich = build_rich_spans(&ordered, pbox);
    let lines = cluster_into_lines(rich);
    let images = extract_images(document, page_idx, pbox)?;

    let mut blocks = split_into_blocks(lines, pbox.width);

    // Merge images into the block list, sorted by vertical position.
    for img in images {
        blocks.push(PageBlock::Image(img));
    }
    blocks.sort_by(|a, b| {
        block_top(a)
            .partial_cmp(&block_top(b))
            .unwrap_or(std::cmp::Ordering::Equal)
    });

    Ok(PageLayout {
        width_pt: pbox.width,
        height_pt: pbox.height,
        blocks,
    })
}

fn block_top(b: &PageBlock) -> f32 {
    match b {
        PageBlock::Para(p) => p.top_pt,
        PageBlock::Table(t) => t.top_pt,
        PageBlock::Image(i) => i.top_pt,
    }
}

fn extract_ordered_spans(
    document: &PdfDocument,
    page_idx: usize,
    pbox: PageBox,
) -> std::result::Result<Vec<OrderedTextSpan>, ConverterError> {
    let raw = document
        .extract_spans(page_idx)
        .map_err(|e| ConverterError::Conversion(format!("extract_spans page {page_idx}: {e}")))?;

    if raw.is_empty() {
        return Ok(vec![]);
    }

    let mut cfg = TextPipelineConfig::default();
    cfg.reading_order.strategy = ReadingOrderStrategyType::XYCut;
    let pipeline = TextPipeline::with_config(cfg);
    let ctx = ReadingOrderContext::new()
        .with_page(page_idx as u32)
        .with_bbox(Rect::new(0.0, 0.0, pbox.width, pbox.height));

    pipeline.process(raw, ctx).map_err(|e| {
        ConverterError::Conversion(format!("reading order page {page_idx}: {e}"))
    })
}

fn build_rich_spans(ordered: &[OrderedTextSpan], pbox: PageBox) -> Vec<RichSpan> {
    let mut spans: Vec<&OrderedTextSpan> = ordered
        .iter()
        .filter(|s| !normalize_text(&s.span.text).is_empty())
        .collect();
    spans.sort_by_key(|s| s.reading_order);

    spans
        .iter()
        .map(|o| {
            let x = o.span.bbox.x - pbox.llx;
            let y_bottom_pdf = o.span.bbox.y - pbox.lly;
            let h = o.span.bbox.height.max(o.span.font_size.max(1.0));
            let y_top_pdf = y_bottom_pdf + h;

            let top_pt = (pbox.height - y_top_pdf).max(0.0);
            let bottom_pt = (pbox.height - y_bottom_pdf).max(top_pt);
            let center_y_pdf = y_bottom_pdf + h / 2.0;

            RichSpan {
                text: normalize_text(&o.span.text),
                left_pt: x.max(0.0),
                right_pt: (x + o.span.bbox.width).max(x),
                top_pt,
                bottom_pt,
                center_y_pdf,
                font_name: sanitize_font_name(&o.span.font_name),
                font_size_pt: o.span.font_size.clamp(4.0, 288.0),
                bold: o.span.font_weight.is_bold(),
                italic: o.span.is_italic,
                color_hex: color_to_hex(&o.span),
                char_spacing_pt: o.span.char_spacing,
                width_scale_pct: o
                    .span
                    .horizontal_scaling
                    .round()
                    .clamp(50.0, 200.0) as u32,
                group_id: o.group_id,
                block_id: o.block_id,
            }
        })
        .collect()
}

// ──────────────────────────────────────────────────────────────
// Line clustering
// ──────────────────────────────────────────────────────────────

fn cluster_into_lines(mut spans: Vec<RichSpan>) -> Vec<TextLine> {
    if spans.is_empty() {
        return vec![];
    }
    // Sort by reading order (they're already ordered, but sort by top_pt within
    // group for robustness, then by left_pt for visual order).
    spans.sort_by(|a, b| {
        let ya = a.center_y_pdf;
        let yb = b.center_y_pdf;
        // Higher PDF y = earlier (top of page). Primary: group_id, secondary: y desc, tertiary: x asc
        match (a.group_id, b.group_id) {
            (Some(ga), Some(gb)) if ga != gb => ga.cmp(&gb),
            _ => yb
                .partial_cmp(&ya)
                .unwrap_or(std::cmp::Ordering::Equal)
                .then(a.left_pt.partial_cmp(&b.left_pt).unwrap_or(std::cmp::Ordering::Equal)),
        }
    });

    let mut lines: Vec<TextLine> = vec![];
    let mut current_group: Vec<RichSpan> = vec![spans.remove(0)];

    for span in spans {
        let fits = same_visual_line(&current_group.last().unwrap(), &span);
        if fits {
            current_group.push(span);
        } else {
            if let Some(line) = finalize_line(current_group) {
                lines.push(line);
            }
            current_group = vec![span];
        }
    }
    if let Some(line) = finalize_line(current_group) {
        lines.push(line);
    }

    // Sort all lines top-to-bottom, left-to-right within same y.
    lines.sort_by(|a, b| {
        a.top_pt
            .partial_cmp(&b.top_pt)
            .unwrap_or(std::cmp::Ordering::Equal)
            .then(
                a.left_pt
                    .partial_cmp(&b.left_pt)
                    .unwrap_or(std::cmp::Ordering::Equal),
            )
    });

    lines
}

fn same_visual_line(a: &RichSpan, b: &RichSpan) -> bool {
    // Same group AND y-centers close enough to be on the same line
    if a.group_id != b.group_id {
        return false;
    }
    let mid_a = a.center_y_pdf;
    let mid_b = b.center_y_pdf;
    let tol = a.font_size_pt.max(b.font_size_pt) * 0.6 + 1.5;
    (mid_a - mid_b).abs() <= tol
}

fn finalize_line(mut spans: Vec<RichSpan>) -> Option<TextLine> {
    if spans.is_empty() {
        return None;
    }
    // Sort by left edge within the line.
    spans.sort_by(|a, b| {
        a.left_pt
            .partial_cmp(&b.left_pt)
            .unwrap_or(std::cmp::Ordering::Equal)
    });

    // Insert space / tab tokens between spans based on horizontal gap.
    let mut merged: Vec<RichSpan> = Vec::with_capacity(spans.len());
    let avg_fs: f32 = spans.iter().map(|s| s.font_size_pt).sum::<f32>() / spans.len() as f32;

    for (i, mut span) in spans.into_iter().enumerate() {
        if i > 0 {
            let prev_right = merged.last().unwrap().right_pt;
            let gap = (span.left_pt - prev_right).max(0.0);
            let tab_gap = (avg_fs * 4.0).max(24.0);
            let space_gap = (avg_fs * 0.25).max(1.5);

            if gap > tab_gap {
                span.text = format!("\t{}", span.text);
            } else if gap > space_gap {
                span.text = format!(" {}", span.text);
            }
        }
        merged.push(span);
    }

    let left_pt = merged.first().unwrap().left_pt;
    let right_pt = merged.iter().map(|s| s.right_pt).fold(0.0_f32, f32::max);
    let top_pt = merged.iter().map(|s| s.top_pt).fold(f32::MAX, f32::min);
    let bottom_pt = merged.iter().map(|s| s.bottom_pt).fold(0.0_f32, f32::max);
    let center_y_pdf = merged.iter().map(|s| s.center_y_pdf).sum::<f32>() / merged.len() as f32;
    let avg_font_size_pt = avg_fs;
    let group_id = merged.first().and_then(|s| s.group_id);
    let block_id = merged.first().and_then(|s| s.block_id);

    Some(TextLine {
        spans: merged,
        left_pt,
        right_pt,
        top_pt,
        bottom_pt,
        center_y_pdf,
        avg_font_size_pt,
        group_id,
        block_id,
    })
}

// ──────────────────────────────────────────────────────────────
// Table detection
// ──────────────────────────────────────────────────────────────

/// Returns a list of (start_line_idx, end_line_idx_exclusive) ranges that
/// form table regions, plus the column boundaries detected.
fn find_table_ranges(lines: &[TextLine]) -> Vec<(usize, usize, Vec<(f32, f32)>)> {
    let mut ranges: Vec<(usize, usize, Vec<(f32, f32)>)> = vec![];
    let mut i = 0;

    while i < lines.len() {
        let cells_i = lines[i].detect_cells();
        if cells_i.len() < 2 {
            i += 1;
            continue;
        }

        // Try to extend a table region starting at line i.
        let n_cols = cells_i.len();
        let ref_cols: Vec<f32> = cells_i.iter().map(|(l, r, _)| (l + r) / 2.0).collect();

        let mut j = i + 1;
        while j < lines.len() {
            let cells_j = lines[j].detect_cells();
            if cells_j.len() != n_cols {
                break;
            }
            // Check that all column centres align within tolerance.
            let tol = lines[j].avg_font_size_pt * 3.0;
            let matches = cells_j
                .iter()
                .enumerate()
                .all(|(k, (l, r, _))| ((l + r) / 2.0 - ref_cols[k]).abs() <= tol);
            if !matches {
                break;
            }
            j += 1;
        }

        if j - i >= 2 {
            // Compute the final column boundaries over all rows in the region.
            let mut col_lefts = vec![f32::MAX; n_cols];
            let mut col_rights = vec![0.0_f32; n_cols];

            for line in &lines[i..j] {
                for (k, (l, r, _)) in line.detect_cells().iter().enumerate() {
                    col_lefts[k] = col_lefts[k].min(*l);
                    col_rights[k] = col_rights[k].max(*r);
                }
            }

            let col_bounds: Vec<(f32, f32)> =
                col_lefts.into_iter().zip(col_rights).collect();
            ranges.push((i, j, col_bounds));
            i = j;
        } else {
            i += 1;
        }
    }

    ranges
}

fn build_table(lines: &[TextLine], col_bounds: &[(f32, f32)]) -> TableData {
    let n_cols = col_bounds.len();
    let mut rows: Vec<Vec<Vec<RichSpan>>> = vec![];

    for line in lines {
        let cells_raw = line.detect_cells();
        let mut row: Vec<Vec<RichSpan>> = vec![vec![]; n_cols];

        for (l, _r, spans) in cells_raw {
            // Assign cell to the nearest column by left edge.
            let best_col = col_bounds
                .iter()
                .enumerate()
                .min_by(|(_, (cl, _)), (_, (dl, _))| {
                    (l - cl).abs().partial_cmp(&(l - dl).abs()).unwrap()
                })
                .map(|(k, _)| k)
                .unwrap_or(0);
            row[best_col].extend(spans);
        }
        rows.push(row);
    }

    let top_pt = lines.first().map(|l| l.top_pt).unwrap_or(0.0);
    let bottom_pt = lines.last().map(|l| l.bottom_pt).unwrap_or(0.0);

    TableData {
        rows,
        col_lefts: col_bounds.iter().map(|(l, _)| *l).collect(),
        col_rights: col_bounds.iter().map(|(_, r)| *r).collect(),
        top_pt,
        bottom_pt,
    }
}

// ──────────────────────────────────────────────────────────────
// Paragraph assembly
// ──────────────────────────────────────────────────────────────

fn split_into_blocks(lines: Vec<TextLine>, page_width: f32) -> Vec<PageBlock> {
    if lines.is_empty() {
        return vec![];
    }

    let table_ranges = find_table_ranges(&lines);

    let mut blocks: Vec<PageBlock> = vec![];
    let mut i = 0;

    while i < lines.len() {
        // Check if a table region starts here.
        if let Some((start, end, cols)) = table_ranges.iter().find(|(s, _, _)| *s == i) {
            blocks.push(PageBlock::Table(build_table(&lines[*start..*end], cols)));
            i = *end;
            continue;
        }

        // Accumulate lines into a paragraph.
        let mut para_lines: Vec<&TextLine> = vec![&lines[i]];
        i += 1;

        while i < lines.len()
            && !table_ranges.iter().any(|(s, _, _)| *s == i)
            && can_merge_line(para_lines.last().unwrap(), &lines[i])
        {
            para_lines.push(&lines[i]);
            i += 1;
        }

        if let Some(para) = assemble_paragraph(&para_lines, page_width) {
            blocks.push(PageBlock::Para(para));
        }
    }

    blocks
}

fn can_merge_line(prev: &TextLine, next: &TextLine) -> bool {
    // Same group (column), same block_id when available, small vertical gap.
    if prev.group_id != next.group_id {
        return false;
    }
    // If both have block_ids and they differ, it's a hard paragraph boundary.
    if let (Some(ba), Some(bb)) = (prev.block_id, next.block_id) {
        if ba != bb {
            return false;
        }
    }
    let gap = next.top_pt - prev.bottom_pt;
    let threshold = (prev.avg_font_size_pt * 0.5).max(4.0);
    gap <= threshold && (next.left_pt - prev.left_pt).abs() <= prev.avg_font_size_pt * 2.0
}

fn assemble_paragraph(lines: &[&TextLine], page_width: f32) -> Option<ParaData> {
    if lines.is_empty() {
        return None;
    }
    let first = lines[0];
    let top_pt = first.top_pt;
    let bottom_pt = lines.last().unwrap().bottom_pt;
    let left_pt = lines.iter().map(|l| l.left_pt).fold(f32::MAX, f32::min);
    let right_pt = lines.iter().map(|l| l.right_pt).fold(0.0_f32, f32::max);
    let avg_font_size_pt = lines.iter().map(|l| l.avg_font_size_pt).sum::<f32>()
        / lines.len() as f32;

    let alignment = detect_alignment(left_pt, right_pt, page_width);

    // Collect all tab stop positions.
    let mut tab_stops: Vec<f32> = lines
        .iter()
        .flat_map(|l| l.spans.iter())
        .filter(|s| s.text.starts_with('\t'))
        .map(|s| s.left_pt)
        .collect();
    tab_stops.sort_by(|a, b| a.partial_cmp(b).unwrap());
    tab_stops.dedup_by(|a, b| (*a - *b).abs() < 0.5);

    // Flatten all spans, adding a line separator between lines.
    let mut runs: Vec<RichSpan> = vec![];
    for (li, line) in lines.iter().enumerate() {
        for (si, span) in line.spans.iter().enumerate() {
            if li > 0 && si == 0 {
                // Prepend a space or hyphen continuation.
                let prev_last = lines[li - 1].spans.last();
                let sep = if prev_last.map(|s| s.text.trim_end().ends_with('-')).unwrap_or(false) {
                    ""
                } else {
                    " "
                };
                let mut joined = span.clone();
                let trimmed = span.text.trim_start_matches('\t').trim_start().to_string();
                joined.text = if span.text.starts_with('\t') {
                    format!("{sep}\t{trimmed}")
                } else {
                    format!("{sep}{trimmed}")
                };
                runs.push(joined);
            } else {
                runs.push(span.clone());
            }
        }
    }

    Some(ParaData {
        runs,
        left_pt,
        right_pt,
        top_pt,
        bottom_pt,
        avg_font_size_pt,
        alignment,
        tab_stops_pt: tab_stops,
        space_before_pt: 0.0, // filled in write_docx
    })
}

// ──────────────────────────────────────────────────────────────
// Image extraction
// ──────────────────────────────────────────────────────────────

fn extract_images(
    document: &PdfDocument,
    page_idx: usize,
    pbox: PageBox,
) -> std::result::Result<Vec<ImageData>, ConverterError> {
    let raw = document
        .extract_images(page_idx)
        .map_err(|e| ConverterError::Conversion(format!("extract_images page {page_idx}: {e}")))?;

    let mut out = vec![];
    for (idx, img) in raw.into_iter().enumerate() {
        let Some(bbox) = img.bbox().copied() else {
            continue;
        };
        let w = bbox.width.max(0.0);
        let h = bbox.height.max(0.0);
        if w < 12.0 || h < 12.0 {
            continue;
        }
        let bytes = img.to_png_bytes().map_err(|e| {
            ConverterError::Conversion(format!("image encode page {page_idx}: {e}"))
        })?;

        let x = (bbox.x - pbox.llx).max(0.0);
        let y_bottom = bbox.y - pbox.lly;
        let top_pt = (pbox.height - (y_bottom + h)).max(0.0);

        out.push(ImageData {
            bytes,
            filename: format!("page{}-img{}.png", page_idx + 1, idx + 1),
            left_pt: x,
            top_pt,
            width_pt: w,
            height_pt: h,
            page_width_pt: pbox.width,
        });
    }
    Ok(out)
}

// ──────────────────────────────────────────────────────────────
// DOCX output
// ──────────────────────────────────────────────────────────────

fn write_docx(
    output_path: &Path,
    pages: &[PageLayout],
) -> std::result::Result<(), ConverterError> {
    let first = pages.first().unwrap();
    let last = pages.last().unwrap();

    let mut document = Document::new();
    document.set_page_size(
        Length::pt(last.width_pt as f64),
        Length::pt(last.height_pt as f64),
    );
    document.set_margins(
        Length::pt(0.0),
        Length::pt(0.0),
        Length::pt(0.0),
        Length::pt(0.0),
    );

    // Pre-compute spacing_before for each block by comparing to its predecessor.
    for (page_idx, page) in pages.iter().enumerate() {
        let prev_page = if page_idx > 0 { Some(&pages[page_idx - 1]) } else { None };
        let is_new_page_section = page_idx > 0
            && prev_page.map_or(false, |pp| !page_size_eq(page, pp));

        let mut prev_bottom: Option<f32> = None;
        let block_count = page.blocks.len();

        for (bi, block) in page.blocks.iter().enumerate() {
            let is_first_block = bi == 0;
            let is_last_block = bi + 1 == block_count;
            let needs_page_break = page_idx > 0 && is_first_block;

            let space_before = match prev_bottom {
                Some(pb) => (block_top(block) - pb).max(0.0),
                None => block_top(block).max(0.0),
            };

            match block {
                PageBlock::Para(para) => {
                    write_paragraph(
                        &mut document,
                        para,
                        space_before,
                        needs_page_break,
                        is_last_block && is_new_page_section,
                        page,
                    );
                }
                PageBlock::Table(table) => {
                    // Table cannot carry page_break_before directly.
                    // Emit an empty separator paragraph for the page break.
                    if needs_page_break {
                        let mut sep = document.add_paragraph("");
                        sep = sep
                            .page_break_before(true)
                            .space_before(Length::pt(0.0))
                            .space_after(Length::pt(0.0));
                        if is_last_block && is_new_page_section {
                            sep = apply_section_break(sep, page);
                        }
                    }
                    write_table(&mut document, table, is_last_block && is_new_page_section, page);
                }
                PageBlock::Image(img) => {
                    write_image_block(
                        &mut document,
                        img,
                        space_before,
                        needs_page_break,
                        is_last_block && is_new_page_section,
                        page,
                    );
                }
            }

            prev_bottom = Some(block_bottom(block));
        }

        // If the page had no blocks at all, emit an empty page.
        if block_count == 0 && page_idx > 0 {
            let mut blank = document.add_paragraph("");
            blank = blank.page_break_before(true).space_before(Length::pt(0.0)).space_after(Length::pt(0.0));
            if is_new_page_section {
                blank = apply_section_break(blank, page);
            }
            let _ = blank;
        }
    }

    document.save(output_path).map_err(|e| {
        ConverterError::DocxGeneration(format!("save {}: {e}", output_path.display()))
    })?;
    Ok(())
}

fn block_bottom(b: &PageBlock) -> f32 {
    match b {
        PageBlock::Para(p) => p.bottom_pt,
        PageBlock::Table(t) => t.bottom_pt,
        PageBlock::Image(i) => i.top_pt + i.height_pt,
    }
}

fn page_size_eq(a: &PageLayout, b: &PageLayout) -> bool {
    (a.width_pt - b.width_pt).abs() <= 1.0 && (a.height_pt - b.height_pt).abs() <= 1.0
}

fn apply_section_break<'a>(
    para: rdocx::paragraph::Paragraph<'a>,
    page: &PageLayout,
) -> rdocx::paragraph::Paragraph<'a> {
    para.section_page_size(
        Length::pt(page.width_pt as f64),
        Length::pt(page.height_pt as f64),
    )
    .section_break(SectionBreak::NextPage)
}

fn write_paragraph(
    document: &mut Document,
    para: &ParaData,
    space_before_pt: f32,
    page_break_before: bool,
    section_break: bool,
    page: &PageLayout,
) {
    let mut word_para = document.add_paragraph("");

    if page_break_before {
        word_para = word_para.page_break_before(true);
    }

    word_para = word_para
        .alignment(to_rdocx_align(para.alignment))
        .indent_left(Length::pt(para.left_pt as f64))
        .line_spacing_multiple(1.15)
        .space_after(Length::pt(0.0));

    if space_before_pt > 0.5 {
        word_para = word_para.space_before(Length::pt(space_before_pt as f64));
    }

    for ts in &para.tab_stops_pt {
        word_para = word_para.add_tab_stop(TabAlignment::Left, Length::pt(*ts as f64));
    }

    for span in &para.runs {
        let mut run = word_para.add_run(&span.text);
        run = run
            .font(&span.font_name)
            .size(span.font_size_pt as f64)
            .bold(span.bold)
            .italic(span.italic)
            .color(&span.color_hex);
        if span.width_scale_pct != 100 {
            run = run.width_scale(span.width_scale_pct);
        }
        if span.char_spacing_pt.abs() > 0.05 {
            run = run.character_spacing(Length::pt(span.char_spacing_pt as f64));
        }
    }

    if section_break {
        word_para = apply_section_break(word_para, page);
    }
    let _ = word_para;
}

fn write_table(
    document: &mut Document,
    table: &TableData,
    section_break: bool,
    page: &PageLayout,
) {
    let n_rows = table.rows.len();
    let n_cols = table.col_lefts.len();
    if n_rows == 0 || n_cols == 0 {
        return;
    }

    // Compute column widths from detected boundaries.
    let col_widths: Vec<f32> = table
        .col_lefts
        .iter()
        .zip(&table.col_rights)
        .map(|(l, r)| (r - l).max(8.0))
        .collect();
    let total_width: f32 = col_widths.iter().sum();

    let mut tbl = document.add_table(n_rows, n_cols);
    tbl = tbl
        .width(Length::pt(total_width as f64))
        .borders(BorderStyle::Single, 4, "999999")
        .cell_margins(
            Length::pt(2.0),
            Length::pt(3.0),
            Length::pt(2.0),
            Length::pt(3.0),
        )
        .layout_fixed();

    for (ri, row_data) in table.rows.iter().enumerate() {
        for (ci, cell_spans) in row_data.iter().enumerate() {
            if let Some(mut cell) = tbl.cell(ri, ci) {
                cell = cell
                    .width(Length::pt(col_widths[ci] as f64))
                    .vertical_alignment(VerticalAlignment::Top);

                if cell_spans.is_empty() {
                    // Empty cell — add a blank paragraph to satisfy OOXML.
                    let _ = cell.add_paragraph("");
                } else {
                    // Group spans into sub-paragraphs by detecting line breaks
                    // (i.e., large vertical gaps between consecutive spans).
                    let sub_paras = group_cell_spans_into_paras(cell_spans);
                    for sub in sub_paras {
                        let mut word_para = cell.add_paragraph("");
                        word_para = word_para
                            .space_before(Length::pt(0.0))
                            .space_after(Length::pt(0.0));
                        for span in &sub {
                            let mut run = word_para.add_run(&span.text);
                            run = run
                                .font(&span.font_name)
                                .size(span.font_size_pt as f64)
                                .bold(span.bold)
                                .italic(span.italic)
                                .color(&span.color_hex);
                        }
                    }
                }
            }
        }
    }

    // Attach section break to the last paragraph of the last cell if needed.
    if section_break {
        // The section break goes on a paragraph *after* the table.
        let mut sep = document.add_paragraph("");
        sep = sep
            .space_before(Length::pt(0.0))
            .space_after(Length::pt(0.0));
        sep = apply_section_break(sep, page);
        let _ = sep;
    }
}

/// Split a flat list of spans into "sub-paragraphs" by top_pt gaps.
fn group_cell_spans_into_paras(spans: &[RichSpan]) -> Vec<Vec<RichSpan>> {
    if spans.is_empty() {
        return vec![];
    }
    let mut paras: Vec<Vec<RichSpan>> = vec![vec![spans[0].clone()]];
    for i in 1..spans.len() {
        let gap = spans[i].top_pt - spans[i - 1].bottom_pt;
        let fs = spans[i].font_size_pt.max(spans[i - 1].font_size_pt);
        if gap > fs * 0.5 {
            paras.push(vec![spans[i].clone()]);
        } else {
            paras.last_mut().unwrap().push(spans[i].clone());
        }
    }
    paras
}

fn write_image_block(
    document: &mut Document,
    img: &ImageData,
    space_before_pt: f32,
    page_break_before: bool,
    section_break: bool,
    page: &PageLayout,
) {
    let mut word_para = document.add_picture(
        &img.bytes,
        &img.filename,
        Length::pt(img.width_pt as f64),
        Length::pt(img.height_pt as f64),
    );

    if page_break_before {
        word_para = word_para.page_break_before(true);
    }

    let img_align = detect_image_alignment(img);
    word_para = word_para
        .alignment(to_rdocx_align(img_align))
        .space_after(Length::pt(0.0));

    if img_align == WordAlignment::Left {
        word_para = word_para.indent_left(Length::pt(img.left_pt as f64));
    }
    if space_before_pt > 0.5 {
        word_para = word_para.space_before(Length::pt(space_before_pt as f64));
    }
    if section_break {
        word_para = apply_section_break(word_para, page);
    }
    let _ = word_para;
}

// ──────────────────────────────────────────────────────────────
// Helpers
// ──────────────────────────────────────────────────────────────

fn detect_alignment(left: f32, right: f32, page_width: f32) -> WordAlignment {
    let content_w = (right - left).max(1.0);
    let center = left + content_w / 2.0;
    let page_center = page_width / 2.0;
    let left_gap = left.max(0.0);
    let right_gap = (page_width - right).max(0.0);

    if left_gap > 24.0
        && right_gap > 24.0
        && (center - page_center).abs() <= page_width * 0.08
        && content_w < page_width * 0.75
    {
        WordAlignment::Center
    } else if right_gap < left_gap * 0.55 && left_gap > 36.0 {
        WordAlignment::Right
    } else if content_w >= page_width * 0.82 {
        WordAlignment::Justify
    } else {
        WordAlignment::Left
    }
}

fn detect_image_alignment(img: &ImageData) -> WordAlignment {
    let center = img.left_pt + img.width_pt / 2.0;
    let page_center = img.page_width_pt / 2.0;
    let right_edge = img.left_pt + img.width_pt;
    let right_gap = (img.page_width_pt - right_edge).max(0.0);

    if (center - page_center).abs() <= img.page_width_pt * 0.08
        && img.left_pt > img.page_width_pt * 0.05
    {
        WordAlignment::Center
    } else if right_gap < img.left_pt * 0.5 && img.left_pt > img.page_width_pt * 0.1 {
        WordAlignment::Right
    } else {
        WordAlignment::Left
    }
}

fn to_rdocx_align(a: WordAlignment) -> Alignment {
    match a {
        WordAlignment::Left => Alignment::Left,
        WordAlignment::Center => Alignment::Center,
        WordAlignment::Right => Alignment::Right,
        WordAlignment::Justify => Alignment::Justify,
    }
}

fn color_to_hex(span: &pdf_oxide::layout::TextSpan) -> String {
    let ch = |v: f32| (v.clamp(0.0, 1.0) * 255.0).round() as u8;
    format!("{:02X}{:02X}{:02X}", ch(span.color.r), ch(span.color.g), ch(span.color.b))
}

fn sanitize_font_name(name: &str) -> String {
    let t = name.trim();
    if t.is_empty() {
        return "Arial".to_string();
    }
    let without_subset = t.split_once('+').map(|(_, s)| s.trim()).unwrap_or(t);
    if without_subset.is_empty() {
        "Arial".to_string()
    } else {
        without_subset.to_string()
    }
}

fn normalize_text(raw: &str) -> String {
    let mut s = raw.replace('\0', "").replace('\r', " ").replace('\n', " ");
    while s.contains("  ") {
        s = s.replace("  ", " ");
    }
    s.trim().to_string()
}
