import io
import json
import base64
from config import OPENAI_MODEL, PDF_MAX_TOKENS, MAX_TOKENS, load_config
from .base import AIProvider, PDF_EXTRACTION_PROMPT
from .local_provider import _pdf_to_page_images, _extract_text_with_fitz


class OpenAIProvider(AIProvider):
    def _client(self):
        import os
        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError("Please install openai: pip install openai")

        cfg = load_config()
        key = cfg.get("openai_api_key") or os.environ.get("OPENAI_API_KEY", "")
        return OpenAI(api_key=key)

    def extract_json_from_pdf(self, pdf_bytes: bytes) -> dict:
        client = self._client()

        # Render pages as images — GPT-4o can see photos, diagrams, dimension callouts
        page_images = _pdf_to_page_images(pdf_bytes)
        fallback_text = _extract_text_with_fitz(pdf_bytes)

        print(f"DEBUG: Rendered {len(page_images)} page(s) as images for OpenAI. Text: {len(fallback_text)} chars.")

        content = []
        for img_b64 in page_images:
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{img_b64}",
                    "detail": "high"
                }
            })

        if fallback_text.strip():
            content.append({
                "type": "text",
                "text": f"EXTRACTED TEXT (for reference):\n\n{fallback_text[:8000]}"
            })

        content.append({
            "type": "text",
            "text": PDF_EXTRACTION_PROMPT
        })

        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            max_tokens=PDF_MAX_TOKENS,
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": content}]
        )

        raw = response.choices[0].message.content.strip()

        start = raw.find('{')
        end   = raw.rfind('}')
        raw_json = raw[start:end+1] if start != -1 and end != -1 else raw

        try:
            return json.loads(raw_json)
        except json.JSONDecodeError as e:
            print(f"ERROR: JSON decode failed: {e}\nFull response:\n{raw}")
            raise ValueError(f"Model did not return valid JSON. Error: {e}. Check terminal for full output.")

    def generate_text(self, system_prompt: str, user_prompt: str) -> str:
        client = self._client()
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            max_tokens=MAX_TOKENS,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt}
            ]
        )
        return response.choices[0].message.content

    def test_connection(self) -> tuple[bool, str]:
        try:
            client = self._client()
            client.chat.completions.create(
                model=OPENAI_MODEL,
                max_tokens=10,
                messages=[{"role": "user", "content": "hi"}]
            )
            return True, "OpenAI API key valid."
        except Exception as e:
            return False, f"OpenAI Error: {str(e)}"
