import asyncio
import base64
from typing import Any, Dict, List, Optional

import google.generativeai as genai


class GeminiClient:
    def __init__(self, api_key: str, model: str = "gemini-1.5-flash") -> None:
        genai.configure(api_key=api_key)
        self.model_name = model

    def start_chat(self, history: Optional[List[Dict[str, Any]]] = None) -> Any:
        model = genai.GenerativeModel(self.model_name)
        return model.start_chat(history=history or [])

    async def generate_with_image_and_text(
        self,
        image_bytes: bytes,
        mime_type: str,
        text: str,
    ) -> str:
        model = genai.GenerativeModel(self.model_name)
        # google-generativeai is sync; run in thread
        def _call() -> Any:
            return model.generate_content(
                [
                    {"mime_type": mime_type, "data": image_bytes},
                    text,
                ]
            )

        resp = await asyncio.to_thread(_call)
        return resp.text or ""


