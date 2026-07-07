import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from PIL import Image, ImageDraw, ImageFont


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DEFAULT_SOURCE_IMAGE = os.path.join("temp", "example.jpg")
DEFAULT_OUTPUT_IMAGE_NAME = "report_example_translated.png"


@dataclass
class ImageSectionResult:
    markdown: str
    source_image_path: str = ""
    output_image_path: str = ""
    log: List[str] = field(default_factory=list)
    success: bool = False






def _resolve_project_path(path: str) -> str:
    if os.path.isabs(path):
        return path
    return os.path.join(PROJECT_ROOT, path)


def _load_font(size: int, bold: bool = True) -> ImageFont.ImageFont:
    candidates = []
    if bold:
        candidates.append(os.path.join(PROJECT_ROOT, "fonts", "Roboto", "Roboto-Bold.ttf"))
        candidates.append(os.path.join(PROJECT_ROOT, "fonts", "Roboto-Bold.ttf"))
    candidates.append(os.path.join(PROJECT_ROOT, "fonts", "Roboto", "Roboto-Regular.ttf"))
    candidates.append(os.path.join(PROJECT_ROOT, "fonts", "Roboto-Regular.ttf"))

    for path in candidates:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _fit_font(draw: ImageDraw.ImageDraw, text: str, box_width: int, box_height: int) -> ImageFont.ImageFont:
    font_size = max(10, min(34, int(box_height * 0.55)))
    while font_size > 9:
        font = _load_font(font_size)
        bbox = draw.textbbox((0, 0), text, font=font)
        width = bbox[2] - bbox[0]
        height = bbox[3] - bbox[1]
        if width <= box_width * 0.9 and height <= box_height * 0.72:
            return font
        font_size -= 1
    return _load_font(9)





def render_example_image_for_pdf(
    source_image_path: str = DEFAULT_SOURCE_IMAGE,
    output_dir: str = "temp",
    output_name: str = DEFAULT_OUTPUT_IMAGE_NAME,
    client = None,
) -> str:
    """
    Creates a PDF-ready image from the source image by running dynamic OCR
    and translating detected English labels to Vietnamese.
    """
    source_abs = _resolve_project_path(source_image_path)
    if not os.path.exists(source_abs):
        raise FileNotFoundError(f"Source image not found: {source_image_path}")

    output_path = os.path.join(output_dir, output_name)
    output_abs = _resolve_project_path(output_path)
    os.makedirs(os.path.dirname(output_abs), exist_ok=True)

    image = Image.open(source_abs).convert("RGB")
    draw = ImageDraw.Draw(image)
    image_width, image_height = image.size

    # Check mock mode status
    is_mock = True
    if client is not None:
        is_mock = client.mock_mode
    else:
        try:
            from src.llm_client import OpenCodeClient
            client = OpenCodeClient()
            is_mock = client.mock_mode
        except Exception:
            is_mock = True

    # DYNAMIC OCR: Use dynamic OCRProvider via get_ocr_provider factory
    from src.ocr_base import get_ocr_provider
    ocr_provider = get_ocr_provider(mock_mode=is_mock)
    ocr_results = ocr_provider.detect_text(source_abs)

    if not ocr_results:
        print(f"Warning: OCR returned empty results for {source_image_path}. Copying original image.")
    else:
        # Translate labels in batch
        eng_texts = [item["text"] for item in ocr_results]
        if is_mock:
            from src.mock_adapters import translate_text
            translations = {txt: translate_text(txt) for txt in eng_texts}
        else:
            translations = client.translate_labels(eng_texts)

        for item in ocr_results:
            bbox = item["boundingBox"]
            x, y, box_width, box_height = bbox["x"], bbox["y"], bbox["width"], bbox["height"]
            
            x = max(0, min(x, image_width - 1))
            y = max(0, min(y, image_height - 1))
            box_width = max(1, min(box_width, image_width - x))
            box_height = max(1, min(box_height, image_height - y))

            # Dynamic background pixel color sampling
            bg_pixel = image.getpixel((x, y))
            if isinstance(bg_pixel, int):
                r = g = b = bg_pixel
            elif len(bg_pixel) >= 3:
                r, g, b = bg_pixel[:3]
            else:
                r = g = b = 0
            
            # Luminance formula to dynamically decide text color
            luminance = 0.299 * r + 0.587 * g + 0.114 * b
            if luminance < 140:
                text_fill = "#FFFFFF"
            else:
                text_fill = "#111111"

            vietnamese_text = translations.get(item["text"], item["text"])
            
            # Erase and Draw the box with sampled background color
            radius = max(4, int(min(box_width, box_height) * 0.12))
            draw.rounded_rectangle(
                (x, y, x + box_width, y + box_height),
                radius=radius,
                fill=(r, g, b),
                outline="#D6D6D6",
                width=max(1, int(min(box_width, box_height) * 0.025)),
            )

            font = _fit_font(draw, vietnamese_text, box_width, box_height)
            text_bbox = draw.textbbox((0, 0), vietnamese_text, font=font)
            text_width = text_bbox[2] - text_bbox[0]
            text_height = text_bbox[3] - text_bbox[1]
            text_x = x + (box_width - text_width) / 2
            text_y = y + (box_height - text_height) / 2 - text_bbox[1]
            draw.text((text_x, text_y), vietnamese_text, fill=text_fill, font=font)

    image.save(output_abs, format="PNG", optimize=True)
    return output_path


def strip_markdown_images(markdown_content: str) -> str:
    """
    Removes any image tags produced by the LLM so image insertion is controlled
    by the dedicated image section.
    """
    text = re.sub(r'!\s*\[.*?\]\s*\(.*?\)', '', markdown_content)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def append_report_image_section(markdown_content: str, image_path: str, source_image_name: str = "example.jpg") -> str:
    clean_content = strip_markdown_images(markdown_content)
    image_section = (
        "\n\n## Phụ lục hình ảnh minh họa\n\n"
        f"Sơ đồ dưới đây được xử lý từ file ảnh nguồn `{source_image_name}` "
        "và được chèn vào PDF như một phần riêng của báo cáo.\n\n"
        f"![Sơ đồ kho hàng đã xử lý]({image_path})\n"
    )
    return f"{clean_content}{image_section}"


def prepare_report_image_section(
    markdown_content: str,
    source_image_path: str = DEFAULT_SOURCE_IMAGE,
    output_dir: str = "temp",
    output_name: str = DEFAULT_OUTPUT_IMAGE_NAME,
    client = None,
) -> ImageSectionResult:
    """
    Prepares the report image section and returns Markdown with that section appended.
    """
    result = ImageSectionResult(markdown=strip_markdown_images(markdown_content))
    result.source_image_path = source_image_path

    try:
        output_path = render_example_image_for_pdf(
            source_image_path=source_image_path,
            output_dir=output_dir,
            output_name=output_name,
            client=client,
        )
        result.output_image_path = output_path
        source_name = os.path.basename(source_image_path)
        result.markdown = append_report_image_section(markdown_content, output_path, source_name)
        result.success = True
        result.log.append(f"Prepared report image from {source_image_path} -> {output_path}")
    except Exception as exc:
        result.log.append(f"Skipped report image section: {exc}")

    return result
