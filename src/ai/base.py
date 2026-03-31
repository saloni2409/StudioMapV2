from typing import Protocol, Tuple, List
import json
from models import StudioProfile

PDF_EXTRACTION_PROMPT = """
You are analysing a school studio documentation PDF.
This PDF may contain BOTH text AND embedded images/photographs/diagrams.
It may describe ONE studio or MULTIPLE studios.

Your job is to extract ALL available information — including:
- Text content (names, descriptions, specifications)
- Photographs: describe what you see in each photo (equipment, layout, student activity setups)
- Diagrams and floor plans: identify and name every labelled item, read any dimension callouts
- Tables: convert rows to structured data
- Captions under images: extract verbatim
- Any information visible on whiteboards, walls, labels, or equipment tags in photographs

IMPORTANT: If the PDF contains information about multiple distinct studios (separate rooms, spaces, or labs),
return a separate entry for EACH studio. Do not merge multiple studios into one.

Return a JSON object with a "studios" array. Return ONLY valid JSON — no markdown fences, no explanation, no preamble.

JSON structure:
{
  "studios": [
    {
      "name": "studio name",
      "tagline": "one sentence that captures what makes this studio unique",
      "description": "2-3 paragraphs describing the studio, its purpose, and philosophy",

      "affordances": {
        "individual_work":  true/false,
        "pair_work":        true/false,
        "group_work":       true/false,
        "movement":         true/false,
        "digital_practice": true/false,
        "physical_making":  true/false,
        "presentation":     true/false,
        "self_assessment":  true/false,
        "max_students":     number or null,
        "summary": "2-3 sentences describing what students CAN DO here based on both text and what you observe in photos."
      },

      "tools": [
        {
          "name": "exact name from text or label visible in photo",
          "description": "combine text description with what you observe in any photograph of this item",
          "quantity": number,
          "dimensions": "exact dimensions from text or any dimension callout in diagrams/floor plan",
          "interaction": "specifically how students use this — infer from photos if not stated",
          "movable": true/false
        }
      ],

      "grades":   ["5", "6", "7"],
      "subjects": ["English", "Science"],
      "board":    "CBSE" or "Karnataka State Board" or "Both",

      "area_sqft":   number or null,
      "capacity":    number or null,
      "lighting":    "describe lighting from text or from what is visible in photos",
      "ventilation": "describe ventilation from text or visible sources",

      "coursework": [
        {
          "topic":         "any activity idea mentioned in the PDF",
          "subject":       "inferred subject",
          "grades":        ["6"],
          "sessions":      1,
          "teaching_plan": "description from document",
          "teacher_notes": ""
        }
      ],

      "raw_notes": "Dump here anything else observed from photos, diagrams, or text that does not fit the above fields — layout observations, signage, poster content, visible student work, equipment brand names from photos, etc."
    }
  ]
}

Rules:
- LOOK AT EVERY IMAGE in the document. Describe what you see.
- If the PDF covers multiple studios, create a separate entry in the "studios" array for each one.
- Each studio entry must be self-contained — do not reference other studios in the array.
- Extract EVERY activity idea or usage suggestion from ANY source (text, photo captions, diagrams) as a coursework entry.
- If a photo shows equipment not mentioned in text, add it to tools anyway.
- Read every dimension label you can see in diagrams/floor plans.
- If grades not explicitly stated, infer from context.
- NEVER return null for array fields — use [] instead.
- Dimensions: preserve the original format (e.g. "3' 4\\" x 5' 7\\"").
"""

class AIProvider(Protocol):
    def extract_json_from_pdf(self, pdf_bytes: bytes) -> List[dict]:
        """Extracts a list of structured studio JSON dicts from a PDF byte stream.
        Returns a list — always, even if only one studio is found."""
        ...

    def generate_text(self, system_prompt: str, user_prompt: str) -> str:
        """Generates a text response based on system and user prompts."""
        ...

    def test_connection(self) -> Tuple[bool, str]:
        """Tests the connection to the provider and API keys."""
        ...
