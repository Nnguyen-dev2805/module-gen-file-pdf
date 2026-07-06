import os
import sys

# Ensure src/ is in the python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.llm_client import OpenCodeClient
from src.image_translator import detect_text_coordinates_tesseract

def print_translations():
    client = OpenCodeClient()
    image_path = "temp/example.jpg"
    
    print(f"Mock mode: {client.mock_mode}")
    ocr_results = detect_text_coordinates_tesseract(image_path)
    print(f"Detected {len(ocr_results)} labels:")
    for idx, item in enumerate(ocr_results):
        print(f" {idx}. text='{item['text']}' at {item['boundingBox']}")
        
    eng_texts = [item["text"] for item in ocr_results]
    translations = client.translate_labels(eng_texts)
    print("\nTranslations from OpenCode API:")
    for eng, vie in translations.items():
        print(f"  '{eng}' -> '{vie}'")

if __name__ == "__main__":
    print_translations()
