import os
import json
import base64
import anthropic

from config import CLAUDE_MODEL, PDF_MAX_TOKENS, MAX_TOKENS, load_config
from .base import AIProvider, PDF_EXTRACTION_PROMPT

class AnthropicProvider(AIProvider):
    def _client(self) -> anthropic.Anthropic:
        cfg = load_config()
        key = cfg.get("anthropic_api_key") or os.environ.get("ANTHROPIC_API_KEY", "")
        return anthropic.Anthropic(api_key=key) if key else anthropic.Anthropic()

    def extract_json_from_pdf(self, pdf_bytes: bytes) -> dict:
        client = self._client()
        pdf_b64 = base64.standard_b64encode(pdf_bytes).decode("utf-8")

        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=PDF_MAX_TOKENS,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type":       "base64",
                            "media_type": "application/pdf",
                            "data":       pdf_b64
                        }
                    },
                    {"type": "text", "text": PDF_EXTRACTION_PROMPT}
                ]
            }]
        )

        raw = response.content[0].text.strip()
        
        start = raw.find('{')
        end = raw.rfind('}')
        if start != -1 and end != -1:
            raw = raw[start:end+1]
            
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            raise ValueError(f"Model did not return valid JSON. Raw output: {raw[:200]}...")

    def generate_text(self, system_prompt: str, user_prompt: str) -> str:
        client = self._client()
        # Anthropic standard: put system instructions in user prompt or 'system' parameter.
        # Here we just combine them.
        prompt = f"{system_prompt}\\n\\n{user_prompt}"

        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}]
        )

        return response.content[0].text

    def test_connection(self) -> tuple[bool, str]:
        try:
            client = self._client()
            client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=10,
                messages=[{"role": "user", "content": "hi"}]
            )
            return True, "API key valid."
        except anthropic.AuthenticationError:
            return False, "Invalid API key. Check Settings."
        except Exception as e:
            return False, str(e)
