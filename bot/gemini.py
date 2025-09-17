import asyncio
from typing import Any, Dict, List, Optional

import google.generativeai as genai
from google.api_core.exceptions import FailedPrecondition, GoogleAPICallError


class GeminiClient:
    def __init__(self, api_key: str, model: str = "gemini-1.5-flash", system_prompt: str | None = None) -> None:
        genai.configure(api_key=api_key)
        self.model_name = model
        self.system_prompt = system_prompt or ""

    def start_chat(self, history: Optional[List[Dict[str, Any]]] = None) -> Any:
        model = genai.GenerativeModel(self.model_name)
        hist = []
        if self.system_prompt:
            hist.append({"role": "system", "parts": [self.system_prompt]})
        if history:
            hist.extend(history)
        return model.start_chat(history=hist)

    async def generate_with_image_and_text(
        self,
        image_bytes: bytes,
        mime_type: str,
        text: str,
    ) -> tuple[str, Any]:
        model = genai.GenerativeModel(self.model_name)
        # google-generativeai is sync; run in thread
        def _call() -> Any:
            return model.generate_content(
                [
                    {"mime_type": mime_type, "data": image_bytes},
                    text,
                ]
            )

        try:
            resp = await asyncio.to_thread(_call)
            return (resp.text or "", resp)
        except FailedPrecondition as e:
            # Typical message: "User location is not supported for the API use."
            raise RuntimeError("gemini_region_blocked") from e
        except GoogleAPICallError as e:
            raise RuntimeError("gemini_api_error") from e
        except Exception as e:
            raise RuntimeError("gemini_unknown_error") from e


