import unittest
import os
import sys
import unicodedata
from unittest.mock import patch

# Ensure src/ is in the python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.pdf_validator import (
    ValidationError,
    ValidationResult,
    RescueResult,
    run_rescue_pipeline,
    _rescue_tier1_nfc,
    _rescue_tier3_simplify,
    _rescue_tier4_plaintext,
)


class TestRescuePipeline(unittest.TestCase):
    """
    Integration tests for the 4-tier rescue pipeline.
    Verifies that rescue steps trigger in sequence, produce a valid PDF,
    and assign the correct warning badge.
    """

    def setUp(self):
        os.makedirs("temp", exist_ok=True)
        self.rescue_pdf = "temp/test_rescue_output.pdf"

    def tearDown(self):
        if os.path.exists(self.rescue_pdf):
            try:
                os.remove(self.rescue_pdf)
            except OSError:
                pass

    # ---------------------------------------------------------------
    # Test: Clean input needs no rescue → badge "OK"
    # ---------------------------------------------------------------
    def test_no_rescue_needed(self):
        md = (
            "# Báo cáo hoạt động kho hàng\n"
            "Hệ thống đang hoạt động ổn định.\n"
        )
        rescue = run_rescue_pipeline(md, self.rescue_pdf)

        self.assertTrue(rescue.success)
        self.assertEqual(rescue.tier_reached, 0)
        self.assertEqual(rescue.badge, "OK")
        self.assertTrue(os.path.exists(self.rescue_pdf))
        self.assertIn("No rescue needed", rescue.rescue_log[-1])

    # ---------------------------------------------------------------
    # Test: U+FFFD in markdown → Tier 1 fixes it → badge "Warning"
    # (This is the primary test requested by the task checklist)
    # ---------------------------------------------------------------
    def test_tier1_fixes_encoding_error(self):
        """Deliberately fail initial validation with U+FFFD and verify rescue."""
        md = (
            "# Lỗi mã hóa\n"
            "Văn bản có ký tự thay thế: \uFFFD trong dòng này.\n"
        )
        rescue = run_rescue_pipeline(md, self.rescue_pdf)

        # 1. Rescue steps trigger in sequence
        self.assertIn("Step 0: Initial compile and validation.", rescue.rescue_log[0])
        tier1_entries = [e for e in rescue.rescue_log if e.startswith("Tier 1:")]
        self.assertGreater(len(tier1_entries), 0, "Tier 1 should have been attempted")

        # 2. A PDF is successfully compiled and delivered
        self.assertTrue(rescue.success)
        self.assertTrue(os.path.exists(self.rescue_pdf))
        self.assertGreater(os.path.getsize(self.rescue_pdf), 100)

        # 3. The output contains a warning indicator
        self.assertEqual(rescue.tier_reached, 1)
        self.assertEqual(rescue.badge, "Warning")

    # ---------------------------------------------------------------
    # Test: Verify rescue log shows sequential execution order
    # ---------------------------------------------------------------
    def test_rescue_log_is_sequential(self):
        """Ensure log entries proceed Step 0 → Tier 1 → ... in order."""
        md = "# Test\nVăn bản có ký tự: \uFFFD.\n"
        rescue = run_rescue_pipeline(md, self.rescue_pdf)

        # Step 0 must come before Tier 1
        step0_idx = next(
            i for i, msg in enumerate(rescue.rescue_log) if "Step 0" in msg
        )
        tier1_idx = next(
            i for i, msg in enumerate(rescue.rescue_log) if "Tier 1" in msg
        )
        self.assertLess(step0_idx, tier1_idx, "Step 0 must precede Tier 1 in the log")

    # ---------------------------------------------------------------
    # Test: Force Tier 2 by mocking validate_pdf to fail twice
    # ---------------------------------------------------------------
    def test_tier2_font_fallback(self):
        """Simulate persistent encoding errors so rescue falls through to Tier 2."""
        md = "# Test\nĐây là văn bản tiếng Việt.\n"
        call_count = [0]

        def mock_validate(pdf_path):
            call_count[0] += 1
            # Fail for initial (call 1) and Tier 1 (call 2)
            if call_count[0] <= 2:
                result = ValidationResult(is_valid=False)
                result.errors = [ValidationError(
                    error_type="encoding",
                    message="Simulated encoding failure",
                    page_number=1,
                    detail="\uFFFD",
                )]
                return result
            # Succeed from Tier 2 onward
            return ValidationResult(is_valid=True, extracted_text="OK", page_count=1)

        with patch("src.pdf_validator.validate_pdf", side_effect=mock_validate):
            rescue = run_rescue_pipeline(md, self.rescue_pdf)

        self.assertTrue(rescue.success)
        self.assertEqual(rescue.tier_reached, 2)
        self.assertEqual(rescue.badge, "Warning")

        # Verify Tier 2 log entries exist
        tier2_entries = [e for e in rescue.rescue_log if "Tier 2" in e]
        self.assertGreater(len(tier2_entries), 0)

    # ---------------------------------------------------------------
    # Test: Force Tier 4 (Critical Warning) by failing tiers 1-3
    # ---------------------------------------------------------------
    def test_tier4_critical_warning(self):
        """Simulate failures through Tiers 1-3 so only Tier 4 succeeds."""
        md = "# Test\nĐây là văn bản tiếng Việt.\n"
        call_count = [0]

        # Calls: Step 0 (1), Tier 1 (1), Tier 2 (2 fonts), Tier 3 (3 fonts) = 7 calls
        # Tier 4 starts at call 8
        def mock_validate(pdf_path):
            call_count[0] += 1
            if call_count[0] <= 7:
                result = ValidationResult(is_valid=False)
                result.errors = [ValidationError(
                    error_type="encoding",
                    message="Simulated persistent failure",
                    page_number=1,
                )]
                return result
            return ValidationResult(is_valid=True, extracted_text="OK", page_count=1)

        with patch("src.pdf_validator.validate_pdf", side_effect=mock_validate):
            rescue = run_rescue_pipeline(md, self.rescue_pdf)

        self.assertTrue(rescue.success)
        self.assertEqual(rescue.tier_reached, 4)
        self.assertEqual(rescue.badge, "Critical Warning")

        # Verify all tiers were logged sequentially
        log_text = "\n".join(rescue.rescue_log)
        for tier_label in ["Step 0", "Tier 1", "Tier 2", "Tier 3", "Tier 4"]:
            self.assertIn(tier_label, log_text, f"{tier_label} should appear in rescue log")

    # ---------------------------------------------------------------
    # Test: Rescue delivers a valid PDF file on disk
    # ---------------------------------------------------------------
    def test_rescue_delivers_valid_pdf_file(self):
        md = "# Tiêu đề\nNội dung có lỗi: \uFFFD ở đây.\n"
        rescue = run_rescue_pipeline(md, self.rescue_pdf)

        self.assertTrue(rescue.success)
        self.assertTrue(os.path.exists(rescue.output_pdf_path))
        self.assertGreater(os.path.getsize(rescue.output_pdf_path), 100)
        self.assertIsNotNone(rescue.validation_result)
        self.assertTrue(rescue.validation_result.is_valid)


class TestTierHelpers(unittest.TestCase):
    """Unit tests for the individual tier transformation functions."""

    # ---- Tier 1 ----
    def test_tier1_normalizes_nfc(self):
        # Compose a Vietnamese character using NFD decomposition
        # "ắ" can be represented as NFD: a + combining breve + combining acute
        nfd_text = "Ti\u0065\u0302\u0301ng Vi\u0065\u0323\u0302t"
        result = _rescue_tier1_nfc(nfd_text)
        self.assertEqual(result, unicodedata.normalize("NFC", nfd_text))

    def test_tier1_strips_replacement_chars(self):
        text = "Hello \uFFFD World \uFFFD"
        result = _rescue_tier1_nfc(text)
        self.assertNotIn("\uFFFD", result)
        self.assertEqual(result, "Hello  World ")

    # ---- Tier 3 ----
    def test_tier3_removes_images(self):
        md = "# Title\n![Alt](image.png)\nParagraph."
        result = _rescue_tier3_simplify(md)
        self.assertNotIn("image.png", result)
        self.assertIn("Hình ảnh đã được lược bỏ", result)
        self.assertIn("Paragraph.", result)

    def test_tier3_converts_tables_to_text(self):
        md = (
            "| Khu vực | Sức chứa |\n"
            "|:---|:---|\n"
            "| Kho A | 100 |\n"
            "| Kho B | 200 |\n"
        )
        result = _rescue_tier3_simplify(md)
        self.assertNotIn("|", result)
        self.assertIn("Khu vực: Kho A", result)
        self.assertIn("Sức chứa: 200", result)

    # ---- Tier 4 ----
    def test_tier4_strips_all_formatting(self):
        md = (
            "# Heading\n"
            "**Bold** and *italic*.\n"
            "- List item\n"
            "1. Ordered item\n"
        )
        result = _rescue_tier4_plaintext(md)
        self.assertNotIn("#", result)
        self.assertNotIn("**", result)
        self.assertNotIn("*", result)
        self.assertIn("Bold", result)
        self.assertIn("italic", result)
        self.assertIn("List item", result)
        self.assertIn("Ordered item", result)

    def test_tier4_preserves_vietnamese_accents(self):
        md = (
            "# Tiêu đề\n"
            "Xin chào, đây là ký tự Việt: ắ, ằ, ẳ, ẵ, ặ, đ, ế, ề, ể, ễ, ệ.\n"
        )
        result = _rescue_tier4_plaintext(md)
        for char in ["ắ", "ằ", "ẳ", "ẵ", "ặ", "đ", "ế", "ề", "ể", "ễ", "ệ"]:
            self.assertIn(char, result, f"Vietnamese character '{char}' must be preserved")

    def test_tier4_removes_images(self):
        md = "Text before\n![Diagram](path/to/img.png)\nText after"
        result = _rescue_tier4_plaintext(md)
        self.assertNotIn("img.png", result)
        self.assertIn("Text before", result)
        self.assertIn("Text after", result)


if __name__ == "__main__":
    unittest.main()
