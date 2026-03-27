import io
import json
import base64
from config import PDF_MAX_TOKENS, MAX_TOKENS, load_config
from .base import AIProvider, PDF_EXTRACTION_PROMPT


def _pdf_to_page_images(pdf_bytes: bytes) -> list[str]:
    """
    Render every PDF page to a JPEG and return base64 strings.
    Returns [] if pymupdf is not installed — caller falls back to text-only mode.
    """
    try:
        import fitz  # pymupdf
    except ImportError:
        return []   # graceful fallback

    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        images_b64 = []
        for page in doc:
            mat      = fitz.Matrix(2.0, 2.0)
            pix      = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
            img_bytes = pix.tobytes("jpeg")
            images_b64.append(base64.b64encode(img_bytes).decode("utf-8"))
        doc.close()
        return images_b64
    except Exception:
        return []


def _extract_text_with_fitz(pdf_bytes: bytes) -> str:
    """Extract text using pymupdf, falling back to PyPDF2 if not available."""
    try:
        import fitz
        doc  = fitz.open(stream=pdf_bytes, filetype="pdf")
        text = "\n".join(page.get_text() for page in doc)
        doc.close()
        return text
    except Exception:
        pass  # try PyPDF2 below

    try:
        import PyPDF2
        reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
        return "\n".join(p.extract_text() or "" for p in reader.pages)
    except ImportError:
        raise ImportError(
            "Cannot extract PDF text. Run:  pip install pymupdf\n"
            "(or: pip install PyPDF2)"
        )


class LocalProvider(AIProvider):
    def _client(self):
        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError("Please install openai: pip install openai")

        cfg = load_config()
        url = cfg.get("local_model_url", "http://127.0.0.1:11434/v1")
        return OpenAI(base_url=url, api_key="local")

    def _model_name(self) -> str:
        cfg = load_config()
        return cfg.get("local_model_name", "llama3")

    def extract_json_from_pdf(self, pdf_bytes: bytes) -> dict:
        client = self._client()

        # Render pages as images so the vision model can see photos & diagrams
        page_images = _pdf_to_page_images(pdf_bytes)
        fallback_text = _extract_text_with_fitz(pdf_bytes)

        print(f"DEBUG: Rendered {len(page_images)} page(s) as images. Text fallback: {len(fallback_text)} chars.")

        # Build a vision message with every page image + extracted text
        content = []
        for i, img_b64 in enumerate(page_images):
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{img_b64}",
                    "detail": "high"
                }
            })

        # Add text dump as additional context
        if fallback_text.strip():
            content.append({
                "type": "text",
                "text": f"EXTRACTED TEXT (for reference, may be incomplete):\n\n{fallback_text[:8000]}"
            })

        content.append({
            "type": "text",
            "text": PDF_EXTRACTION_PROMPT
        })

        response = client.chat.completions.create(
            model=self._model_name(),
            max_tokens=PDF_MAX_TOKENS,
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": content}]
        )

        raw = response.choices[0].message.content.strip()
        print(f"DEBUG: LLM response length: {len(raw)}, start: {raw[:80]}")

        start = raw.find('{')
        end   = raw.rfind('}')
        raw_json = raw[start:end+1] if start != -1 and end != -1 else raw

        try:
            return json.loads(raw_json)
        except json.JSONDecodeError as e:
            print(f"ERROR: JSON decode failed: {e}\nFull response:\n{raw}")
            raise ValueError(f"Model did not return valid JSON. Error: {e}. Check terminal for raw output.")

    def generate_text(self, system_prompt: str, user_prompt: str) -> str:
        client = self._client()
        response = client.chat.completions.create(
            model=self._model_name(),
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
                model=self._model_name(),
                max_tokens=10,
                messages=[{"role": "user", "content": "hi"}]
            )
            return True, f"Local model '{self._model_name()}' connection successful."
        except Exception as e:
            return False, f"Local Provider Error: {str(e)}"
