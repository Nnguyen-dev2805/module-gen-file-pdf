import unittest
import os
import sys
from PIL import Image, ImageDraw, ImageFont

# Ensure src/ is in the python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.image_translator import detect_text_coordinates_easyocr

class TestEasyOCR(unittest.TestCase):

    def setUp(self):
        os.makedirs("temp", exist_ok=True)
        self.test_img_path = "temp/test_easyocr_canvas.png"

    def tearDown(self):
        if os.path.exists(self.test_img_path):
            try:
                os.remove(self.test_img_path)
            except OSError:
                pass

    def test_detect_text_coordinates_easyocr(self):
        # Create a simple white canvas (600x200) and draw distinct English text
        img = Image.new("RGB", (600, 200), "#FFFFFF")
        draw = ImageDraw.Draw(img)
        
        # Load a default font
        font = ImageFont.load_default()
        
        # Draw bold-like text in black
        draw.text((100, 80), "ASRS Storage", fill="#000000", font=font)
        img.save(self.test_img_path)

        ocr_results = detect_text_coordinates_easyocr(self.test_img_path)
        
        # Verify result structure
        self.assertIsInstance(ocr_results, list)
        
        for item in ocr_results:
            self.assertIn("text", item)
            self.assertIn("boundingBox", item)
            bbox = item["boundingBox"]
            self.assertIn("x", bbox)
            self.assertIn("y", bbox)
            self.assertIn("width", bbox)
            self.assertIn("height", bbox)
            
            # Verify data types
            self.assertIsInstance(item["text"], str)
            self.assertIsInstance(bbox["x"], int)
            self.assertIsInstance(bbox["y"], int)
            self.assertIsInstance(bbox["width"], int)
            self.assertIsInstance(bbox["height"], int)
            
        print(f"\nEasyOCR test results: {ocr_results}")

if __name__ == "__main__":
    unittest.main()
