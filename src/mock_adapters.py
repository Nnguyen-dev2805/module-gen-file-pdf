import os
from typing import Dict, List, Any
from src.ocr_base import OCRResultSchema

# Standard mock translation lookup
MOCK_TRANSLATION_MAP: Dict[str, str] = {
    "Truck Yard": "Bãi đỗ xe tải",
    "Inbound Docks": "Cảng nhập hàng",
    "100 Pallets": "100 Pallet",
    "ASRS Storage": "Kho tự động ASRS",
    "(8,000 - 10,000 Pallets)": "(8.000 - 10.000 Pallet)",
    "Aisle 1": "Lối đi 1",
    "Aisle 2": "Lối đi 2",
    "Aisle 3": "Lối đi 3",
    "Aisle 5": "Lối đi 5",
    "Processing Area": "Khu vực xử lý",
    "Outbound Docks": "Cảng xuất hàng",
    "Shipping": "Vận chuyển",
    "Inbound Processing": "Xử lý hàng nhập",
    "Outbound Processing": "Xử lý hàng xuất",
    "Gate & Security": "Cổng & An ninh",
    "Staging Area": "Khu vực gom hàng",
    "Admin & ERP": "Hành chính & ERP",
    "WMS": "Hệ thống WMS",
    "AGV Paths": "Đường đi xe AGV",
    "Utility": "Khu tiện ích"
}

# Standard mock OCR labels and coordinates (x, y, width, height) representing the warehouse layout
MOCK_OCR_DATA: List[Dict[str, Any]] = [
    {"text": "Truck Yard", "boundingBox": {"x": 80, "y": 80, "width": 100, "height": 20}},
    {"text": "Inbound Docks", "boundingBox": {"x": 200, "y": 20, "width": 120, "height": 20}},
    {"text": "100 Pallets", "boundingBox": {"x": 200, "y": 42, "width": 120, "height": 20}},
    {"text": "ASRS Storage", "boundingBox": {"x": 390, "y": 15, "width": 230, "height": 20}},
    {"text": "(8,000 - 10,000 Pallets)", "boundingBox": {"x": 390, "y": 37, "width": 230, "height": 20}},
    {"text": "Aisle 1", "boundingBox": {"x": 395, "y": 62, "width": 50, "height": 15}},
    {"text": "Aisle 2", "boundingBox": {"x": 450, "y": 62, "width": 50, "height": 15}},
    {"text": "Aisle 3", "boundingBox": {"x": 505, "y": 62, "width": 50, "height": 15}},
    {"text": "Aisle 5", "boundingBox": {"x": 560, "y": 62, "width": 50, "height": 15}},
    {"text": "Processing Area", "boundingBox": {"x": 440, "y": 355, "width": 180, "height": 30}},
    {"text": "Outbound Docks", "boundingBox": {"x": 740, "y": 20, "width": 130, "height": 20}},
    {"text": "100 Pallets", "boundingBox": {"x": 740, "y": 42, "width": 130, "height": 20}},
    {"text": "Shipping", "boundingBox": {"x": 855, "y": 315, "width": 90, "height": 20}},
    {"text": "Inbound Processing", "boundingBox": {"x": 235, "y": 415, "width": 140, "height": 45}},
    {"text": "Outbound Processing", "boundingBox": {"x": 655, "y": 415, "width": 140, "height": 45}},
    {"text": "Gate & Security", "boundingBox": {"x": 20, "y": 555, "width": 100, "height": 45}},
    {"text": "Staging Area", "boundingBox": {"x": 350, "y": 660, "width": 130, "height": 25}},
    {"text": "Admin & ERP", "boundingBox": {"x": 615, "y": 595, "width": 150, "height": 25}},
    {"text": "WMS", "boundingBox": {"x": 735, "y": 660, "width": 75, "height": 25}},
    {"text": "AGV Paths", "boundingBox": {"x": 375, "y": 815, "width": 110, "height": 25}},
    {"text": "Utility", "boundingBox": {"x": 840, "y": 715, "width": 100, "height": 25}}
]


def detect_text(image_path: str) -> List[Dict[str, Any]]:
    """
    Simulates Google Cloud Vision OCR detection for a diagram image.
    Returns a list of dicts with bounding boxes and text labels.
    """
    if not image_path:
        raise ValueError("image_path is required")
    # For testing, we verify that the file actually exists if it's a real path
    if not os.path.exists(image_path) and not image_path.startswith("mock://"):
        raise FileNotFoundError(f"Diagram image file not found: {image_path}")
    
    # Return the static mock OCR annotations
    return MOCK_OCR_DATA


def translate_text(text: str) -> str:
    """
    Simulates Google Translate / Gemini contextual translation.
    Falls back to original text if no translation is found in the dictionary.
    """
    return MOCK_TRANSLATION_MAP.get(text, text)


class MockOCRProvider:
    def detect_text(self, image_path: str) -> List[OCRResultSchema]:
        """Returns mock OCR results, simulating OCR engine."""
        return detect_text(image_path)

