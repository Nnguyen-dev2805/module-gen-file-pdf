import os
from typing import Protocol, List, TypedDict, Any, runtime_checkable

class BoundingBoxSchema(TypedDict):
    x: int
    y: int
    width: int
    height: int

class OCRResultSchema(TypedDict):
    text: str
    boundingBox: BoundingBoxSchema

@runtime_checkable
class OCRProvider(Protocol):
    def detect_text(self, image_path: str) -> List[OCRResultSchema]:
        """Detects text in the given image path and returns standardized bounding boxes and labels."""
        ...

def get_ocr_provider(mock_mode: bool = False) -> OCRProvider:
    """
    Factory function to return the configured OCRProvider.
    If mock_mode is True, returns MockOCRProvider.
    Otherwise, reads the OCR_PROVIDER env var to decide (defaults to 'easyocr').
    """
    if mock_mode:
        from src.mock_adapters import MockOCRProvider
        return MockOCRProvider()
    
    provider_name = os.environ.get("OCR_PROVIDER", "easyocr").lower()
    if provider_name == "mock":
        from src.mock_adapters import MockOCRProvider
        return MockOCRProvider()
    else:
        # Default is EasyOCR
        from src.image_translator import EasyOCRProvider
        return EasyOCRProvider()
