# Vietnamese PDF Generation & Validation Engine

Dự án này là một công cụ (engine) tự động tạo báo cáo tiếng Việt dưới dạng file PDF chuyên nghiệp từ prompt của người dùng. Hệ thống tích hợp khả năng quét dịch nhãn sơ đồ động trực tiếp từ ảnh nguồn, biên dịch chất lượng cao thông qua **Typst** và tự động chạy **Rescue Pipeline 4 tầng** khi phát hiện lỗi mã hóa font hoặc bố cục.

---

## 🚀 Tính năng nổi bật

1. **Biên tập tài liệu bằng LLM (DeepSeek v4)**: Sử dụng **OpenCode API** làm nhà cung cấp dịch vụ ngôn ngữ chính (kèm cơ chế offline fallback tự động).
2. **Dịch nhãn ảnh thông minh (Dynamic Image Translation)**:
   * **2D Spatial Clustering**: Tự động gom nhóm các từ đơn lẻ theo trục ngang và trục dọc (xử lý gộp chữ xuống dòng động tương thích mọi độ phân giải).
   * **OpenCV Telea Inpainting**: Xóa sạch nhãn tiếng Anh cũ và phục dựng kết cấu nền ảnh tự nhiên thay vì tô màu phẳng.
   * **Pillow Typography**: Vẽ nhãn tiếng Việt mới bo góc sắc nét, tự động co giãn cỡ chữ (auto-scaling) và tự chọn màu tương phản dựa trên độ sáng (Luminance) của nền ảnh.
3. **Biên dịch PDF bằng Typst**: Nhanh gấp hàng chục lần LaTeX/PDFKit, sử dụng bộ font local được đóng gói sẵn để hiển thị tiếng Việt hoàn hảo.
4. **Kiểm định chất lượng PDF (Validator)**: Tự động quét tìm ký tự lỗi hiển thị `` (`U+FFFD`) hoặc nhãn tiếng Anh bị dịch sót.
5. **Cứu hộ tự động 4 tầng (4-Tier Rescue)**: Khi gặp lỗi biên dịch hoặc lỗi font, hệ thống tự động hạ cấp dần độ phức tạp để bảo đảm luôn xuất ra file PDF hợp lệ:
   $$\text{Unicode NFC} \rightarrow \text{Thay thế Font} \rightarrow \text{Đơn giản bố cục} \rightarrow \text{Văn bản thô (Plain-text)}$$
6. **Glassmorphism Web Dashboard**: Giao diện điều khiển Web phong cách kính mờ hiện đại, hỗ trợ kéo thả ảnh sơ đồ và xem preview PDF thời gian thực.

---

## 📂 Cấu trúc dự án

```text
module-gen-file-pdf/
├── src/
│   ├── app.py                 # Flask Backend & API
│   ├── demo.py                # CLI demo chạy end-to-end
│   ├── llm_client.py          # Gọi OpenCode API / Mock offline
│   ├── ocr_base.py            # [NEW] Định nghĩa Interface & Schema cho OCR
│   ├── report_image.py        # Xử lý nhãn ảnh và ghép phân đoạn phụ lục ảnh
│   ├── image_translator.py    # Thuật toán EasyOCR & OpenCV Inpaint xóa chữ
│   ├── typst_generator.py     # Chuyển đổi Markdown -> Typst -> PDF
│   ├── pdf_validator.py       # Trích xuất văn bản, kiểm tra lỗi & Rescue Pipeline
│   ├── mock_adapters.py       # Mock dữ liệu OCR & Translation khi offline
│   └── templates/
│       └── index.html         # Frontend Dashboard (HTML/CSS/JS)
├── fonts/                     # Thư mục chứa Roboto, Noto Sans, DejaVu Sans
├── tests/                     # Bộ kiểm thử tự động (Unit & Integration tests)
├── temp/                      # Thư mục lưu trữ PDF, ảnh tạm và output
├── docs/                      # Tài liệu thiết kế và hướng dẫn luồng hoạt động
├── requirements.txt           # Danh sách các thư viện Python phụ thuộc
└── .env                       # Cấu hình biến môi trường
```

---

## 🛠️ Cài đặt & Cấu hình

### 1. Yêu cầu hệ thống
* Python 3.x
* Môi trường ảo (virtualenv)

### 2. Cài đặt các thư viện phụ thuộc
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Cấu hình biến môi trường
Tạo file `.env` từ file mẫu `.env.example`:
```env
OPENCODE_API_KEY=your_api_key_here
OPENCODE_MODEL=deepseek-v4-flash-free
OPENCODE_BASE_URL=https://opencode.ai/zen/v1
OPENCODE_TIMEOUT=300
OCR_PROVIDER=easyocr
```
*(Nếu không có `OPENCODE_API_KEY`, engine sẽ tự động chạy ở chế độ **Offline Mock** mà không bị crash).*

---

## 💻 Hướng dẫn chạy chương trình

### Chạy CLI Demo (End-to-End)
```bash
venv/bin/python src/demo.py
```
*Kết quả PDF đầu ra được lưu tại `temp/demo_report.pdf`.*

### Chạy Web Dashboard
```bash
venv/bin/python src/app.py
```
*Truy cập [http://localhost:8085](http://localhost:8085) trên trình duyệt.*

### Chạy bộ kiểm thử tự động (Unit Tests)
```bash
OPENCODE_API_KEY= POLLINATIONS_API_KEY= \
venv/bin/python -m unittest discover -s tests
```

---

## 📐 Luồng xử lý Pipeline ảnh

```text
Ảnh Sơ đồ Gốc
  │
  ├──► [ocr_base.py] Factory quyết định OCRProvider (EasyOCR / Mock)
  │      │
  │      └──► [image_translator.py] Tìm tọa độ chữ & Gom nhóm 2D (Ngang & Dọc)
  │
  ├──► [llm_client.py] Dịch nhãn tiếng Anh sang Việt (Batch API call)
  │
  ├──► [image_translator.py] Tạo mask nhị phân & Chạy cv2.inpaint (Xóa nền sạch)
  │
  └──► [report_image.py] Pillow vẽ đè nhãn tiếng Việt bo góc tự scale font & đổi màu tương phản
         │
         └──► Ảnh sơ đồ tiếng Việt đã xử lý hoàn chỉnh
```
