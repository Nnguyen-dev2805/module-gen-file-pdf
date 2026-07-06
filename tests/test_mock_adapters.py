import unittest
import os
import sys

# Ensure src/ is in the python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.mock_adapters import detect_text, translate_text, MOCK_OCR_DATA, MOCK_TRANSLATION_MAP


class TestMockAdapters(unittest.TestCase):

    def test_detect_text_success(self):
        # We can pass a mock URL/path starting with mock://
        result = detect_text("mock://warehouse_layout.png")
        self.assertEqual(len(result), len(MOCK_OCR_DATA))
        
        # Verify structure of first element
        first = result[0]
        self.assertIn("text", first)
        self.assertIn("boundingBox", first)
        bbox = first["boundingBox"]
        self.assertIn("x", bbox)
        self.assertIn("y", bbox)
        self.assertIn("width", bbox)
        self.assertIn("height", bbox)

    def test_detect_text_file_not_found(self):
        # Verify that passing a non-existent file raises FileNotFoundError
        with self.assertRaises(FileNotFoundError):
            detect_text("non_existent_file.png")

    def test_translate_text_dictionary(self):
        # Verify translations match dictionary
        for eng, vi in MOCK_TRANSLATION_MAP.items():
            self.assertEqual(translate_text(eng), vi)

    def test_translate_text_fallback(self):
        # Verify fallback to original text for unknown inputs
        unknown_text = "Random Unmapped Word"
        self.assertEqual(translate_text(unknown_text), unknown_text)


if __name__ == "__main__":
    unittest.main()
