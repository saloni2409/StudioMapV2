import os
import io
import json
import time
import base64
import anthropic

from config import CLAUDE_MODEL, PDF_MAX_TOKENS, MAX_TOKENS, load_config
from .base import AIProvider, PDF_EXTRACTION_PROMPT

# Split PDFs larger than this into chunks (bytes). ~4MB ≈ ~20k tokens for a typical PDF.
_CHUNK_THRESHOLD_BYTES = 4 * 1024 * 1024
_PAGES_PER_CHUNK = 10   # pages per API call when chunking

def _split_pdf_by_pages(pdf_bytes: bytes, pages_per_chunk: int) -> list[bytes]:
    """Split a PDF into chunks of N pages each. Returns list of PDF byte strings."""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return [pdf_bytes]  # can't split, send whole thing

    src = fitz.open(stream=pdf_bytes, filetype="pdf")
    total = src.page_count
    chunks = []
    for start in range(0, total, pages_per_chunk):
        end = min(start + pages_per_chunk, total)
        out = fitz.open()
        out.insert_pdf(src, from_page=start, to_page=end - 1)
        buf = io.BytesIO()
        out.save(buf)
        chunks.append(buf.getvalue())
        out.close()
    src.close()
    return chunks


def _call_with_retry(client: anthropic.Anthropic, pdf_bytes: bytes,
                     max_retries: int = 4) -> list[dict]:
    """Send one PDF chunk to Claude with exponential backoff on 429."""
    pdf_b64 = base64.standard_b64encode(pdf_bytes).decode("utf-8")
    delay = 60  # start with 60s on first 429 (rate limit window is 1 min)

    for attempt in range(max_retries):
        try:
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
            break
        except anthropic.RateLimitError:
            if attempt == max_retries - 1:
                raise
            time.sleep(delay)
            delay = min(delay * 2, 300)  # cap at 5 minutes
    else:
        raise RuntimeError("Exhausted retries due to rate limiting.")

    raw = response.content[0].text.strip()
    start = raw.find('{')
    end   = raw.rfind('}')
    if start != -1 and end != -1:
        raw = raw[start:end+1]

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        raise ValueError(f"Model did not return valid JSON. Raw output: {raw[:200]}...")

    if isinstance(parsed, list):
        return parsed
    studios = parsed.get("studios")
    if isinstance(studios, list):
        return studios
    return [parsed]


class AnthropicProvider(AIProvider):
    def _client(self) -> anthropic.Anthropic:
        cfg = load_config()
        key = cfg.get("anthropic_api_key") or os.environ.get("ANTHROPIC_API_KEY", "")
        return anthropic.Anthropic(api_key=key) if key else anthropic.Anthropic()

    def extract_json_from_pdf(self, pdf_bytes: bytes) -> list[dict]:
        client = self._client()

        # For large PDFs, split into page chunks and merge results
        if len(pdf_bytes) > _CHUNK_THRESHOLD_BYTES:
            chunks = _split_pdf_by_pages(pdf_bytes, _PAGES_PER_CHUNK)
        else:
            chunks = [pdf_bytes]

        all_studios: list[dict] = []
        seen_names: set[str] = set()

        for chunk in chunks:
            studios = _call_with_retry(client, chunk)
            for studio in studios:
                name = studio.get("name", "")
                # Deduplicate studios that appear across chunk boundaries
                if name and name in seen_names:
                    continue
                if name:
                    seen_names.add(name)
                all_studios.append(studio)
            # Small pause between chunks to stay within rate limits
            if len(chunks) > 1:
                time.sleep(5)

        return all_studios if all_studios else [{}]

    def generate_text(self, system_prompt: str, user_prompt: str) -> str:
        client = self._client()
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=MAX_TOKENS,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}]
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
