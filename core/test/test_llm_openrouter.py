import os
import json
import unittest
import requests

OPENROUTER_BASE = "https://openrouter.ai/api/v1"


@unittest.skipUnless(
    os.environ.get("RUN_LLM_TESTS") == "1",
    "Set RUN_LLM_TESTS=1 untuk menjalankan tes OpenRouter"
)
class OpenRouterHealthTests(unittest.TestCase):
    """
    TEST INI AKAN:
    - Mengakses OpenRouter langsung
    - Menggunakan API key asli
    - Memakai kuota
    """

    def test_openrouter_chat_completion(self):
        api_key = os.environ.get("OPENROUTER_API_KEY")
        model = os.environ.get(
            "OPENROUTER_MODEL",
            "liquid/lfm-2.5-1.2b-thinking:free"
        )

        self.assertTrue(api_key, "OPENROUTER_API_KEY belum diset")

        payload = {
            "model": model,
            "messages": [
                {"role": "user", "content": "Balas hanya dengan kata: OK"}
            ],
            "temperature": 0.0,
        }

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost:8000",
            "X-Title": "AcademicChatbot",
        }

        response = requests.post(
            f"{OPENROUTER_BASE}/chat/completions",
            headers=headers,
            data=json.dumps(payload),
            timeout=30,
        )

        self.assertEqual(
            response.status_code,
            200,
            f"OpenRouter error: {response.status_code} {response.text[:200]}"
        )

        data = response.json()
        text = data["choices"][0]["message"]["content"].strip()

        self.assertIn("OK", text.upper())
