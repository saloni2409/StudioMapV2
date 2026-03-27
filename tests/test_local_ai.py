import sys
from pathlib import Path

# Add src to sys.path so we can import app modules directly
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from config import load_config, save_config
from ai import get_provider

def run_test():
    print("--- Starting AI Provider Test ---")
    
    # 1. Force the config internally so it uses Local
    cfg = load_config()
    cfg["ai_provider"] = "local"
    cfg["local_model_name"] = "llama3:latest"
    cfg["local_model_url"] = "http://127.0.0.1:11434/v1"
    save_config(cfg)
    print("Config set to Local Mode with llama3:latest")

    # 2. Extract PDF bytes
    pdf_path = Path("tests/Duolingo Lab Studio Mapping (1).pdf")
    if not pdf_path.exists():
        print("ERROR: tests/dummy_studio.pdf not found. Please run generate_test_pdf.py first.")
        return

    pdf_bytes = pdf_path.read_bytes()
    print(f"Read {len(pdf_bytes)} bytes from PDF.")
    
    # 3. Call the provider directly
    provider = get_provider()
    print("Calling extract_json_from_pdf on LocalProvider...")
    try:
        result = provider.extract_json_from_pdf(pdf_bytes)
        print("SUCCESS! Model returned valid JSON.")
        print("--- PARSED JSON ---")
        print(result)
    except Exception as e:
        print("FAILED!")
        print(str(e))
        
        # If it threw a ValueError, the stacktrace will contain the raw.
        # But to be extremely sure what we got from Ollama, let's bypass the helper
        # and print the raw string manually if it falls into exception.
        print("\\n--- RAW RESPONSE ---")
        # Reproducing the raw query to get the exact output from OpenAI SDK!
        try:
            client = provider._client()
            import PyPDF2
            import io
            reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
            text = ""
            for page in reader.pages:
                extracted = page.extract_text()
                if extracted:
                    text += extracted + "\\n"
                    
            from ai.base import PDF_EXTRACTION_PROMPT
            resp = client.chat.completions.create(
                model=provider._model_name(),
                max_tokens=4096,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": PDF_EXTRACTION_PROMPT},
                    {"role": "user", "content": f"Here is the PDF text:\\n\\n{text}"}
                ]
            )
            raw = resp.choices[0].message.content
            print("====RAW LLM DUMP====")
            print(raw)
            print("====================")
        except Exception as internal_e:
            print("Internal reproduction failed:", internal_e)

if __name__ == "__main__":
    run_test()
