import os
import cv2
import pytesseract
from PIL import Image

def test_improved_ocr(image_path: str):
    if not os.path.exists(image_path):
        print(f"Error: {image_path} does not exist.")
        return

    # 1. Read with OpenCV
    cv_img = cv2.imread(image_path)
    # Convert to grayscale
    gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
    # Upscale 2x for small text
    resized = cv2.resize(gray, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
    
    # Run Tesseract with --psm 12
    data = pytesseract.image_to_data(resized, config='--psm 12', output_type=pytesseract.Output.DICT)
    
    n_boxes = len(data['text'])
    words = []
    
    for i in range(n_boxes):
        text = data['text'][i].strip()
        try:
            conf = float(data['conf'][i])
        except ValueError:
            conf = 0.0
            
        if not text or conf < 30:
            continue
            
        # Filter noise and non-alphanumeric bridges (dashes, arrows, borders)
        if not any(char.isalnum() for char in text):
            continue
            
        # Map back coordinates (divide by 2.0)
        words.append({
            'text': text,
            'x': int(data['left'][i] / 2.0),
            'y': int(data['top'][i] / 2.0),
            'w': int(data['width'][i] / 2.0),
            'h': int(data['height'][i] / 2.0),
            'conf': conf
        })

    # 2. 2D Spatial Clustering
    # Sort words left-to-right
    words.sort(key=lambda w: w['x'])
    
    clusters = []
    for word in words:
        merged = False
        for cluster in clusters:
            last = cluster[-1]
            
            # Check vertical overlap
            overlap = min(last['y'] + last['h'], word['y'] + word['h']) - max(last['y'], word['y'])
            min_h = min(last['h'], word['h'])
            same_line = overlap >= min_h * 0.45
            
            # Check y-center distance
            last_y_center = last['y'] + last['h'] / 2.0
            word_y_center = word['y'] + word['h'] / 2.0
            same_line_fallback = abs(last_y_center - word_y_center) <= min_h * 0.4
            
            if same_line or same_line_fallback:
                # Check horizontal distance
                dist = word['x'] - (last['x'] + last['w'])
                max_dist = max(last['h'], word['h']) * 1.8
                max_dist = max(max_dist, 40)  # strict limit
                
                # Allow minor overlap (negative distance)
                if dist >= -15 and dist <= max_dist:
                    cluster.append(word)
                    merged = True
                    break
        
        if not merged:
            clusters.append([word])
            
    # Format and merge
    merged_results = []
    for cluster in clusters:
        cluster.sort(key=lambda w: w['x'])
        merged_text = " ".join([w['text'] for w in cluster])
        min_x = min([w['x'] for w in cluster])
        min_y = min([w['y'] for w in cluster])
        max_r = max([w['x'] + w['w'] for w in cluster])
        max_b = max([w['y'] + w['h'] for w in cluster])
        
        merged_results.append({
            "text": merged_text,
            "boundingBox": {
                "x": min_x,
                "y": min_y,
                "width": max_r - min_x,
                "height": max_b - min_y
            }
        })
        
    print(f"Detected {len(merged_results)} merged labels:")
    for item in sorted(merged_results, key=lambda item: (item['boundingBox']['y'], item['boundingBox']['x'])):
        print(f" - '{item['text']}' at {item['boundingBox']}")

if __name__ == "__main__":
    test_improved_ocr("temp/example.jpg")
