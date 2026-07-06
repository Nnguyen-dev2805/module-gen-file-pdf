import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Ensure src/ is in the python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.llm_client import OpenCodeClient, MOCK_REPORT


class TestOpenCodeClient(unittest.TestCase):

    @patch.dict(os.environ, {}, clear=True)
    def test_mock_mode_initialization(self):
        client = OpenCodeClient()

        self.assertTrue(client.mock_mode)
        self.assertEqual(client.provider, "mock")
        self.assertIsNone(client.api_key)

    @patch.dict(
        os.environ,
        {
            "OPENCODE_API_KEY": "fake_open_key",
            "OPENCODE_MODEL": "deepseek-v4-flash-free",
            "OPENCODE_TIMEOUT": "300",
        },
        clear=True,
    )
    def test_opencode_mode_initialization(self):
        client = OpenCodeClient()

        self.assertFalse(client.mock_mode)
        self.assertEqual(client.provider, "opencode")
        self.assertEqual(client.opencode_model, "deepseek-v4-flash-free")
        self.assertEqual(client.opencode_timeout, 300)

    @patch.dict(os.environ, {}, clear=True)
    def test_generate_report_mock(self):
        client = OpenCodeClient()
        report = client.generate_report("Generate a report")

        self.assertEqual(report, MOCK_REPORT)
        self.assertIn("Báo cáo Cấu trúc Hoạt động Kho bãi", report)
        self.assertIn("mock://warehouse_layout.png", report)

    @patch.dict(os.environ, {}, clear=True)
    def test_translate_labels_mock(self):
        client = OpenCodeClient()
        labels = ["Truck Yard", "ASRS Storage", "Unknown Word"]
        translations = client.translate_labels(labels)

        self.assertEqual(translations["Truck Yard"], "Bãi đỗ xe tải")
        self.assertEqual(translations["ASRS Storage"], "Kho tự động ASRS")
        self.assertEqual(translations["Unknown Word"], "Unknown Word")

    @patch.dict(
        os.environ,
        {"OPENCODE_API_KEY": "fake_open_key", "OPENCODE_MODEL": "deepseek-v4-flash-free"},
        clear=True,
    )
    @patch("requests.post")
    def test_generate_report_opencode_success(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": (
                            "# Báo cáo kho hàng\n\n"
                            "| Hạng mục | Mô tả |\n"
                            "| :--- | :--- |\n"
                            "| Robot | Vận chuyển hàng tự động |"
                        )
                    }
                }
            ]
        }
        mock_post.return_value = mock_response

        client = OpenCodeClient()
        report = client.generate_report("Tạo báo cáo")

        self.assertIn("| Hạng mục | Mô tả |", report)
        mock_post.assert_called_once()

    @patch.dict(os.environ, {"OPENCODE_API_KEY": "fake_open_key"}, clear=True)
    @patch("requests.post")
    def test_translate_labels_opencode_success(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": (
                            "```json\n"
                            "{\"translations\":[{\"english\":\"Truck Yard\",\"vietnamese\":\"Bãi xe tải\"}]}"
                            "\n```"
                        )
                    }
                }
            ]
        }
        mock_post.return_value = mock_response

        client = OpenCodeClient()
        result = client.translate_labels(["Truck Yard"])

        self.assertEqual(result["Truck Yard"], "Bãi xe tải")
        mock_post.assert_called_once()

    @patch.dict(os.environ, {"OPENCODE_API_KEY": "fake_open_key"}, clear=True)
    @patch("requests.post")
    def test_generate_report_opencode_failure_falls_back_to_mock(self, mock_post):
        mock_post.side_effect = TimeoutError("simulated timeout")

        client = OpenCodeClient()
        report = client.generate_report("Tạo báo cáo")

        self.assertEqual(report, MOCK_REPORT)
        self.assertTrue(
            any("OpenCode report generation failed" in item for item in client.api_status)
        )

    @patch.dict(os.environ, {"OPENCODE_API_KEY": "fake_open_key"}, clear=True)
    @patch("requests.post")
    def test_translate_labels_opencode_failure_falls_back_to_mock(self, mock_post):
        mock_post.side_effect = TimeoutError("simulated timeout")

        client = OpenCodeClient()
        result = client.translate_labels(["Truck Yard"])

        self.assertEqual(result["Truck Yard"], "Bãi đỗ xe tải")
        self.assertTrue(
            any("OpenCode label translation failed" in item for item in client.api_status)
        )


if __name__ == "__main__":
    unittest.main()
