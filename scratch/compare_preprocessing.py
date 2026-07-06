import os
import cv2
import pytesseract

def test_preprocessing_methods(image_path: str):
    if not os.path.exists(image_path):
        print(f"Error: {image_path} does not exist.")
        return

    # Load image
    img = cv2.imread(image_path)
    
    # Method 1: Grayscale + 2x Resize
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    r1 = cv2.resize(gray, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
    
    # Method 2: Contrast Limited Adaptive Histogram Equalization (CLAHE) + 2x Resize
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
    cl = clahe.apply(gray)
    r2 = cv2.resize(cl, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
    
    # Method 3: Thresholding (Otsu's binarization) + 2x Resize
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    r3 = cv2.resize(thresh, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)

    methods = {
        "Grayscale + 2x": r1,
        "CLAHE + 2x": r2,
        "Otsu Binarization + 2x": r3
    }
    
    for name, processed_img in methods.items():
        data = pytesseract.image_to_data(processed_img, output_type=pytesseract.Output.DICT)
        n_boxes = len(data['text'])
        detected_texts = []
        for i in range(n_boxes):
            text = data['text'][i].strip()
            try:
                conf = float(data['conf'][i])
            except ValueError:
                conf = 0.0
            if text and conf >= 0:
                detected_texts.append(text)
        
        # Deduplicate and sort
        unique_texts = sorted(list(set([t for t in detected_texts if len(t) > 2])))
        print(f"\n--- Method: {name} ---")
        print(f"Total tokens detected: {len(detected_texts)}")
        print(f"Sample words detected: {unique_texts[:25]}")
        
        # Check specific targets
        targets = ["Gate", "Security", "Inbound", "Outbound", "Processing", "Aisle", "Staging", "Utility", "Shipping"]
        found = [t for t in targets if any(t.lower() in w.lower() for w in unique_texts)]
        print(f"Target words found: {found}")

if __name__ == "__main__":
    test_preprocessing_methods("temp/example.jpg")
