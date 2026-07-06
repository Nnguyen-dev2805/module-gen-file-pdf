import os
import re
import unicodedata
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

import pdfplumber

from src.mock_adapters import MOCK_TRANSLATION_MAP
from src.typst_generator import compile_pdf as _compile_pdf


# English labels that should never appear in a correctly translated PDF
ENGLISH_LEAK_LABELS: List[str] = list(MOCK_TRANSLATION_MAP.keys())


@dataclass
class ValidationError:
    """Represents a single validation failure found in a PDF."""
    error_type: str       # "encoding" or "leak"
    message: str
    page_number: int      # 1-indexed page number where the issue was found
    detail: str = ""      # The offending text snippet


@dataclass
class ValidationResult:
    """Aggregated result of all validation checks on a PDF."""
    is_valid: bool = True
    errors: List[ValidationError] = field(default_factory=list)
    extracted_text: str = ""
    page_count: int = 0


def extract_text(pdf_path: str) -> str:
    """
    Extracts all text from a PDF file using pdfplumber.
    Returns the concatenated text from all pages, NFC-normalized.
    """
    pages_text: List[str] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            pages_text.append(text)
    full_text = "\n".join(pages_text)
    # Enforce Unicode NFC normalization on extracted text for consistent comparison
    return unicodedata.normalize("NFC", full_text)


def check_missing_glyphs(pdf_path: str) -> List[ValidationError]:
    """
    Checks for replacement characters (U+FFFD) in a PDF, which indicate
    that the font was unable to render one or more glyphs correctly.

    Returns a list of ValidationError with error_type="encoding" for each
    page where the replacement character is found.
    """
    errors: List[ValidationError] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_idx, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            text = unicodedata.normalize("NFC", text)
            if "\uFFFD" in text:
                # Count occurrences for a descriptive message
                count = text.count("\uFFFD")
                errors.append(ValidationError(
                    error_type="encoding",
                    message=f"Found {count} replacement character(s) (U+FFFD) on page {page_idx}. "
                            f"This indicates missing glyphs or font encoding failures.",
                    page_number=page_idx,
                    detail=f"\uFFFD x{count}"
                ))
    return errors


def check_leaked_english(pdf_path: str, labels: List[str] | None = None) -> List[ValidationError]:
    """
    Checks whether any known English annotation labels leaked into the final PDF
    without being translated. This catches failures in the image translation or
    Typst compilation pipeline.

    Args:
        pdf_path: Path to the PDF file to validate.
        labels: Optional list of English labels to check for. Defaults to
                the full MOCK_TRANSLATION_MAP keys.

    Returns a list of ValidationError with error_type="leak" for each
    leaked label found.
    """
    if labels is None:
        labels = ENGLISH_LEAK_LABELS

    errors: List[ValidationError] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_idx, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            text = unicodedata.normalize("NFC", text)
            for label in labels:
                if label in text:
                    errors.append(ValidationError(
                        error_type="leak",
                        message=f"Leaked English label \"{label}\" found on page {page_idx}. "
                                f"This text should have been translated to Vietnamese.",
                        page_number=page_idx,
                        detail=label
                    ))
    return errors


def validate_pdf(pdf_path: str) -> ValidationResult:
    """
    Runs all validation checks on a compiled PDF and returns a ValidationResult.

    Checks performed:
    1. Missing glyph detection (U+FFFD replacement characters).
    2. Leaked English annotation label detection.
    """
    result = ValidationResult()

    # Extract text for the result summary
    result.extracted_text = extract_text(pdf_path)

    with pdfplumber.open(pdf_path) as pdf:
        result.page_count = len(pdf.pages)

    # Run checks
    glyph_errors = check_missing_glyphs(pdf_path)
    leak_errors = check_leaked_english(pdf_path)

    result.errors = glyph_errors + leak_errors
    result.is_valid = len(result.errors) == 0

    return result


# ===================================================================
# 4-Tier Rescue Pipeline
# ===================================================================

# Font fallback order used by the rescue pipeline
FALLBACK_FONT_CHAIN = ["Roboto", "Noto Sans", "DejaVu Sans"]


@dataclass
class RescueResult:
    """Result of the rescue pipeline execution."""
    success: bool = False
    tier_reached: int = 0      # 0=no rescue needed, 1-4=which tier fixed it
    badge: str = "OK"          # "OK", "Warning", or "Critical Warning"
    validation_result: Optional[ValidationResult] = None
    rescue_log: List[str] = field(default_factory=list)
    output_pdf_path: str = ""


# -------------------------------------------------------------------
# Tier transformation helpers
# -------------------------------------------------------------------

def _rescue_tier1_nfc(content: str) -> str:
    """
    Tier 1: Unicode NFC normalization.
    - Normalizes all text to NFC form (fixes decomposed Vietnamese diacritics).
    - Strips U+FFFD replacement characters that indicate prior encoding failures.
    """
    normalized = unicodedata.normalize("NFC", content)
    normalized = normalized.replace("\uFFFD", "")
    return normalized


def _rescue_tier3_simplify(content: str) -> str:
    """
    Tier 3: Simplify markdown content by removing complex elements
    (images, tables) while preserving all textual content.
    """
    lines = content.splitlines()
    result: List[str] = []
    in_table = False
    table_header: List[str] = []

    for line in lines:
        stripped = line.strip()

        # Remove image tags
        if re.match(r'!\s*\[.*?\]\s*\(.*?\)', stripped):
            result.append("_(Hình ảnh đã được lược bỏ trong chế độ đơn giản)_")
            continue

        # Handle tables: extract content as plain text key-value pairs
        if stripped.startswith("|"):
            cells = [c.strip() for c in stripped.split("|")]
            cells = [c for c in cells if c]

            # Skip separator rows like |:---|:---|
            if cells and all(re.match(r'^:?-+:?$', c) for c in cells):
                continue

            if not in_table:
                in_table = True
                table_header = cells
            else:
                # Data row — format as "header: value" bullets
                for i, cell in enumerate(cells):
                    prefix = f"{table_header[i]}: " if i < len(table_header) else ""
                    result.append(f"- {prefix}{cell}")
            continue
        else:
            if in_table:
                in_table = False
                result.append("")  # Blank line after table content

        result.append(line)

    return "\n".join(result)


def _rescue_tier4_plaintext(content: str) -> str:
    """
    Tier 4: Strip ALL markdown formatting, preserving only plain text
    and Vietnamese accented characters. This is the last-resort fallback.
    """
    text = content

    # Remove image tags
    text = re.sub(r'!\s*\[.*?\]\s*\(.*?\)', '', text)

    # Convert headers to plain text (keep the title text)
    text = re.sub(r'^#{1,6}\s+(.+)$', r'\1', text, flags=re.MULTILINE)

    # Remove bold markers
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)

    # Remove italic markers (single * not preceded/followed by *)
    text = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'\1', text)

    # Convert table rows to comma-separated cell values
    new_lines: List[str] = []
    pending_table_rows: List[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("|"):
            cells = [c.strip() for c in stripped.split("|")]
            cells = [c for c in cells if c and not re.match(r'^:?-+:?$', c)]
            if cells:
                pending_table_rows.append(", ".join(cells))
        else:
            if pending_table_rows:
                new_lines.extend(pending_table_rows)
                pending_table_rows = []
                new_lines.append("")
            new_lines.append(line)
    if pending_table_rows:
        new_lines.extend(pending_table_rows)
    text = "\n".join(new_lines)

    # Remove list markers
    text = re.sub(r'^(\s*)[-*+]\s+', r'\1', text, flags=re.MULTILINE)
    text = re.sub(r'^(\s*)\d+\.\s+', r'\1', text, flags=re.MULTILINE)

    # Remove horizontal rules
    text = re.sub(r'^---+$', '', text, flags=re.MULTILINE)

    # Collapse multiple blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)

    # NFC normalize and strip replacement characters
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\uFFFD", "")

    return text.strip()


# -------------------------------------------------------------------
# Compile-and-validate helper
# -------------------------------------------------------------------

def _try_compile_and_validate(
    content: str,
    output_path: str,
    font_name: str,
    simplified: bool = False,
) -> Optional[ValidationResult]:
    """
    Attempts to compile content to PDF and validate the result.
    Returns a ValidationResult on success, or None if compilation fails.
    """
    try:
        _compile_pdf(content, output_path, font_name=font_name, simplified=simplified)
        return validate_pdf(output_path)
    except Exception:
        return None


# -------------------------------------------------------------------
# Main rescue pipeline runner
# -------------------------------------------------------------------

def run_rescue_pipeline(
    content_markdown: str,
    output_pdf_path: str,
    font_name: str = "Roboto",
) -> RescueResult:
    """
    Compiles a Vietnamese markdown document to PDF and validates the output.
    If validation fails, applies a sequential 4-tier rescue strategy:

      Tier 1 — Unicode NFC normalization (strips U+FFFD, fixes decomposed chars)
      Tier 2 — Recompile with fallback fonts (Roboto → Noto Sans → DejaVu Sans)
      Tier 3 — Recompile with simplified Typst layout (no header/footer/justify)
      Tier 4 — Recompile as plain-text PDF (all formatting stripped, accents kept)

    Post-rescue validator assigns badges:
      "OK"               — no rescue was needed
      "Warning"           — rescue succeeded at Tier 1, 2, or 3
      "Critical Warning"  — only Tier 4 plain-text fallback worked
    """
    rescue = RescueResult(output_pdf_path=output_pdf_path)

    # ------ Step 0: Initial compile and validate ------
    rescue.rescue_log.append("Step 0: Initial compile and validation.")
    result = _try_compile_and_validate(content_markdown, output_pdf_path, font_name)

    if result is not None and result.is_valid:
        rescue.success = True
        rescue.tier_reached = 0
        rescue.badge = "OK"
        rescue.validation_result = result
        rescue.rescue_log.append("Step 0: Passed. No rescue needed.")
        return rescue

    if result is not None:
        rescue.rescue_log.append(
            f"Step 0: Failed validation with {len(result.errors)} error(s). Starting rescue."
        )
    else:
        rescue.rescue_log.append("Step 0: Compilation failed. Starting rescue.")

    # ------ Tier 1: NFC normalization ------
    rescue.rescue_log.append("Tier 1: Applying Unicode NFC normalization...")
    nfc_content = _rescue_tier1_nfc(content_markdown)

    result = _try_compile_and_validate(nfc_content, output_pdf_path, font_name)
    if result is not None and result.is_valid:
        rescue.success = True
        rescue.tier_reached = 1
        rescue.badge = "Warning"
        rescue.validation_result = result
        rescue.rescue_log.append("Tier 1: Success. NFC normalization fixed the issue.")
        return rescue

    rescue.rescue_log.append("Tier 1: Still failing. Proceeding to Tier 2.")

    # ------ Tier 2: Fallback fonts ------
    rescue.rescue_log.append("Tier 2: Trying fallback fonts...")
    for fallback_font in FALLBACK_FONT_CHAIN:
        if fallback_font == font_name:
            continue  # Already tried with this font in Tier 1

        rescue.rescue_log.append(f"Tier 2: Trying font '{fallback_font}'...")
        result = _try_compile_and_validate(nfc_content, output_pdf_path, fallback_font)
        if result is not None and result.is_valid:
            rescue.success = True
            rescue.tier_reached = 2
            rescue.badge = "Warning"
            rescue.validation_result = result
            rescue.rescue_log.append(f"Tier 2: Success with font '{fallback_font}'.")
            return rescue

    rescue.rescue_log.append("Tier 2: All fonts failed. Proceeding to Tier 3.")

    # ------ Tier 3: Simplified layout ------
    rescue.rescue_log.append("Tier 3: Simplifying layout...")
    simple_content = _rescue_tier3_simplify(nfc_content)

    for font in FALLBACK_FONT_CHAIN:
        rescue.rescue_log.append(f"Tier 3: Trying simplified layout with font '{font}'...")
        result = _try_compile_and_validate(
            simple_content, output_pdf_path, font, simplified=True
        )
        if result is not None and result.is_valid:
            rescue.success = True
            rescue.tier_reached = 3
            rescue.badge = "Warning"
            rescue.validation_result = result
            rescue.rescue_log.append(
                f"Tier 3: Success with simplified layout and font '{font}'."
            )
            return rescue

    rescue.rescue_log.append("Tier 3: Failed. Proceeding to Tier 4.")

    # ------ Tier 4: Plain-text fallback ------
    rescue.rescue_log.append("Tier 4: Falling back to plain text...")
    plain_content = _rescue_tier4_plaintext(nfc_content)

    for font in FALLBACK_FONT_CHAIN:
        rescue.rescue_log.append(f"Tier 4: Trying plain text with font '{font}'...")
        result = _try_compile_and_validate(
            plain_content, output_pdf_path, font, simplified=True
        )
        if result is not None and result.is_valid:
            rescue.success = True
            rescue.tier_reached = 4
            rescue.badge = "Critical Warning"
            rescue.validation_result = result
            rescue.rescue_log.append(
                f"Tier 4: Success with plain text and font '{font}'."
            )
            return rescue

    rescue.rescue_log.append("Tier 4: All attempts failed.")

    # ------ All tiers exhausted ------
    rescue.tier_reached = 4
    rescue.badge = "Critical Warning"
    rescue.success = False
    rescue.validation_result = result
    rescue.rescue_log.append(
        "CRITICAL: All rescue tiers exhausted. No valid PDF could be produced."
    )
    return rescue
