import os
import cv2
import pytesseract

def test_psm_modes(image_path: str):
    if not os.path.exists(image_path):
        print(f"Error: {image_path} does not exist.")
        return

    # Load image, convert to grayscale, upscale 2x
    img = cv2.imread(image_path)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    resized = cv2.resize(gray, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)

    psm_modes = [3, 11, 12]
    
    for psm in psm_modes:
        config = f"--psm {psm}"
        data = pytesseract.image_to_data(resized, config=config, output_type=pytesseract.Output.DICT)
        n_boxes = len(data['text'])
        detected_texts = []
        for i in range(n_boxes):
            text = data['text'][i].strip()
            try:
                conf = float(data['conf'][i])
            except ValueError:
                conf = 0.0
            if text and conf >= 15: # lower confidence filter slightly to see candidates
                detected_texts.append(text)
                
        unique_texts = sorted(list(set([t for t in detected_texts if len(t) > 2])))
        print(f"\n--- PSM Mode: {psm} ---")
        print(f"Total tokens detected: {len(detected_texts)}")
        
        # Check specific targets
        targets = ["Gate", "Security", "Inbound", "Outbound", "Processing", "Aisle", "Staging", "Utility", "Shipping", "Paths"]
        found = [t for t in targets if any(t.lower() in w.lower() for w in unique_texts)]
        print(f"Target words found: {found}")
        print(f"Sample words detected: {unique_texts[:30]}")

if __name__ == "__main__":
    test_psm_modes("temp/example.jpg")
