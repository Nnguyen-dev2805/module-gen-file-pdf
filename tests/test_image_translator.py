import unittest
import os
import sys
import re

# Ensure src/ is in the python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.image_translator import (
    create_mock_warehouse_image,
    translate_image_annotations,
    translate_markdown_images
)


class TestImageTranslator(unittest.TestCase):

    def setUp(self):
        # Create temp folder if not exists
        os.makedirs("temp", exist_ok=True)
        self.source_path = "temp/test_source_layout.png"
        self.output_path = "temp/test_output_layout.png"

    def tearDown(self):
        # Clean up test files if they exist
        for path in [self.source_path, self.output_path]:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass

    def test_create_mock_image(self):
        create_mock_warehouse_image(self.source_path)
        self.assertTrue(os.path.exists(self.source_path))
        self.assertGreater(os.path.getsize(self.source_path), 0)

    def test_translate_image_annotations(self):
        # Generate source
        create_mock_warehouse_image(self.source_path)
        
        # Translate
        translate_image_annotations(self.source_path, self.output_path)
        
        # Verify output exists
        self.assertTrue(os.path.exists(self.output_path))
        self.assertGreater(os.path.getsize(self.output_path), 0)

    def test_translate_markdown_images(self):
        mock_markdown = (
            "# Báo cáo hoạt động\n"
            "Dưới đây là sơ đồ:\n"
            "! [Sơ đồ kho hàng] (mock://warehouse_layout.png)\n"
            "Hết báo cáo."
        )
        
        modified_markdown = translate_markdown_images(mock_markdown, output_dir="temp")
        
        # Check replacement occurred
        self.assertNotIn("mock://warehouse_layout.png", modified_markdown)
        self.assertIn("temp/translated_warehouse_layout.png", modified_markdown)
        
        # Verify output file was generated
        self.assertTrue(os.path.exists("temp/translated_warehouse_layout.png"))
        
        # Cleanup translated test image
        if os.path.exists("temp/translated_warehouse_layout.png"):
            os.remove("temp/translated_warehouse_layout.png")
            
        # Clean up source image generated during replacement
        if os.path.exists("temp/mock_warehouse_source.png"):
            os.remove("temp/mock_warehouse_source.png")


if __name__ == "__main__":
    unittest.main()
