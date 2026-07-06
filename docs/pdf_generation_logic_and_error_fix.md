# Quy trình logic tạo PDF và cơ chế sửa lỗi

Tài liệu này chỉ tập trung vào flow logic tạo file PDF và cách project xử lý lỗi trong quá trình generate PDF.

## 1. Mục tiêu kỹ thuật

Mục tiêu của project là biến một prompt hoặc một nội dung Markdown thành file PDF tiếng Việt ổn định.

Các lỗi cần kiểm soát chính:

| Nhóm lỗi | Ví dụ | Cách project xử lý |
| :--- | :--- | :--- |
| Lỗi LLM/API | OpenCode timeout, API trả lỗi, response rỗng | Fallback về `MOCK_REPORT` |
| Lỗi Markdown | Bảng Markdown sai, image tag do model sinh không kiểm soát được | Ép prompt sinh Markdown chuẩn, xóa image tag do model sinh |
| Lỗi ảnh | Không muốn ảnh phụ thuộc vào LLM | Tách ảnh thành module riêng dùng `temp/example.jpg` |
| Lỗi Typst compile | Typst không compile được do syntax/layout | Chạy rescue pipeline |
| Lỗi font tiếng Việt | PDF có ký tự thay thế `�` | Validate bằng `pdfplumber`, rescue bằng NFC/font fallback |
| Lỗi nội dung tiếng Anh lọt vào | Label như `Truck Yard`, `Inbound Processing` xuất hiện trong PDF text | Validator báo `Warning` |

Flow tổng thể hiện tại:

```text
Prompt
  -> OpenCodeClient.generate_report()
  -> Markdown tiếng Việt
  -> Unicode NFC normalize
  -> prepare_report_image_section()
  -> Markdown có section ảnh riêng
  -> compile_pdf()
  -> validate_pdf()
  -> nếu compile fail hoặc lỗi encoding thì run_rescue_pipeline()
  -> PDF cuối cùng
```

## 2. Entry logic chính trong CLI demo

File liên quan:

```text
src/demo.py
```

Đây là flow end-to-end gọn nhất để hiểu toàn bộ logic tạo PDF. Tài liệu này chỉ phân tích logic core.

Các import chính:

```python
from src.llm_client import OpenCodeClient
from src.report_image import DEFAULT_SOURCE_IMAGE, prepare_report_image_section
from src.typst_generator import compile_pdf
from src.pdf_validator import (
    validate_pdf,
    run_rescue_pipeline,
)
```

Ý nghĩa:

| Module | Vai trò trong flow PDF |
| :--- | :--- |
| `OpenCodeClient` | Sinh Markdown tiếng Việt từ prompt |
| `prepare_report_image_section` | Tạo phần ảnh riêng từ `temp/example.jpg` |
| `compile_pdf` | Chuyển Markdown sang Typst rồi compile PDF |
| `validate_pdf` | Kiểm tra PDF sau compile |
| `run_rescue_pipeline` | Tự cứu khi compile/validate lỗi |

Trong `src/demo.py`, file output mặc định là:

```python
OUTPUT_DIR = "temp"
OUTPUT_PDF = os.path.join(OUTPUT_DIR, "demo_report.pdf")
```

Nghĩa là PDF demo sẽ nằm ở:

```text
temp/demo_report.pdf
```

## 3. Quy trình 1: Sinh Markdown bằng OpenCode

File liên quan:

```text
src/llm_client.py
```

Class chính:

```python
class OpenCodeClient:
```

### 3.1. Khởi tạo client

Code:

```python
self.opencode_api_key = os.environ.get("OPENCODE_API_KEY")
self.opencode_base_url = os.environ.get(
    "OPENCODE_BASE_URL",
    OPENCODE_DEFAULT_BASE_URL,
).rstrip("/")
self.opencode_model = os.environ.get("OPENCODE_MODEL", OPENCODE_DEFAULT_MODEL)
self.opencode_timeout = int(
    os.environ.get("OPENCODE_TIMEOUT", str(OPENCODE_DEFAULT_TIMEOUT))
)
```

Ý nghĩa:

| Biến | Mục đích |
| :--- | :--- |
| `OPENCODE_API_KEY` | API key để gọi OpenCode |
| `OPENCODE_BASE_URL` | Endpoint gốc của OpenCode |
| `OPENCODE_MODEL` | Model dùng để sinh text |
| `OPENCODE_TIMEOUT` | Thời gian chờ response, mặc định `300` giây |

Nếu có API key:

```python
if self.opencode_api_key:
    self.provider = "opencode"
    self.mock_mode = False
    self.api_status.append(f"Using OpenCode model: {self.opencode_model}")
```

Nếu không có API key:

```python
else:
    self.api_status.append("OpenCode API key missing (running in offline mock mode)")
```

Khi không có key, project không crash. Nó chuyển sang mock mode để vẫn có thể test logic PDF.

### 3.2. Gọi OpenCode API

Hàm:

```python
def _chat_completion(self, messages, temperature=0.2) -> str:
```

Code gửi request:

```python
response = requests.post(
    url,
    headers={
        "Authorization": f"Bearer {self.opencode_api_key}",
        "Content-Type": "application/json",
    },
    json={
        "model": self.opencode_model,
        "messages": messages,
        "temperature": temperature,
    },
    timeout=self.opencode_timeout,
)
```

Điểm quan trọng để fix lỗi:

| Vấn đề | Code xử lý |
| :--- | :--- |
| API trả non-JSON | Bắt `ValueError`, raise `RuntimeError` rõ message |
| API trả HTTP lỗi hoặc có field `error` | Raise `RuntimeError` |
| API không có `choices` | Raise `RuntimeError` |
| Content rỗng | Raise `RuntimeError` |
| Timeout | Exception nổi lên để `generate_report()` fallback |

Đoạn kiểm tra response:

```python
if response.status_code >= 400 or "error" in payload:
    error = payload.get("error", payload)
    ...
    raise RuntimeError(f"OpenCode API returned {response.status_code}: {message}")
```

Đoạn kiểm tra nội dung rỗng:

```python
content = str(content).strip()
if not content:
    raise RuntimeError("OpenCode API returned an empty message")
return content
```

### 3.3. Sinh báo cáo Markdown

Hàm:

```python
def generate_report(self, prompt: str) -> str:
```

Nếu mock mode:

```python
if self.mock_mode:
    return MOCK_REPORT
```

Nếu có OpenCode key, code tạo system prompt:

```python
system_prompt = (
    "Bạn là chuyên gia biên tập kỹ thuật. "
    "Hãy tạo báo cáo bằng Markdown tiếng Việt, rõ ràng, có cấu trúc. "
    "Bắt buộc có: tiêu đề H1, các đoạn văn giải thích, ít nhất một bảng Markdown "
    "đúng cú pháp, và danh sách gạch đầu dòng hoặc đánh số. "
    "Không bọc câu trả lời trong code fence. Hạn chế dùng cụm tiếng Anh nếu không cần thiết."
)
```

Mục tiêu của system prompt:

| Ràng buộc | Lý do |
| :--- | :--- |
| Markdown tiếng Việt | Typst converter đang nhận Markdown |
| Có tiêu đề H1 | PDF có cấu trúc |
| Có bảng Markdown đúng cú pháp | Test khả năng render bảng |
| Không code fence | Tránh Typst nhận nguyên block code thay vì nội dung |
| Hạn chế tiếng Anh | Giảm cảnh báo English leak |

Prompt người dùng được bọc thêm yêu cầu kỹ thuật:

```python
user_prompt = (
    f"{prompt}\n\n"
    "Yêu cầu đầu ra: trả về trực tiếp nội dung Markdown tiếng Việt để render PDF. "
    "Bảng Markdown nên có 2-4 cột và có hàng phân cách `| :--- |` hợp lệ."
)
```

Đây là một điểm fix lỗi quan trọng: nếu bảng Markdown thiếu dòng phân cách như:

```markdown
| Cột A | Cột B |
| Dữ liệu | Dữ liệu |
```

converter dễ hiểu sai bảng. Vì vậy prompt ép model tạo:

```markdown
| Cột A | Cột B |
| :--- | :--- |
| Dữ liệu | Dữ liệu |
```

### 3.4. Fallback khi OpenCode lỗi

Code:

```python
except Exception as e:
    self.api_status.append(f"OpenCode report generation failed: {e}")
    print(f"Warning: OpenCode API call failed ({e}). Falling back to mock report.")
    return MOCK_REPORT
```

Ý nghĩa:

Nếu OpenCode bị timeout hoặc lỗi, pipeline vẫn tiếp tục bằng `MOCK_REPORT`. Điều này giúp phần PDF generation, Typst compile, validate và rescue vẫn test được.

Lưu ý khi debug:

Nếu PDF vẫn được tạo nhưng nội dung không giống prompt vừa nhập, hãy kiểm tra log có dòng:

```text
OpenCode report generation failed
```

Nếu có, nghĩa là PDF đang dùng fallback mock.

## 4. Quy trình 2: Chuẩn hóa Unicode tiếng Việt

File liên quan:

```text
src/demo.py
```

Sau khi có Markdown từ OpenCode hoặc mock, code normalize Unicode:

```python
report_md = client.generate_report(prompt)
report_md = unicodedata.normalize("NFC", report_md)
```

Vì sao cần NFC?

Tiếng Việt có dấu có thể được biểu diễn theo nhiều cách Unicode:

| Dạng | Ví dụ |
| :--- | :--- |
| Composed | `ắ` là một ký tự hoàn chỉnh |
| Decomposed | `a` + dấu breve + dấu sắc |

Hai dạng nhìn giống nhau nhưng byte khác nhau. Nếu không normalize, khi extract text từ PDF hoặc so sánh lỗi, kết quả có thể không ổn định.

NFC giúp:

1. Gom ký tự tiếng Việt về dạng chuẩn.
2. Giảm rủi ro font/render bị lệch.
3. Giúp validator so sánh ổn định hơn.

## 5. Quy trình 3: Tách phần ảnh ra riêng

File liên quan:

```text
src/report_image.py
```

Ý tưởng hiện tại:

```text
Không để LLM quyết định ảnh trong PDF.
Code luôn dùng temp/example.jpg làm ảnh nguồn.
Code tự tạo temp/report_example_translated.png.
Code append section ảnh vào cuối Markdown.
```

Hàm chính được gọi trong flow:

```python
image_result = prepare_report_image_section(
    report_md,
    source_image_path=DEFAULT_SOURCE_IMAGE,
    output_dir=OUTPUT_DIR,
)
document_md = image_result.markdown
```

Trong đó:

```python
DEFAULT_SOURCE_IMAGE = os.path.join("temp", "example.jpg")
DEFAULT_OUTPUT_IMAGE_NAME = "report_example_translated.png"
```

Nghĩa là:

| File | Vai trò |
| :--- | :--- |
| `temp/example.jpg` | Ảnh nguồn |
| `temp/report_example_translated.png` | Ảnh đã xử lý để chèn vào PDF |

### 5.1. Vì sao phải tách ảnh riêng?

Trước đây, nếu model sinh image tag trong Markdown, project phải tin vào output của model:

```markdown
![Sơ đồ](some-path.png)
```

Rủi ro:

1. Model không sinh ảnh.
2. Model sinh sai đường dẫn.
3. Model sinh image tag sai cú pháp.
4. Ảnh không tồn tại khi Typst compile.
5. PDF compile fail vì đường dẫn ảnh lỗi.

Flow mới loại bỏ rủi ro này bằng cách:

```text
LLM chỉ sinh text và bảng.
Ảnh do code tự xử lý từ temp/example.jpg.
```

### 5.2. Xóa image tag do LLM sinh

Hàm:

```python
def strip_markdown_images(markdown_content: str) -> str:
```

Code:

```python
text = re.sub(r'!\s*\[.*?\]\s*\(.*?\)', '', markdown_content)
text = re.sub(r'\n{3,}', '\n\n', text)
return text.strip()
```

Ý nghĩa:

Nếu LLM sinh:

```markdown
![Ảnh minh họa](abc.png)
```

thì dòng đó sẽ bị xóa. Như vậy ảnh trong PDF luôn do module `report_image.py` kiểm soát.

### 5.3. Render ảnh đã xử lý

Hàm:

```python
def render_example_image_for_pdf(
    source_image_path: str = DEFAULT_SOURCE_IMAGE,
    output_dir: str = "temp",
    output_name: str = DEFAULT_OUTPUT_IMAGE_NAME,
) -> str:
```

Các bước:

1. Resolve path của `temp/example.jpg`.
2. Kiểm tra ảnh tồn tại.
3. Mở ảnh bằng Pillow.
4. Duyệt các label box cố định.
5. Vẽ rectangle đè lên label cũ.
6. Vẽ label tiếng Việt.
7. Lưu ảnh output dạng PNG.

Code kiểm tra ảnh nguồn:

```python
source_abs = _resolve_project_path(source_image_path)
if not os.path.exists(source_abs):
    raise FileNotFoundError(f"Source image not found: {source_image_path}")
```

Nếu ảnh nguồn mất, `prepare_report_image_section()` không làm crash toàn pipeline. Nó ghi log và trả Markdown đã strip image tag.

### 5.4. Tọa độ label

Danh sách tọa độ:

```python
EXAMPLE_LABEL_BOXES = [
    {"text": "Truck Yard", "box": (120, 86, 165, 48), ...},
    {"text": "Inbound Docks", "box": (278, 24, 225, 43), ...},
    ...
]
```

Các tọa độ này đo theo ảnh mẫu kích thước:

```text
1536x1024
```

Nếu ảnh nguồn đổi kích thước, code scale theo tỷ lệ:

```python
def _scaled_box(box, width, height):
    scale_x = width / 1536
    scale_y = height / 1024
    ...
```

Điều này giúp ảnh vẫn dùng được nếu kích thước thay đổi theo tỷ lệ.

### 5.5. Mapping label tiếng Anh sang tiếng Việt

Mapping:

```python
DEFAULT_TRANSLATIONS = {
    "Truck Yard": "Bãi xe tải",
    "Inbound Docks": "Cảng nhập",
    "ASRS Storage": "Kho ASRS",
    "Outbound Docks": "Cảng xuất",
    ...
}
```

Khi render:

```python
text = str(item["text"])
vietnamese_text = DEFAULT_TRANSLATIONS.get(text, text)
```

Nếu chưa có bản dịch trong map, code giữ nguyên text gốc. Vì vậy khi thêm label mới vào ảnh, cần thêm vào `DEFAULT_TRANSLATIONS`.

### 5.6. Auto-fit font trong ảnh

Hàm:

```python
def _fit_font(draw, text, box_width, box_height):
```

Logic:

```python
font_size = max(10, min(34, int(box_height * 0.55)))
while font_size > 9:
    font = _load_font(font_size)
    bbox = draw.textbbox((0, 0), text, font=font)
    width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]
    if width <= box_width * 0.9 and height <= box_height * 0.72:
        return font
    font_size -= 1
```

Mục tiêu:

1. Chữ tiếng Việt không tràn ra khỏi hộp.
2. Font tự giảm nếu label dài.
3. Ảnh output nhìn ổn hơn khi chèn vào PDF.

### 5.7. Append section ảnh vào Markdown

Hàm:

```python
def append_report_image_section(markdown_content: str, image_path: str) -> str:
```

Code:

```python
image_section = (
    "\n\n## Phụ lục hình ảnh minh họa\n\n"
    "Sơ đồ dưới đây được xử lý từ file ảnh nguồn `temp/example.jpg` "
    "và được chèn vào PDF như một phần riêng của báo cáo.\n\n"
    f"![Sơ đồ kho hàng đã xử lý]({image_path})\n"
)
```

Markdown cuối cùng sẽ có thêm:

```markdown
## Phụ lục hình ảnh minh họa

Sơ đồ dưới đây được xử lý từ file ảnh nguồn `temp/example.jpg`
và được chèn vào PDF như một phần riêng của báo cáo.

![Sơ đồ kho hàng đã xử lý](temp/report_example_translated.png)
```

Đây là chỗ ảnh được đưa vào PDF.

## 6. Quy trình 4: Chuyển Markdown sang Typst

File liên quan:

```text
src/typst_generator.py
```

Hàm chính:

```python
def convert_markdown_to_typst(markdown_text: str) -> str:
```

### 6.1. Chuyển heading

Markdown:

```markdown
# Tiêu đề
## Mục lớn
```

Typst:

```typst
= Tiêu đề
== Mục lớn
```

Code:

```python
header_match = re.match(r'^(#{1,6})\s+(.+)$', line)
...
if is_header:
    typst_lines.append(f"{'=' * level} {content}")
```

### 6.2. Chuyển danh sách

Markdown unordered list:

```markdown
- Mục A
- Mục B
```

Giữ nguyên:

```typst
- Mục A
- Mục B
```

Markdown ordered list:

```markdown
1. Bước một
2. Bước hai
```

Typst:

```typst
+ Bước một
+ Bước hai
```

Code:

```python
elif is_ol:
    typst_lines.append(f"+ {content}")
```

### 6.3. Chuyển bold và italic

Markdown:

```markdown
**đậm** và *nghiêng*
```

Typst:

```typst
*đậm* và _nghiêng_
```

Code:

```python
content = re.sub(r'(?<!\*)\*(?!\*)(.*?)(?<!\*)\*(?!\*)', r'_\1_', content)
content = re.sub(r'\*\*(.*?)\*\*', r'*\1*', content)
```

### 6.4. Chuyển ảnh

Markdown:

```markdown
![Sơ đồ kho hàng đã xử lý](temp/report_example_translated.png)
```

Typst:

```typst
#image("temp/report_example_translated.png", width: 90%)
```

Code:

```python
content = re.sub(
    r'!\s*\[(.*?)\]\s*\((.*?)\)',
    r'#image("\2", width: 90%)',
    content
)
```

Đây là chỗ section ảnh riêng được đưa vào PDF.

### 6.5. Chuyển bảng Markdown sang Typst table

Hàm:

```python
def convert_markdown_table_to_typst(markdown_table_lines: List[str]) -> str:
```

Input:

```markdown
| Hạng mục | Mô tả |
| :--- | :--- |
| Font | Roboto |
```

Output Typst:

```typst
#table(
  columns: (1fr, 1fr),
  align: (left, ) * 2,
  [* Hạng mục *],
  [* Mô tả *],
  [Font],
  [Roboto]
)
```

Các bước xử lý:

1. Duyệt từng dòng table.
2. Tách cell bằng ký tự `|`.
3. Bỏ cell rỗng đầu/cuối.
4. Bỏ dòng separator `| :--- | :--- |`.
5. Header row được bọc bold.
6. Data rows được đưa vào cell thường.

Code bỏ dòng separator:

```python
if parts and all(re.match(r'^:?-+:?$', p) for p in parts):
    continue
```

Điểm dễ lỗi:

Nếu LLM sinh table không đều số cột, code dùng:

```python
row_extended = row + [""] * (num_cols - len(row))
```

để padding cell thiếu. Nhưng nếu row thừa quá nhiều cột thì vẫn có thể làm Typst table lệch. Vì vậy prompt đã ép bảng 2-4 cột và cú pháp chuẩn.

## 7. Quy trình 5: Tạo Typst document

File liên quan:

```text
src/typst_generator.py
```

Hàm:

```python
def generate_typst_document(content_markdown, font_name="Roboto", simplified=False)
```

Nó làm 2 việc:

1. Gọi `convert_markdown_to_typst`.
2. Bọc nội dung vào template Typst.

### 7.1. Template bình thường

Template chính:

```typst
#set page(
  paper: "a4",
  margin: (x: 2cm, y: 2.5cm),
  header: align(right)[Báo cáo Kho hàng Thông minh],
  footer: context align(center)[Trang #counter(page).display("1 / 1", both: true)]
)

#set text(
  font: "Roboto",
  size: 11pt,
  lang: "vi",
  region: "vn",
  spacing: 120%
)

#set par(
  leading: 0.65em,
  justify: true
)
```

Các setting quan trọng:

| Setting | Ý nghĩa |
| :--- | :--- |
| `paper: "a4"` | PDF khổ A4 |
| `font: "Roboto"` | Font chính |
| `lang: "vi"` | Ngôn ngữ tiếng Việt |
| `region: "vn"` | Vùng Việt Nam |
| `justify: true` | Căn đều đoạn văn |

### 7.2. Template simplified

Khi rescue, `simplified=True` sẽ dùng layout đơn giản:

```typst
#set page(
  paper: "a4",
  margin: (x: 2.5cm, y: 3cm)
)

#set text(
  font: "{font_name}",
  size: 11pt,
  lang: "vi",
  region: "vn"
)
```

Nó bỏ:

1. Header.
2. Footer.
3. Justify.
4. Line spacing phức tạp.

Mục tiêu là giảm khả năng Typst lỗi layout.

## 8. Quy trình 6: Compile PDF bằng Typst

File liên quan:

```text
src/typst_generator.py
```

Hàm:

```python
def compile_pdf(content_markdown, output_pdf_path, font_name="Roboto", simplified=False)
```

Các bước:

### 8.1. Sinh Typst source

```python
typst_code = generate_typst_document(content_markdown, font_name, simplified)
```

### 8.2. Ghi file Typst tạm

```python
temp_typ_path = "temp_doc.typ"
with open(temp_typ_path, "w", encoding="utf-8") as f:
    f.write(typst_code)
```

Điểm quan trọng:

File được ghi bằng `utf-8`, giúp giữ tiếng Việt.

### 8.3. Chỉ định font paths

```python
font_dirs = ["fonts", "fonts/NotoSans", "fonts/DejaVuSans"]
```

Các font liên quan:

| Font | Vai trò |
| :--- | :--- |
| Roboto | Font chính |
| Noto Sans | Fallback |
| DejaVu Sans | Fallback |

### 8.4. Gọi Typst compile

```python
typst.compile(
    input=temp_typ_path,
    output=output_pdf_path,
    font_paths=font_dirs,
    ignore_system_fonts=True
)
```

Điểm quan trọng để fix lỗi font:

```python
ignore_system_fonts=True
```

Nghĩa là Typst chỉ dùng font trong project, không phụ thuộc font máy người chạy. Điều này làm kết quả ổn định hơn giữa các môi trường.

### 8.5. Dọn file tạm

```python
finally:
    if os.path.exists(temp_typ_path):
        os.remove(temp_typ_path)
```

Dù compile thành công hay lỗi, file tạm vẫn được xóa.

## 9. Quy trình 7: Validate PDF sau compile

File liên quan:

```text
src/pdf_validator.py
```

Hàm chính:

```python
def validate_pdf(pdf_path: str) -> ValidationResult:
```

Nó chạy 2 loại check:

```python
glyph_errors = check_missing_glyphs(pdf_path)
leak_errors = check_leaked_english(pdf_path)

result.errors = glyph_errors + leak_errors
result.is_valid = len(result.errors) == 0
```

### 9.1. Extract text từ PDF

Hàm:

```python
def extract_text(pdf_path: str) -> str:
```

Code:

```python
with pdfplumber.open(pdf_path) as pdf:
    for page in pdf.pages:
        text = page.extract_text() or ""
        pages_text.append(text)
full_text = "\n".join(pages_text)
return unicodedata.normalize("NFC", full_text)
```

Ý nghĩa:

1. Dùng `pdfplumber` để đọc text thực tế từ PDF.
2. Nếu PDF render lỗi font, text extract có thể có ký tự `�`.
3. Normalize NFC để so sánh tiếng Việt ổn định.

### 9.2. Check lỗi missing glyph

Hàm:

```python
def check_missing_glyphs(pdf_path: str) -> List[ValidationError]:
```

Lỗi cần bắt:

```text
U+FFFD: �
```

Code:

```python
if "\uFFFD" in text:
    count = text.count("\uFFFD")
    errors.append(ValidationError(
        error_type="encoding",
        message=f"Found {count} replacement character(s) (U+FFFD) on page {page_idx}. "
                f"This indicates missing glyphs or font encoding failures.",
        page_number=page_idx,
        detail=f"\uFFFD x{count}"
    ))
```

Nếu check này báo lỗi, nghĩa là PDF có vấn đề font/encoding thật sự. Khi đó pipeline cần rescue.

### 9.3. Check leaked English labels

Hàm:

```python
def check_leaked_english(pdf_path: str, labels=None) -> List[ValidationError]:
```

Danh sách check:

```python
ENGLISH_LEAK_LABELS = list(MOCK_TRANSLATION_MAP.keys())
```

Nếu text PDF còn các label như:

```text
Truck Yard
Inbound Processing
Outbound Processing
```

thì validator báo lỗi loại `leak`.

Lưu ý quan trọng:

Leak English là cảnh báo nội dung. Nó không nhất thiết là lỗi font. Trong flow hiện tại, nếu chỉ có leak error, app có thể gắn badge `Warning` nhưng PDF vẫn dùng được.

## 10. Quy trình 8: Rescue pipeline

File liên quan:

```text
src/pdf_validator.py
```

Hàm:

```python
def run_rescue_pipeline(content_markdown, output_pdf_path, font_name="Roboto") -> RescueResult:
```

Rescue pipeline dùng khi:

1. Compile ban đầu fail.
2. Compile được nhưng validate có lỗi encoding.

Mục tiêu là tạo được PDF tốt nhất có thể thay vì dừng ngay.

## 11. Rescue Step 0: Compile và validate ban đầu

Code:

```python
result = _try_compile_and_validate(content_markdown, output_pdf_path, font_name)

if result is not None and result.is_valid:
    rescue.success = True
    rescue.tier_reached = 0
    rescue.badge = "OK"
    rescue.validation_result = result
    rescue.rescue_log.append("Step 0: Passed. No rescue needed.")
    return rescue
```

Nếu Step 0 pass:

```text
Không cần rescue.
Badge = OK.
```

Nếu compile fail:

```python
rescue.rescue_log.append("Step 0: Compilation failed. Starting rescue.")
```

Nếu compile được nhưng validate fail:

```python
rescue.rescue_log.append(
    f"Step 0: Failed validation with {len(result.errors)} error(s). Starting rescue."
)
```

## 12. Rescue Tier 1: Unicode NFC normalization

Hàm:

```python
def _rescue_tier1_nfc(content: str) -> str:
```

Code:

```python
normalized = unicodedata.normalize("NFC", content)
normalized = normalized.replace("\uFFFD", "")
return normalized
```

Tier này xử lý:

1. Ký tự tiếng Việt decomposed.
2. Ký tự thay thế `�` đã có sẵn trong Markdown.

Sau khi normalize:

```python
result = _try_compile_and_validate(nfc_content, output_pdf_path, font_name)
```

Nếu pass:

```python
rescue.tier_reached = 1
rescue.badge = "Warning"
```

Vì đã phải rescue nên badge là `Warning`, dù PDF cuối hợp lệ.

## 13. Rescue Tier 2: Fallback fonts

Font chain:

```python
FALLBACK_FONT_CHAIN = ["Roboto", "Noto Sans", "DejaVu Sans"]
```

Code:

```python
for fallback_font in FALLBACK_FONT_CHAIN:
    if fallback_font == font_name:
        continue

    result = _try_compile_and_validate(nfc_content, output_pdf_path, fallback_font)
    if result is not None and result.is_valid:
        rescue.success = True
        rescue.tier_reached = 2
        rescue.badge = "Warning"
        ...
        return rescue
```

Tier này xử lý trường hợp:

1. Font chính thiếu glyph.
2. Font chính render tiếng Việt không ổn.
3. PDF extract ra `�`.

Nếu `Roboto` lỗi, pipeline thử `Noto Sans` hoặc `DejaVu Sans`.

## 14. Rescue Tier 3: Simplified layout

Hàm:

```python
def _rescue_tier3_simplify(content: str) -> str:
```

Tier này làm nội dung đơn giản hơn:

| Thành phần | Cách xử lý |
| :--- | :--- |
| Image tag | Thay bằng dòng ghi chú |
| Markdown table | Chuyển thành bullet text |
| Text thường | Giữ lại |

Ví dụ image:

```markdown
![Ảnh](temp/report_example_translated.png)
```

thành:

```markdown
_(Hình ảnh đã được lược bỏ trong chế độ đơn giản)_
```

Ví dụ table:

```markdown
| Khu vực | Vai trò |
| :--- | :--- |
| Kho A | Lưu trữ |
```

thành:

```markdown
- Khu vực: Kho A
- Vai trò: Lưu trữ
```

Sau đó compile bằng simplified Typst layout:

```python
result = _try_compile_and_validate(
    simple_content,
    output_pdf_path,
    font,
    simplified=True
)
```

Tier này xử lý:

1. Table phức tạp làm Typst lỗi.
2. Image path làm compile lỗi.
3. Layout header/footer/justify gây lỗi.

Nếu pass:

```python
rescue.tier_reached = 3
rescue.badge = "Warning"
```

## 15. Rescue Tier 4: Plain text fallback

Hàm:

```python
def _rescue_tier4_plaintext(content: str) -> str:
```

Tier này là fallback cuối cùng. Nó strip hầu hết Markdown, chỉ giữ nội dung text.

Các xử lý chính:

| Thành phần | Cách xử lý |
| :--- | :--- |
| Image | Xóa |
| Heading | Giữ text heading |
| Bold | Xóa marker `**` |
| Italic | Xóa marker `*` |
| Table | Chuyển cell thành text phân tách bằng dấu phẩy |
| List marker | Xóa marker |
| U+FFFD | Xóa |
| Unicode | Normalize NFC |

Code xóa image:

```python
text = re.sub(r'!\s*\[.*?\]\s*\(.*?\)', '', text)
```

Code giữ text heading:

```python
text = re.sub(r'^#{1,6}\s+(.+)$', r'\1', text, flags=re.MULTILINE)
```

Code normalize cuối:

```python
text = unicodedata.normalize("NFC", text)
text = text.replace("\uFFFD", "")
```

Nếu Tier 4 pass:

```python
rescue.tier_reached = 4
rescue.badge = "Critical Warning"
```

Vì sao là `Critical Warning`?

Vì PDF tạo được nhưng đã mất nhiều định dạng: bảng, ảnh, heading Markdown gốc. Đây là bản cứu hộ cuối cùng, không phải bản đẹp nhất.

## 16. Logic quyết định badge

Trong core flow:

| Tình huống | Badge |
| :--- | :--- |
| Compile và validate pass ngay | `OK` |
| Có leak English nhưng không có encoding error | `Warning` |
| Rescue Tier 1-3 thành công | `Warning` |
| Rescue Tier 4 thành công | `Critical Warning` |
| Rescue fail toàn bộ | `Critical Warning` |

Điểm cần nhớ:

```text
Encoding error là lỗi kỹ thuật cần rescue.
English leak thường là warning nội dung.
```

## 17. Những điểm fix lỗi PDF quan trọng trong code

### 17.1. Fallback khi LLM lỗi

File:

```text
src/llm_client.py
```

Code:

```python
except Exception as e:
    self.api_status.append(f"OpenCode report generation failed: {e}")
    return MOCK_REPORT
```

Tác dụng:

Không để API lỗi làm vỡ pipeline PDF.

### 17.2. Normalize Unicode NFC

File:

```text
src/demo.py
src/pdf_validator.py
src/pdf_validator.py rescue tier 1
```

Code:

```python
unicodedata.normalize("NFC", text)
```

Tác dụng:

Giảm lỗi tiếng Việt do Unicode decomposed.

### 17.3. Tách ảnh khỏi output của LLM

File:

```text
src/report_image.py
```

Code:

```python
strip_markdown_images(markdown_content)
append_report_image_section(markdown_content, image_path)
```

Tác dụng:

Tránh lỗi compile PDF do image tag hoặc image path model tự sinh.

### 17.4. Dùng font local

File:

```text
src/typst_generator.py
```

Code:

```python
font_dirs = ["fonts", "fonts/NotoSans", "fonts/DejaVuSans"]
ignore_system_fonts=True
```

Tác dụng:

Giảm phụ thuộc vào font hệ điều hành.

### 17.5. Validate bằng PDF text extraction

File:

```text
src/pdf_validator.py
```

Code:

```python
if "\uFFFD" in text:
    ...
```

Tác dụng:

Phát hiện lỗi font/encoding sau khi PDF thật đã được render.

### 17.6. Rescue 4 tầng

File:

```text
src/pdf_validator.py
```

Tác dụng:

Tự động thử nhiều cách để vẫn tạo được PDF:

```text
NFC -> fallback fonts -> simplified layout -> plain text
```

## 18. Khi debug lỗi gen PDF thì xem theo thứ tự nào?

Nên debug theo thứ tự này:

### 18.1. Kiểm tra LLM có fallback không

Dấu hiệu:

```text
OpenCode report generation failed
```

Nếu có, nội dung PDF có thể đang là `MOCK_REPORT`.

### 18.2. Kiểm tra ảnh có được tạo không

File cần có:

```text
temp/report_example_translated.png
```

Nếu không có, kiểm tra:

```text
temp/example.jpg
```

### 18.3. Kiểm tra Typst compile có lỗi không

Nếu `compile_pdf()` raise exception, lỗi thường nằm ở:

1. Markdown chuyển sang Typst sai.
2. Image path không tồn tại.
3. Table syntax làm Typst fail.
4. Font không tìm thấy.

### 18.4. Kiểm tra validator

Nếu PDF compile được nhưng badge không OK:

1. Nếu lỗi `encoding`: xem có `U+FFFD` không.
2. Nếu lỗi `leak`: xem có label tiếng Anh không.

### 18.5. Kiểm tra rescue tier

Nếu rescue tier càng cao, nghĩa là lỗi càng nặng:

| Tier | Ý nghĩa |
| :--- | :--- |
| Tier 1 | Lỗi Unicode nhẹ |
| Tier 2 | Có thể do font |
| Tier 3 | Có thể do layout/table/image |
| Tier 4 | Nội dung quá khó compile, phải plain text |

## 19. Lệnh kiểm chứng core flow

Chạy toàn bộ test offline:

```bash
OPENCODE_API_KEY= POLLINATIONS_API_KEY= \
venv/bin/python -m unittest discover -s tests
```

Chạy CLI demo:

```bash
OPENCODE_API_KEY= POLLINATIONS_API_KEY= \
venv/bin/python src/demo.py
```

Kết quả cần thấy:

```text
Prepared report image from temp/example.jpg -> temp/report_example_translated.png
Compilation successful.
Encoding : No missing glyphs (U+FFFD)
```

Output cần kiểm tra:

```text
temp/demo_report.pdf
temp/report_example_translated.png
```

## 20. Tóm tắt ngắn nhất

Core logic sửa lỗi gen PDF nằm ở 5 điểm:

1. `OpenCodeClient.generate_report()` ép LLM trả Markdown chuẩn và fallback khi API lỗi.
2. `unicodedata.normalize("NFC", ...)` chuẩn hóa tiếng Việt trước khi compile/validate.
3. `prepare_report_image_section()` tách ảnh ra khỏi LLM, luôn dùng `temp/example.jpg`.
4. `compile_pdf()` dùng Typst với font local và `ignore_system_fonts=True`.
5. `validate_pdf()` và `run_rescue_pipeline()` phát hiện lỗi font/encoding rồi tự cứu theo 4 tier.

Flow cuối cùng:

```text
Markdown từ OpenCode/mock
  -> normalize NFC
  -> thêm ảnh đã xử lý từ temp/example.jpg
  -> Markdown sang Typst
  -> Typst compile PDF
  -> pdfplumber validate
  -> rescue nếu cần
  -> PDF cuối
```
