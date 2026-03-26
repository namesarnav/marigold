from typing import List, Dict, Any

from google import genai

from .config import get_settings


settings = get_settings()


async def generate_flashcards(extracted_text: str, n: int = 15) -> List[Dict[str, Any]]:
    prompt = f"""
You are a study assistant. Extract flashcards from the following text.
Return ONLY a JSON array, no markdown, no explanation. Format:
[
  {{
    "question": "...",
    "answer": "...",
    "topic": "...",
    "distractors": ["wrong1", "wrong2", "wrong3"]
  }}
]

Generate exactly {n} flashcards. Cover the most important concepts.
Text: {extracted_text}
"""

    client = genai.Client(api_key=settings.gemini_api_key)

    # google-genai uses sync I/O; call it in a thread so our FastAPI handler can stay async.
    import anyio

    def _call_model() -> str:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        # response.text is a convenience that concatenates parts
        return response.text

    text = await anyio.to_thread.run_sync(_call_model)

    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]

    import json

    return json.loads(cleaned)

