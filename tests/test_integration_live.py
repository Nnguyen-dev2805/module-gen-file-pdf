import os
import sys
import unittest

# Ensure src/ is in the python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.llm_client import OpenCodeClient, MOCK_REPORT


class TestLiveOpenCodeClient(unittest.TestCase):

    def setUp(self):
        self.api_key = os.environ.get("OPENCODE_API_KEY")
        if not self.api_key:
            self.skipTest(
                "OPENCODE_API_KEY environment variable is not set. "
                "Skipping live OpenCode integration tests."
            )

    def test_live_generate_report(self):
        client = OpenCodeClient()
        self.assertFalse(client.mock_mode)
        self.assertEqual(client.provider, "opencode")

        prompt = (
            "Viết một báo cáo tiếng Việt ngắn về lợi ích của kho hàng tự động. "
            "Bắt buộc có một bảng Markdown 2 cột."
        )
        report = client.generate_report(prompt)

        self.assertTrue(len(report) > 0, "Report should not be empty")
        self.assertNotEqual(report, MOCK_REPORT, "Report should not be the mock fallback")
        self.assertIn("|", report, "Report should contain a Markdown table")

    def test_live_translate_labels(self):
        client = OpenCodeClient()
        self.assertFalse(client.mock_mode)
        self.assertEqual(client.provider, "opencode")

        labels = ["ASRS Storage", "Inbound Processing"]
        translations = client.translate_labels(labels)

        self.assertIsInstance(translations, dict)
        self.assertIn("ASRS Storage", translations)
        self.assertIn("Inbound Processing", translations)
        self.assertTrue(len(translations["ASRS Storage"]) > 0)
        self.assertTrue(len(translations["Inbound Processing"]) > 0)


if __name__ == "__main__":
    unittest.main()
