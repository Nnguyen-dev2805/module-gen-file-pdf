import os
import re
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from typing import List, Dict, Any
import pytesseract

from src.mock_adapters import detect_text, translate_text, MOCK_OCR_DATA


def create_mock_warehouse_image(output_path: str) -> None:
    """
    Generates a mock warehouse layout diagram image containing the English annotations
    at their expected mock coordinates. This allows tests to run on a real file.
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    # Create a light gray background image (1000x900)
    img = Image.new("RGB", (1000, 900), "#E0E0E0")
    draw = ImageDraw.Draw(img)

    # Draw rack aisles (blue boxes)
    draw.rectangle([380, 100, 620, 320], fill="#D0E0F0", outline="#1A5276", width=2)
    draw.text((460, 200), "ASRS Rack Area", fill="#1A5276")

    # Draw process boxes
    draw.rectangle([210, 390, 390, 520], fill="#EAFAF1", outline="#27AE60", width=2)
    draw.rectangle([630, 390, 810, 520], fill="#FDEDEC", outline="#CB4335", width=2)

    # Load standard sans-serif font
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None

    # Draw the mock text annotations at the exact bounding box coordinates
    for item in MOCK_OCR_DATA:
        bbox = item["boundingBox"]
        text = item["text"]
        
        # Draw background patch (simulating the diagram's label tags)
        # We color-code: Inbound (green), Outbound (red), general (blue/gray)
        fill_color = "#E5E7E9"
        text_color = "#2C3E50"
        
        if "Inbound" in text:
            fill_color = "#27AE60"
            text_color = "#FFFFFF"
        elif "Outbound" in text:
            fill_color = "#CB4335"
            text_color = "#FFFFFF"
        elif "ASRS" in text:
            fill_color = "#1F618D"
            text_color = "#FFFFFF"

        # Draw labeled box
        draw.rectangle(
            [bbox["x"], bbox["y"], bbox["x"] + bbox["width"], bbox["y"] + bbox["height"]],
            fill=fill_color,
            outline="#1C2833",
            width=1
        )
        
        # Draw text centered inside the box
        if font:
            text_w = draw.textlength(text, font=font)
            text_h = 10  # default height approx
            tx = bbox["x"] + (bbox["width"] - text_w) / 2
            ty = bbox["y"] + (bbox["height"] - text_h) / 2
            draw.text((tx, ty), text, fill=text_color, font=font)
            
    img.save(output_path)


def is_primarily_numeric(text: str) -> bool:
    """
    Checks if a string is primarily numeric (e.g. contains only digits, formatting symbols, commas, dots, slashes).
    Numbers are the same in English and Vietnamese, so we shouldn't translate or draw boxes over them.
    """
    # Remove common formatting symbols
    cleaned = re.sub(r'[\s,\.\-\(\)/+*=%$#@!~?\[\]{}]', '', text)
    return not cleaned or cleaned.isdigit()


def detect_text_coordinates_tesseract(image_path: str) -> List[Dict[str, Any]]:
    """
    Runs Tesseract OCR on the image at image_path and returns list of detected bounding boxes.
    Adjacent words on the same horizontal line are merged into single labels using 2D spatial clustering.
    """
    try:
        # Load image with OpenCV for preprocessing
        cv_img = cv2.imread(image_path)
        if cv_img is None:
            raise ValueError(f"Failed to load image for OCR: {image_path}")

        # Convert to grayscale and upscale 2x to detect small and low-contrast diagram text
        gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
        resized = cv2.resize(gray, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)

        data = pytesseract.image_to_data(resized, output_type=pytesseract.Output.DICT)
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
                
            # Filter out primarily numeric values (numbers are the same anyway)
            if is_primarily_numeric(text):
                continue
                
            # Map back coordinates (divide by 2.0 to restore original scale)
            words.append({
                'text': text,
                'x': int(data['left'][i] / 2.0),
                'y': int(data['top'][i] / 2.0),
                'w': int(data['width'][i] / 2.0),
                'h': int(data['height'][i] / 2.0)
            })
            
        # 2D Spatial Clustering (ignores Tesseract's noisy column/paragraph logic)
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
                
                # Also check center-to-center distance as fallback
                last_y_center = last['y'] + last['h'] / 2.0
                word_y_center = word['y'] + word['h'] / 2.0
                same_line_fallback = abs(last_y_center - word_y_center) <= min_h * 0.4
                
                if same_line or same_line_fallback:
                    # Check horizontal distance
                    dist = word['x'] - (last['x'] + last['w'])
                    max_dist = max(last['h'], word['h']) * 1.8
                    max_dist = max(max_dist, 40)  # strict limit to prevent cross-zone merges
                    
                    if dist >= -15 and dist <= max_dist:
                        cluster.append(word)
                        merged = True
                        break
            
            if not merged:
                clusters.append([word])
                
        # Format and merge labels
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
        return merged_results
    except Exception as e:
        print(f"Warning: Tesseract OCR failed ({e}). Returning empty list.")
        return []


_EASYOCR_READER = None

def get_easyocr_reader():
    global _EASYOCR_READER
    if _EASYOCR_READER is None:
        import ssl
        # Bypass SSL verification issues on macOS for model downloads
        try:
            ssl._create_default_https_context = ssl._create_unverified_context
        except AttributeError:
            pass
        import easyocr
        # Set gpu=True; easyocr will auto-fallback to CPU if not supported and load both English and Vietnamese models
        _EASYOCR_READER = easyocr.Reader(['en', 'vi'], gpu=True)
    return _EASYOCR_READER


def detect_text_coordinates_easyocr(image_path: str) -> List[Dict[str, Any]]:
    """
    Runs EasyOCR on the image at image_path and returns a list of detected bounding boxes.
    Filters noise and groups adjacent words using 2D spatial clustering.
    """
    try:
        reader = get_easyocr_reader()
        # readtext returns a list of tuples: (bbox, text, conf)
        # where bbox is [[x, y], [x, y], [x, y], [x, y]] (clockwise starting top-left)
        results = reader.readtext(image_path)
        
        words = []
        for bbox, text, conf in results:
            text = text.strip()
            # EasyOCR confidence is 0.0 to 1.0. We use 0.3 threshold.
            if not text or conf < 0.3:
                continue
                
            # Filter noise and non-alphanumeric bridges (dashes, arrows, borders)
            if not any(char.isalnum() for char in text):
                continue
                
            # Filter out primarily numeric values (numbers are the same anyway)
            if is_primarily_numeric(text):
                continue
                
            x1, y1 = int(bbox[0][0]), int(bbox[0][1])
            x2, y2 = int(bbox[2][0]), int(bbox[2][1])
            
            words.append({
                'text': text,
                'x': x1,
                'y': y1,
                'w': x2 - x1,
                'h': y2 - y1
            })
            
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
                
                # Also check center-to-center distance as fallback
                last_y_center = last['y'] + last['h'] / 2.0
                word_y_center = word['y'] + word['h'] / 2.0
                same_line_fallback = abs(last_y_center - word_y_center) <= min_h * 0.4
                
                if same_line or same_line_fallback:
                    # Check horizontal distance
                    dist = word['x'] - (last['x'] + last['w'])
                    max_dist = max(last['h'], word['h']) * 1.8
                    max_dist = max(max_dist, 40)  # strict limit to prevent cross-zone merges
                    
                    if dist >= -15 and dist <= max_dist:
                        cluster.append(word)
                        merged = True
                        break
            
            if not merged:
                clusters.append([word])
                
        # Format and merge labels
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
        return merged_results
    except Exception as e:
        print(f"Warning: EasyOCR failed ({e}). Returning empty list.")
        return []


def translate_image_annotations(image_path: str, output_path: str, client = None) -> None:
    """
    Translates English annotations inside an image to Vietnamese.
    1. Resolves mock image paths to a local deterministic image.
    2. Runs Tesseract OCR to detect text bounding boxes dynamically.
    3. Erases original English text areas using OpenCV (background color matching).
    4. Overlays translated Vietnamese text using Pillow with Roboto font and auto-scaling.
    """
    if client is None:
        from src.llm_client import OpenCodeClient
        client = OpenCodeClient()

    # 1. Resolve mock image paths
    is_mock = image_path.startswith("mock://") or not os.path.exists(image_path)
    local_input_path = image_path
    
    if is_mock:
        # Create the mock warehouse layout image locally for testing.
        local_input_path = "temp/mock_warehouse_source.png"
        create_mock_warehouse_image(local_input_path)

    # 2. Run OCR to detect text bounding boxes dynamically
    if client.mock_mode:
        ocr_results = detect_text(local_input_path)
    else:
        ocr_results = detect_text_coordinates_easyocr(local_input_path)
        if not ocr_results:
            print("Warning: EasyOCR returned empty results. Falling back to mock OCR data.")
            ocr_results = detect_text(local_input_path)
    
    # 2. Load the image into OpenCV for text erasing (inpainting)
    cv_img = cv2.imread(local_input_path)
    if cv_img is None:
        raise ValueError(f"Failed to load image: {local_input_path}")
        
    h, w, c = cv_img.shape
    
    # Process each bounding box in OpenCV
    for item in ocr_results:
        bbox = item["boundingBox"]
        x, y, bw, bh = bbox["x"], bbox["y"], bbox["width"], bbox["height"]
        
        # Ensure coordinates are within image boundaries
        x = max(0, min(x, w - 1))
        y = max(0, min(y, h - 1))
        bw = max(1, min(bw, w - x))
        bh = max(1, min(bh, h - y))
        
        # Background color matching:
        # Sample pixels around the border of the bounding box to match the background color
        # We sample the top-left corner pixel of the box
        bg_color = cv_img[y, x]  # BGR order
        
        # Erase the text by drawing a solid rectangle of the background color
        cv2.rectangle(
            cv_img,
            (x, y),
            (x + bw, y + bh),
            color=(int(bg_color[0]), int(bg_color[1]), int(bg_color[2])),
            thickness=-1  # Solid fill
        )

    # Convert BGR CV2 image back to RGB PIL Image for typography rendering
    pil_img = Image.fromarray(cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(pil_img)
    
    # 3. Load Roboto font for Vietnamese overlay
    font_path = "fonts/Roboto-Bold.ttf"
    if not os.path.exists(font_path):
        # Fallback to Roboto-Regular if Bold is missing
        font_path = "fonts/Roboto-Regular.ttf"
    
    # 4. Contextual translation of labels in one batch call to prevent API spamming
    eng_texts = [item["text"] for item in ocr_results]
    if client.mock_mode:
        translations = {txt: translate_text(txt) for txt in eng_texts}
    else:
        translations = client.translate_labels(eng_texts)

    # Overlay Vietnamese translated text
    for item in ocr_results:
        bbox = item["boundingBox"]
        eng_text = item["text"]
        viet_text = translations.get(eng_text, eng_text)
        
        x, y, bw, bh = bbox["x"], bbox["y"], bbox["width"], bbox["height"]
        
        # Detect text color (Inbound/Outbound/ASRS boxes have white text, others dark)
        text_color = (44, 62, 80)  # default dark charcoal
        if any(keyword in eng_text for keyword in ["Inbound", "Outbound", "ASRS"]):
            text_color = (255, 255, 255)  # white text

        # Font auto-scaling loop to prevent overflow
        font_size = int(bh * 0.7)  # Start at 70% of box height
        font_size = max(8, font_size)
        
        font = None
        if os.path.exists(font_path):
            try:
                font = ImageFont.truetype(font_path, font_size)
                # Shrink font until it fits bounding box width
                while draw.textlength(viet_text, font=font) > bw * 0.95 and font_size > 8:
                    font_size -= 1
                    font = ImageFont.truetype(font_path, font_size)
            except Exception as e:
                print(f"Warning: Failed to load TrueType font ({e}). Using default.")
                font = None
                
        if font is None:
            # Fallback to default PIL font
            font = ImageFont.load_default()

        # Draw the text centered in the bounding box
        text_w = draw.textlength(viet_text, font=font)
        # Approximate text height from font size or bbox
        text_h = font_size if hasattr(font, "size") else 10
        
        tx = x + (bw - text_w) / 2
        ty = y + (bh - text_h) / 2
        
        draw.text((tx, ty), viet_text, fill=text_color, font=font)

    # Save translated image
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    pil_img.save(output_path)


def translate_markdown_images(markdown_content: str, output_dir: str = "temp", client = None) -> str:
    """
    Parses a markdown content string, detects all image tags, translates their annotations,
    saves the translated images to output_dir, and returns the modified markdown.
    """
    # Regex to capture markdown image syntax: ![Alt](image_path)
    # Allows spaces inside image brackets as resolved in implementation plan
    pattern = r'! \[(.*?)\] \((.*?)\)'
    
    def replace_image_tag(match):
        alt_text = match.group(1)
        image_path = match.group(2)
        
        # Clean image path
        image_path = image_path.strip()
        
        # Generate safe filename for translated image
        sanitized_filename = re.sub(r'[^a-zA-Z0-9_\.-]', '_', os.path.basename(image_path))
        if not sanitized_filename.endswith(".png"):
            # Ensure output is PNG for canvas overlays
            sanitized_filename = os.path.splitext(sanitized_filename)[0] + ".png"
            
        translated_image_name = f"translated_{sanitized_filename}"
        output_path = os.path.join(output_dir, translated_image_name)
        
        try:
            translate_image_annotations(image_path, output_path, client=client)
            # Return rewritten markdown tag pointing to the translated local path
            # Make path absolute or relative based on requirement
            return f"! [{alt_text}] ({output_path})"
        except Exception as e:
            # Image translation fallback: Use original image on failure
            print(f"Warning: Image translation failed for {image_path} ({e}). Using original.")
            return match.group(0)

    # Run regex replace
    return re.sub(pattern, replace_image_tag, markdown_content)
