import json
import os
import re
from typing import Any, Dict, List

import requests
from dotenv import load_dotenv

from src.mock_adapters import MOCK_TRANSLATION_MAP

# Load environment variables from .env file.
load_dotenv()


MOCK_REPORT = """# Báo cáo Cấu trúc Hoạt động Kho bãi (Warehouse Report)

Tài liệu này đánh giá tổng quan về luồng hoạt động trong kho hàng tự động thông minh.

## 1. Lưu lượng và Sắp xếp Pallet (Pallet Storage)
Hệ thống sử dụng các thiết bị tự động và xe tự hành để tối đa hóa không gian và tốc độ xuất nhập hàng:

| Khu vực (Area) | Sức chứa tối đa (Capacity) | Trạng thái (Status) |
| :--- | :--- | :--- |
| Cảng nhập hàng | 100 Pallets | Đang hoạt động |
| Kho tự động ASRS | 8,000 - 10,000 Pallets | Sẵn sàng |
| Cảng xuất hàng | 100 Pallets | Đang hoạt động |

## 2. Giao diện Sơ đồ Phân khu Kho hàng (Warehouse Layout)
Dưới đây là sơ đồ mặt bằng tổng thể của kho hàng thông minh:

! [Sơ đồ kho hàng] (mock://warehouse_layout.png)

## 3. Các quy trình cốt lõi
1. **Xử lý hàng nhập (Inbound Processing):** Kiểm tra chất lượng và dán nhãn pallet.
2. **Lưu trữ tự động ASRS (ASRS Storage):** Cẩu tự động xếp hàng vào các dãy lối đi.
3. **Xử lý hàng xuất (Outbound Processing):** Đóng gói và chuyển ra cảng xuất hàng.
"""


OPENCODE_DEFAULT_BASE_URL = "https://opencode.ai/zen/v1"
OPENCODE_DEFAULT_MODEL = "deepseek-v4-flash-free"
OPENCODE_DEFAULT_TIMEOUT = 300


class OpenCodeClient:
    """
    OpenCode-only client for report generation and label translation.

    If OPENCODE_API_KEY is missing, the client enters deterministic mock mode.
    """

    def __init__(self):
        self.opencode_api_key = os.environ.get("OPENCODE_API_KEY")
        self.opencode_base_url = os.environ.get(
            "OPENCODE_BASE_URL",
            OPENCODE_DEFAULT_BASE_URL,
        ).rstrip("/")
        self.opencode_model = os.environ.get("OPENCODE_MODEL", OPENCODE_DEFAULT_MODEL)
        self.opencode_timeout = int(
            os.environ.get("OPENCODE_TIMEOUT", str(OPENCODE_DEFAULT_TIMEOUT))
        )

        self.api_key = self.opencode_api_key
        self.api_status: List[str] = []
        self.provider = "mock"
        self.mock_mode = True

        if self.opencode_api_key:
            self.provider = "opencode"
            self.mock_mode = False
            self.api_status.append(f"Using OpenCode model: {self.opencode_model}")
        else:
            self.api_status.append("OpenCode API key missing (running in offline mock mode)")

    def _chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.2,
    ) -> str:
        """
        Calls the OpenCode OpenAI-compatible chat completions endpoint.
        """
        url = f"{self.opencode_base_url}/chat/completions"
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

        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError(
                f"OpenCode returned non-JSON response: {response.text[:200]}"
            ) from exc

        if response.status_code >= 400 or "error" in payload:
            error = payload.get("error", payload)
            if isinstance(error, dict):
                message = error.get("message") or json.dumps(error, ensure_ascii=False)
            else:
                message = str(error)
            raise RuntimeError(f"OpenCode API returned {response.status_code}: {message}")

        choices = payload.get("choices") or []
        if not choices:
            raise RuntimeError("OpenCode API response did not contain choices")

        message = choices[0].get("message", {})
        content = message.get("content", "")
        if isinstance(content, list):
            content = "\n".join(
                part.get("text", "") if isinstance(part, dict) else str(part)
                for part in content
            )

        content = str(content).strip()
        if not content:
            raise RuntimeError("OpenCode API returned an empty message")
        return content

    @staticmethod
    def _load_json_from_model_text(text: str) -> Dict[str, Any]:
        """
        Parses JSON from model output, tolerating fenced JSON blocks.
        """
        cleaned = text.strip()
        fenced = re.search(
            r"```(?:json)?\s*(.*?)```",
            cleaned,
            flags=re.DOTALL | re.IGNORECASE,
        )
        if fenced:
            cleaned = fenced.group(1).strip()
        return json.loads(cleaned)

    def generate_report(self, prompt: str) -> str:
        """
        Generates a Vietnamese Markdown report based on a prompt.
        If mock mode is active, returns a deterministic mock report.
        """
        if self.mock_mode:
            return MOCK_REPORT

        try:
            system_prompt = (
                "Bạn là chuyên gia biên tập kỹ thuật. "
                "Hãy tạo báo cáo bằng Markdown tiếng Việt, rõ ràng, có cấu trúc. "
                "Bắt buộc có: tiêu đề H1, các đoạn văn giải thích, ít nhất một bảng Markdown "
                "đúng cú pháp, và danh sách gạch đầu dòng hoặc đánh số. "
                "Không bọc câu trả lời trong code fence. Hạn chế dùng cụm tiếng Anh nếu không cần thiết."
            )
            user_prompt = (
                f"{prompt}\n\n"
                "Yêu cầu đầu ra: trả về trực tiếp nội dung Markdown tiếng Việt để render PDF. "
                "Bảng Markdown nên có 2-4 cột và có hàng phân cách `| :--- |` hợp lệ."
            )
            return self._chat_completion(
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.2,
            )
        except Exception as e:
            self.api_status.append(f"OpenCode report generation failed: {e}")
            print(f"Warning: OpenCode API call failed ({e}). Falling back to mock report.")
            return MOCK_REPORT

    def translate_labels(self, labels: List[str]) -> Dict[str, str]:
        """
        Translates diagram labels from English to Vietnamese using OpenCode.
        Falls back to MOCK_TRANSLATION_MAP in mock mode or on API failure.
        """
        if self.mock_mode:
            return {label: MOCK_TRANSLATION_MAP.get(label, label) for label in labels}

        try:
            prompt = (
                "Translate these diagram labels to Vietnamese. "
                "If a label is already in Vietnamese or is a number, preserve it exactly as-is. "
                "Return strict JSON only, no markdown, no explanation. "
                "Schema: {\"translations\": [{\"english\": string, \"vietnamese\": string}]}. "
                f"Labels: {json.dumps(labels, ensure_ascii=False)}"
            )
            response_text = self._chat_completion(
                [
                    {
                        "role": "system",
                        "content": "You translate technical diagram labels into concise Vietnamese and preserve existing Vietnamese labels.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.0,
            )
            data = self._load_json_from_model_text(response_text)
            raw_translations = data.get("translations", {})
            result: Dict[str, str] = {}

            if isinstance(raw_translations, list):
                for item in raw_translations:
                    if isinstance(item, dict):
                        eng = item.get("english")
                        vie = item.get("vietnamese")
                        if eng and vie:
                            result[eng] = vie
            elif isinstance(raw_translations, dict):
                result = raw_translations

            for label in labels:
                if label not in result:
                    result[label] = MOCK_TRANSLATION_MAP.get(label, label)
            return result
        except Exception as e:
            self.api_status.append(f"OpenCode label translation failed: {e}")
            print(
                "Warning: OpenCode translation call failed "
                f"({e}). Falling back to mock translation map."
            )
            return {label: MOCK_TRANSLATION_MAP.get(label, label) for label in labels}
