import unittest
import os
import sys

# Ensure src/ is in the python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.typst_generator import compile_pdf
from src.pdf_validator import (
    extract_text,
    check_missing_glyphs,
    check_leaked_english,
    validate_pdf,
    ValidationResult,
)


class TestPdfValidator(unittest.TestCase):

    def setUp(self):
        os.makedirs("temp", exist_ok=True)
        self.correct_pdf = "temp/test_valid.pdf"
        self.glyph_pdf = "temp/test_glyph_error.pdf"
        self.leak_pdf = "temp/test_leak_error.pdf"

        # 1. Compile a correct Vietnamese-only PDF
        correct_md = (
            "# Báo cáo hoạt động kho hàng\n"
            "Hệ thống đang hoạt động ổn định.\n"
            "Tất cả pallet đã được xếp đúng vị trí.\n"
        )
        compile_pdf(correct_md, self.correct_pdf, font_name="Roboto")

        # 2. Compile a PDF containing the Unicode replacement character (U+FFFD)
        glyph_md = (
            "# Lỗi mã hóa\n"
            "Văn bản có ký tự thay thế: \uFFFD trong dòng này.\n"
        )
        compile_pdf(glyph_md, self.glyph_pdf, font_name="Roboto")

        # 3. Compile a PDF containing a leaked English annotation label
        leak_md = (
            "# Sơ đồ kho hàng\n"
            "Khu vực Truck Yard chưa được dịch đúng.\n"
        )
        compile_pdf(leak_md, self.leak_pdf, font_name="Roboto")

    def tearDown(self):
        for path in [self.correct_pdf, self.glyph_pdf, self.leak_pdf]:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass

    # ---------------------------------------------------------------
    # Test 1: A correct PDF returns no errors
    # ---------------------------------------------------------------
    def test_correct_pdf_no_errors(self):
        result = validate_pdf(self.correct_pdf)

        self.assertIsInstance(result, ValidationResult)
        self.assertTrue(result.is_valid)
        self.assertEqual(len(result.errors), 0)
        self.assertGreater(len(result.extracted_text), 0)
        self.assertGreater(result.page_count, 0)

    # ---------------------------------------------------------------
    # Test 2: A PDF with injected U+FFFD returns an encoding error
    # ---------------------------------------------------------------
    def test_glyph_error_detected(self):
        errors = check_missing_glyphs(self.glyph_pdf)

        self.assertGreater(len(errors), 0)
        self.assertTrue(all(e.error_type == "encoding" for e in errors))
        self.assertIn("\uFFFD", errors[0].detail)

    def test_glyph_error_via_validate(self):
        result = validate_pdf(self.glyph_pdf)

        self.assertFalse(result.is_valid)
        encoding_errors = [e for e in result.errors if e.error_type == "encoding"]
        self.assertGreater(len(encoding_errors), 0)

    # ---------------------------------------------------------------
    # Test 3: A PDF containing "Truck Yard" returns a leak error
    # ---------------------------------------------------------------
    def test_leaked_english_detected(self):
        errors = check_leaked_english(self.leak_pdf)

        self.assertGreater(len(errors), 0)
        self.assertTrue(all(e.error_type == "leak" for e in errors))
        # Verify the specific leaked label was identified
        leaked_labels = [e.detail for e in errors]
        self.assertIn("Truck Yard", leaked_labels)

    def test_leaked_english_via_validate(self):
        result = validate_pdf(self.leak_pdf)

        self.assertFalse(result.is_valid)
        leak_errors = [e for e in result.errors if e.error_type == "leak"]
        self.assertGreater(len(leak_errors), 0)

    # ---------------------------------------------------------------
    # Utility: extract_text returns NFC-normalized content
    # ---------------------------------------------------------------
    def test_extract_text_returns_content(self):
        text = extract_text(self.correct_pdf)
        self.assertIsInstance(text, str)
        self.assertGreater(len(text), 0)
        # Verify Vietnamese content is present
        self.assertIn("hoạt động", text.lower().replace("\n", " "))

    # ---------------------------------------------------------------
    # Edge case: correct PDF has no leaked English labels
    # ---------------------------------------------------------------
    def test_correct_pdf_no_leaked_english(self):
        errors = check_leaked_english(self.correct_pdf)
        self.assertEqual(len(errors), 0)


if __name__ == "__main__":
    unittest.main()
