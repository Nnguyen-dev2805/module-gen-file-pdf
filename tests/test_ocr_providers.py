import unittest
import os
import sys
from unittest.mock import patch

# Ensure src/ is in the python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.ocr_base import get_ocr_provider, OCRProvider
from src.mock_adapters import MockOCRProvider
from src.image_translator import EasyOCRProvider

class TestOCRProviders(unittest.TestCase):

    def test_mock_ocr_provider_conforms(self):
        provider = MockOCRProvider()
        # Verify that MockOCRProvider conforms to OCRProvider protocol interface
        self.assertTrue(isinstance(provider, OCRProvider))
        
        # Test with a mock image URL path
        results = provider.detect_text("mock://warehouse_layout.png")
        self.assertIsInstance(results, list)
        self.assertGreater(len(results), 0)
        
        first = results[0]
        self.assertIn("text", first)
        self.assertIn("boundingBox", first)
        bbox = first["boundingBox"]
        for key in ["x", "y", "width", "height"]:
            self.assertIn(key, bbox)
            self.assertIsInstance(bbox[key], int)

    def test_easy_ocr_provider_conforms(self):
        provider = EasyOCRProvider()
        self.assertTrue(isinstance(provider, OCRProvider))

    def test_factory_get_ocr_provider_mock_mode(self):
        # mock_mode=True should always return MockOCRProvider
        provider = get_ocr_provider(mock_mode=True)
        self.assertIsInstance(provider, MockOCRProvider)

    @patch.dict(os.environ, {"OCR_PROVIDER": "easyocr"})
    def test_factory_get_ocr_provider_env_easyocr(self):
        provider = get_ocr_provider(mock_mode=False)
        self.assertIsInstance(provider, EasyOCRProvider)

    @patch.dict(os.environ, {"OCR_PROVIDER": "mock"})
    def test_factory_get_ocr_provider_env_mock(self):
        provider = get_ocr_provider(mock_mode=False)
        self.assertIsInstance(provider, MockOCRProvider)

if __name__ == "__main__":
    unittest.main()
