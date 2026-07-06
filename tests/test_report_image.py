import os
import sys
import unittest

from PIL import Image

# Ensure src/ is in the python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.report_image import (
    append_report_image_section,
    prepare_report_image_section,
    render_example_image_for_pdf,
    strip_markdown_images,
)


class TestReportImage(unittest.TestCase):

    def setUp(self):
        os.makedirs("temp", exist_ok=True)
        self.source_path = "temp/test_example_source.jpg"
        self.output_name = "test_report_example_translated.png"
        self.output_path = os.path.join("temp", self.output_name)

        image = Image.new("RGB", (1536, 1024), "#EEEEEE")
        image.save(self.source_path, format="JPEG")

    def tearDown(self):
        for path in [self.source_path, self.output_path]:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass

    def test_render_example_image_for_pdf(self):
        output = render_example_image_for_pdf(
            source_image_path=self.source_path,
            output_dir="temp",
            output_name=self.output_name,
        )

        self.assertEqual(output, self.output_path)
        self.assertTrue(os.path.exists(output))
        self.assertGreater(os.path.getsize(output), 0)

    def test_strip_markdown_images(self):
        markdown = "# Báo cáo\n\n![Alt](temp/example.jpg)\n\nNội dung."
        stripped = strip_markdown_images(markdown)

        self.assertNotIn("![Alt]", stripped)
        self.assertIn("Nội dung.", stripped)

    def test_append_report_image_section(self):
        markdown = "# Báo cáo\n\n![Old](mock://warehouse_layout.png)\n\nNội dung."
        result = append_report_image_section(markdown, "temp/report_example_translated.png")

        self.assertNotIn("mock://warehouse_layout.png", result)
        self.assertIn("## Phụ lục hình ảnh minh họa", result)
        self.assertIn("![Sơ đồ kho hàng đã xử lý](temp/report_example_translated.png)", result)

    def test_prepare_report_image_section(self):
        markdown = "# Báo cáo\n\nNội dung chính."
        result = prepare_report_image_section(
            markdown,
            source_image_path=self.source_path,
            output_dir="temp",
        )

        self.assertTrue(result.success)
        self.assertTrue(os.path.exists(result.output_image_path))
        self.assertIn("## Phụ lục hình ảnh minh họa", result.markdown)

    def test_render_example_image_for_pdf_dynamic(self):
        class MockClient:
            def __init__(self):
                self.mock_mode = False
            def translate_labels(self, labels):
                return {label: f"VIE_{label}" for label in labels}

        from unittest.mock import patch
        
        mock_ocr_results = [
            {"text": "Gate & Security", "boundingBox": {"x": 10, "y": 10, "width": 100, "height": 30}}
        ]

        with patch("src.image_translator.detect_text_coordinates_easyocr", return_value=mock_ocr_results):
            client = MockClient()
            output = render_example_image_for_pdf(
                source_image_path=self.source_path,
                output_dir="temp",
                output_name=self.output_name,
                client=client,
            )

            self.assertEqual(output, self.output_path)
            self.assertTrue(os.path.exists(output))
            self.assertGreater(os.path.getsize(output), 0)


if __name__ == "__main__":
    unittest.main()
