import unittest
import os
import sys

# Ensure src/ is in the python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.typst_generator import convert_markdown_to_typst, compile_pdf


class TestTypstGenerator(unittest.TestCase):

    def setUp(self):
        os.makedirs("temp", exist_ok=True)
        self.output_pdf = "temp/test_compile.pdf"

    def tearDown(self):
        if os.path.exists(self.output_pdf):
            try:
                os.remove(self.output_pdf)
            except OSError:
                pass

    def test_convert_markdown_elements(self):
        md = (
            "# Tiêu đề lớn\n"
            "## Tiêu đề phụ\n"
            "Đoạn văn này có chữ **đậm** và *nghiêng*.\n"
            "- Mục danh sách 1\n"
            "- Mục danh sách 2"
        )
        typst_code = convert_markdown_to_typst(md)
        
        self.assertIn("= Tiêu đề lớn", typst_code)
        self.assertIn("== Tiêu đề phụ", typst_code)
        self.assertIn("*đậm*", typst_code)
        self.assertIn("_nghiêng_", typst_code)
        self.assertIn("- Mục danh sách 1", typst_code)

    def test_convert_table(self):
        md_table = (
            "| Cột 1 | Cột 2 |\n"
            "|:---:|:---:|\n"
            "| Giá trị 1 | Giá trị 2 |"
        )
        typst_code = convert_markdown_to_typst(md_table)
        
        self.assertIn("#table(", typst_code)
        self.assertIn("columns: (1fr, 1fr)", typst_code)
        self.assertIn("[* Cột 1 *]", typst_code)
        self.assertIn("[Giá trị 1]", typst_code)

    def test_compile_pdf_vietnamese(self):
        md = (
            "# Thử nghiệm tài liệu tiếng Việt\n"
            "Xin chào, đây là văn bản chứa các nguyên âm tiếng Việt phức tạp: "
            "á, à, ả, ã, ạ, â, ấ, ầ, ẩ, ẫ, ậ, ă, ắ, ằ, ẳ, ẵ, ặ, đ, "
            "é, è, ẻ, ẽ, ẹ, ê, ế, ề, ể, ễ, ệ, í, ì, ỉ, ĩ, ị, "
            "ó, ò, ỏ, õ, ọ, ô, ố, ồ, ổ, ỗ, ộ, ơ, ớ, ờ, ở, ỡ, ợ, "
            "ú, ù, ủ, ũ, ụ, ư, ứ, ừ, ử, ữ, ự, ý, ỳ, ỷ, ỹ, ỵ.\n"
            "Hệ thống hoạt động ổn định."
        )
        
        # Compile PDF using local font Roboto
        compile_pdf(md, self.output_pdf, font_name="Roboto")
        
        self.assertTrue(os.path.exists(self.output_pdf))
        self.assertGreater(os.path.getsize(self.output_pdf), 100)  # Verify valid PDF file


if __name__ == "__main__":
    unittest.main()
