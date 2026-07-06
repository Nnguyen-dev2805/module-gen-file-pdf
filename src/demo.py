#!/usr/bin/env python3
"""
End-to-End Demo: Vietnamese PDF Generation & Validation

Wires all modules together in a complete pipeline:
  1. OpenCode LLM generates a Vietnamese Markdown report with diagram references
  2. Image Translator converts English diagram annotations to Vietnamese
  3. Typst Generator compiles the content into a styled PDF
  4. PDF Validator checks for encoding issues and leaked English labels
  5. Rescue Pipeline attempts auto-recovery if encoding validation fails

Usage:
    python3 src/demo.py
"""

import os
import sys
import unicodedata

# Ensure project root is in the Python path for src imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.llm_client import OpenCodeClient
from src.report_image import DEFAULT_SOURCE_IMAGE, prepare_report_image_section
from src.typst_generator import compile_pdf
from src.pdf_validator import (
    validate_pdf,
    run_rescue_pipeline,
)

# ── Configuration ─────────────────────────────────────────────────────
OUTPUT_DIR = "temp"
OUTPUT_PDF = os.path.join(OUTPUT_DIR, "demo_report.pdf")

SEPARATOR = "═" * 65


def _step(num: int, total: int, title: str) -> None:
    pad = max(1, 42 - len(title))
    print(f"\n{'─' * 3} [Step {num}/{total}] {title} {'─' * pad}")


def main() -> int:
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print(f"\n{SEPARATOR}")
    print("  Vietnamese PDF Generation & Validation — E2E Demo")
    print(SEPARATOR)

    # ═══════════════════════════════════════════════════════════════
    # Step 1: Generate Vietnamese Markdown Report
    # ═══════════════════════════════════════════════════════════════
    _step(1, 5, "Generate Markdown Report")

    client = OpenCodeClient()
    if client.mock_mode:
        mode_str = "Mock (offline)"
    else:
        mode_str = f"OpenCode API ({client.opencode_model})"
    print(f"  LLM mode : {mode_str}")

    prompt = (
        "Tạo báo cáo chi tiết bằng tiếng Việt về cấu trúc và hoạt động "
        "của một kho hàng tự động thông minh, bao gồm sơ đồ phân khu."
    )
    report_md = client.generate_report(prompt)
    # NFC-normalize all LLM output immediately (per project coding guidelines)
    report_md = unicodedata.normalize("NFC", report_md)

    print(f"  Content  : {len(report_md):,} characters generated")
    print("  ✓ Done.")

    # ═══════════════════════════════════════════════════════════════
    # Step 2: Prepare Dedicated Report Image Section
    # ═══════════════════════════════════════════════════════════════
    _step(2, 5, "Prepare Report Image Section")

    image_result = prepare_report_image_section(
        report_md,
        source_image_path=DEFAULT_SOURCE_IMAGE,
        output_dir=OUTPUT_DIR,
        client=client,
    )
    document_md = image_result.markdown

    for entry in image_result.log:
        print(f"  {entry}")
    if image_result.output_image_path and os.path.exists(image_result.output_image_path):
        size = os.path.getsize(image_result.output_image_path)
        print(f"  Image    : {image_result.output_image_path} ({size:,} bytes)")

    print("  ✓ Done.")

    # ═══════════════════════════════════════════════════════════════
    # Step 3: Compile PDF via Typst
    # ═══════════════════════════════════════════════════════════════
    _step(3, 5, "Compile PDF via Typst")

    compile_ok = False
    try:
        compile_pdf(document_md, OUTPUT_PDF, font_name="Roboto")
        compile_ok = True
        pdf_size = os.path.getsize(OUTPUT_PDF)
        print(f"  Output   : {OUTPUT_PDF}")
        print(f"  Size     : {pdf_size:,} bytes")
        print("  ✓ Compilation successful.")
    except Exception as exc:
        print(f"  ✗ Compilation failed: {exc}")
        print("  → Will attempt rescue in Step 4.")

    # ═══════════════════════════════════════════════════════════════
    # Step 4: Validate & Rescue
    # ═══════════════════════════════════════════════════════════════
    _step(4, 5, "Validate & Rescue")

    badge = "OK"
    rescue_applied = False
    rescue_tier = 0

    if compile_ok:
        validation = validate_pdf(OUTPUT_PDF)

        encoding_errors = [e for e in validation.errors if e.error_type == "encoding"]
        leak_errors = [e for e in validation.errors if e.error_type == "leak"]

        print(f"  Pages    : {validation.page_count}")
        print(f"  Text     : {len(validation.extracted_text):,} characters extracted")

        # ── Encoding check ──
        if encoding_errors:
            for err in encoding_errors:
                print(f"  ✗ {err.message}")
        else:
            print("  ✓ Encoding : No missing glyphs (U+FFFD)")

        # ── Leak check ──
        if leak_errors:
            print(
                f"  ⚠ Leak check: {len(leak_errors)} English label(s) "
                f"detected in body text"
            )
            for err in leak_errors:
                print(f"      \"{err.detail}\" (page {err.page_number})")
        else:
            print("  ✓ Leak check: No leaked English annotation labels")

        # ── Decide badge / run rescue ──
        if encoding_errors:
            print("\n  → Encoding issues found. Launching rescue pipeline...")
            rescue = run_rescue_pipeline(document_md, OUTPUT_PDF)
            rescue_applied = True

            for entry in rescue.rescue_log:
                print(f"    {entry}")

            if rescue.success:
                badge = rescue.badge
                rescue_tier = rescue.tier_reached
                compile_ok = True
                print(f"  ✓ Rescue succeeded at Tier {rescue_tier}.")
            else:
                badge = rescue.badge
                rescue_tier = rescue.tier_reached
                print("  ✗ Rescue exhausted all tiers.")
        elif leak_errors:
            badge = "Warning"
        # else: badge stays "OK"
    else:
        # Compilation failed entirely — run full rescue pipeline
        print("  → Initial compilation failed. Launching rescue pipeline...")
        rescue = run_rescue_pipeline(document_md, OUTPUT_PDF)
        rescue_applied = True

        for entry in rescue.rescue_log:
            print(f"    {entry}")

        if rescue.success:
            badge = rescue.badge
            rescue_tier = rescue.tier_reached
            compile_ok = True
            print(f"  ✓ Rescue succeeded at Tier {rescue_tier}.")
        else:
            badge = rescue.badge
            rescue_tier = rescue.tier_reached
            print("  ✗ Rescue exhausted all tiers.")

    # ═══════════════════════════════════════════════════════════════
    # Step 5: Final Report
    # ═══════════════════════════════════════════════════════════════
    _step(5, 5, "Summary")

    pdf_exists = os.path.exists(OUTPUT_PDF)

    if pdf_exists and compile_ok:
        final_size = os.path.getsize(OUTPUT_PDF)

        if badge == "OK":
            icon = "✅"
            status = "PDF generated and fully validated"
        elif badge == "Warning":
            icon = "⚠️ "
            status = "PDF generated with informational warnings"
        else:
            icon = "⛔"
            status = "PDF generated with critical warnings"

        print(f"\n  {icon} {status}")
        print(f"  Badge   : {badge}")
        if rescue_applied:
            print(f"  Rescue  : Tier {rescue_tier} applied")
        print(f"  Output  : {OUTPUT_PDF} ({final_size:,} bytes)")

        # Show a snippet of extracted Vietnamese text as proof
        if compile_ok and validation and validation.extracted_text:
            snippet = validation.extracted_text[:200].replace("\n", " ").strip()
            print(f"\n  Text preview:")
            print(f"    \"{snippet}...\"")
    else:
        print(f"\n  ⛔ No valid PDF was produced.")
        print(f"  Badge   : Critical Warning")

    print(f"\n{SEPARATOR}")
    print("  Demo complete.")
    print(f"{SEPARATOR}\n")

    return 0 if (pdf_exists and compile_ok) else 1


if __name__ == "__main__":
    sys.exit(main())
